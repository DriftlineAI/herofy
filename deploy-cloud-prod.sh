#!/usr/bin/env bash
#
# Deploy the Herofy backend (Cloud Run "herofy-api") + frontend (Firebase Hosting) to PRODUCTION.
#
# Smart-runner behavior:
#   - fail-fast: stops on the first failing command (set -euo pipefail + ERR trap)
#   - preflight: shows the environment and offers to re-authenticate first
#   - interactive: asks for confirmation before every step
#   - resumable: re-run from any step after a failure, no need to repeat earlier steps
#
# Usage:
#   ./deploy-cloud-prod.sh                 # interactive, all steps
#   ./deploy-cloud-prod.sh --from 2b       # resume at step 2b (skip 1, 1b, 2)
#   AUTO_YES=true ./deploy-cloud-prod.sh   # non-interactive (or pass -y / --yes)
#
# Step IDs: 1 (build)  1b (secret IAM)  2 (deploy)  2b (public invoker)  3 (frontend)
#
set -euo pipefail

# ───────────────────────────── configuration ─────────────────────────────
export ENVIRONMENT="production"
export PROJECT_ID="herofy-496505"
export REGION="us-central1"
export AR_REPO="herofy"
export API_SERVICE_PROD="herofy-api"
export APP_URL_PROD="https://herofy.ai"
export APP_BASE_URL="${APP_URL_PROD}"
export API_BASE_URL="${API_SERVICE_PROD}"
export REPO_ROOT="$(git rev-parse --show-toplevel)"

# Email - Resend
# API key lives in Secret Manager as secret name RESEND_API_KEY (uppercase, so the
# auto-mount on the SECRETS line below maps it to env var RESEND_API_KEY). Never hardcode it here.
#   printf '%s' 'YOUR_KEY' | gcloud secrets create RESEND_API_KEY --project="$PROJECT_ID" --data-file=-
export RESEND_NOTIFY_EMAIL=hello@herofy.ai
export RESEND_FROM_EMAIL=noreply@herofy.ai

# Service account the Cloud Run revision runs as (must exist before first deploy)
export RUNTIME_SA="herofy-api-runner@${PROJECT_ID}.iam.gserviceaccount.com"
export GIT_SHA="$(git rev-parse --short HEAD)"
export IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${API_SERVICE_PROD}:${GIT_SHA}"

export env_vars="ENVIRONMENT=production,FIREBASE_PROJECT_ID=${PROJECT_ID},USE_DATACONNECT=true,USE_DATACONNECT_EMULATOR=false,DATACONNECT_LOCATION=us-central1,DATACONNECT_SERVICE=herofy-prod-service,DATACONNECT_CONNECTOR=herofy,LOG_LEVEL=INFO,APP_BASE_URL=${APP_URL_PROD},API_BASE_URL=${API_SERVICE_PROD},GOOGLE_CLOUD_PROJECT=${PROJECT_ID},RESEND_NOTIFY_EMAIL=${RESEND_NOTIFY_EMAIL},RESEND_FROM_EMAIL=${RESEND_FROM_EMAIL},GOOGLE_OAUTH_REDIRECT_URI=${APP_URL_PROD}/integrations/gmail/callback,NOTION_OAUTH_REDIRECT_URI=${APP_URL_PROD}/integrations/notion/callback,NOTION_AUTHORIZATION_URL=https://api.notion.com/v1/oauth/authorize?client_id=364d872b-594c-817d-86f0-0037946408a1&response_type=code&owner=user&redirect_uri=https%3A%2F%2Fherofy.ai%2Fintegrations%2Fnotion%2Fcallback,LANGFUSE_HOST=https://us.cloud.langfuse.com,DEMO_ENABLED=true"

# Mock mode for testing
USE_MOCK_NOTION=false

# ───────────────────────────── args ─────────────────────────────
AUTO_YES="${AUTO_YES:-false}"
FROM="${FROM:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes)    AUTO_YES=true ;;
    --from)      FROM="${2:-}"; shift ;;
    --from=*)    FROM="${1#*=}" ;;
    -h|--help)   grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)           echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

STEP_IDS=(1 1b 2 2b 3)
if [[ -n "$FROM" ]]; then
  # shellcheck disable=SC2076
  [[ " ${STEP_IDS[*]} " == *" ${FROM} "* ]] || { echo "Invalid --from '${FROM}'. Valid: ${STEP_IDS[*]}" >&2; exit 2; }
fi

# ───────────────────────────── helpers ─────────────────────────────
trap 'rc=$?; echo ""; echo "❌ FAILED at line ${LINENO} (exit ${rc}). Deploy stopped. Re-run from this step with: ./deploy-cloud-prod.sh --from <step>"; exit "${rc}"' ERR

step() {
  echo ""
  echo "════════════════════════════════════════════════════════════════"
  echo "▶  $1"
  echo "════════════════════════════════════════════════════════════════"
}

# Yes/No prompt. Returns 0 for yes, 1 for no. Default = No. Reads from the terminal
# so it still works if the script's stdout is piped/redirected.
ask() {
  [[ "$AUTO_YES" == "true" ]] && return 0
  local reply
  read -r -p "$1 [y/N] " reply < /dev/tty || return 1
  [[ "$reply" =~ ^[yY]([eE][sS])?$ ]]
}

# Gate a step on confirmation; abort the whole deploy on No.
gate() {
  ask "$1" || { echo "✋ Aborted by user. No further steps will run."; exit 0; }
}

ok() { echo "✅ $1"; }

# Resume support: want <step-id> returns 0 if this step should run, 1 (with a skip
# notice) if we haven't yet reached the --from start point.
_started=true
[[ -n "$FROM" ]] && _started=false
want() {
  local id="$1"
  [[ "$_started" == true ]] && return 0
  if [[ "$id" == "$FROM" ]]; then _started=true; return 0; fi
  echo "⏭  Skipping step ${id} (resuming from ${FROM})."
  return 1
}

# ───────────────────────────── preflight: auth + environment ─────────────────────────────
step "Preflight — environment & authentication"

ACTIVE_ACCT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -1 || true)"
ACTIVE_PROJ="$(gcloud config get-value project 2>/dev/null || true)"

cat <<EOF
  Target environment : ${ENVIRONMENT}
  GCP project        : ${PROJECT_ID}   (gcloud active: ${ACTIVE_PROJ:-<none>})
  Region             : ${REGION}
  Cloud Run service  : ${API_SERVICE_PROD}
  Runtime SA         : ${RUNTIME_SA}
  Image URI          : ${IMAGE_URI}
  App URL            : ${APP_URL_PROD}
  gcloud account     : ${ACTIVE_ACCT:-<none — not logged in>}
  Resume from        : ${FROM:-<all steps>}
EOF

if [[ -z "$ACTIVE_ACCT" ]]; then
  echo ""
  echo "⚠️  No active gcloud account detected — re-authentication is required."
fi

if ask "Re-authenticate now (gcloud login + application-default + firebase)?"; then
  gcloud auth login
  gcloud auth application-default login
  firebase login --reauth || firebase login
  ok "Re-authenticated."
fi

# Pin the active project so nothing targets the wrong one.
gcloud config set project "$PROJECT_ID" >/dev/null
ok "Active project set to ${PROJECT_ID}."

# Compute the secret mount list (needs auth). Shown so you can eyeball what gets mounted.
export SECRETS="$(gcloud secrets list --project="$PROJECT_ID" --format='value(name)' \
  | xargs -I {} echo {}={}:latest | paste -sd "," -)"
echo ""
echo "Secrets that will be mounted (name=name:latest):"
echo "  ${SECRETS//,/$'\n'  }"
echo ""
echo "Env vars:"
echo "  ${env_vars}"

# ───────────────────────────── 1. build image ─────────────────────────────
if want 1; then
  gate "STEP 1 — Build & push the backend image with Cloud Build?"
  step "1 — Cloud Build (context = repo root)"
  gcloud builds submit "$REPO_ROOT" \
    --project="$PROJECT_ID" \
    --config=cloudbuild.yaml \
    --substitutions=_IMAGE_URI="$IMAGE_URI"
  ok "Image built & pushed: ${IMAGE_URI}"
fi

# ───────────────────────────── 1b. secret IAM ─────────────────────────────
if want 1b; then
  gate "STEP 1b — Grant the runtime SA secretAccessor on every secret?"
  step "1b — Grant ${RUNTIME_SA} access to all secrets (idempotent)"
  for SECRET in $(gcloud secrets list --project="$PROJECT_ID" --format="value(name)"); do
    gcloud secrets add-iam-policy-binding "$SECRET" \
      --project="$PROJECT_ID" \
      --member="serviceAccount:${RUNTIME_SA}" \
      --role="roles/secretmanager.secretAccessor"
  done
  ok "Runtime SA can read all mounted secrets."
fi

# ───────────────────────────── 2. deploy Cloud Run ─────────────────────────────
if want 2; then
  gate "STEP 2 — Deploy the new Cloud Run revision to ${API_SERVICE_PROD}?"
  step "2 — Deploy Cloud Run revision"
  gcloud run deploy "$API_SERVICE_PROD" \
    --project="$PROJECT_ID" --region="$REGION" \
    --image="$IMAGE_URI" \
    --platform=managed --service-account="$RUNTIME_SA" \
    --allow-unauthenticated --port=8080 \
    --memory=1Gi --cpu=1 --timeout=3600 --concurrency=80 \
    --min-instances=0 --max-instances=10 \
    --set-env-vars="$env_vars" --set-secrets="$SECRETS"
  ok "Cloud Run revision deployed."
fi

# ───────────────────────────── 2b. public invoker (Firebase Hosting rewrites) ─────────────────────────────
# Firebase Hosting rewrites reach Cloud Run as ANONYMOUS requests, so the service must allow
# allUsers invoke. Step 2's `--allow-unauthenticated` already grants that when the org policy
# permits allUsers (yours is allowAll: true), so this step is usually a no-op verification.
# NOTE: the Firebase Hosting *service agent* binding is only for PRIVATE services and that agent
# may not even exist yet — that's the "service account ... does not exist" error. We ensure
# public invoke instead. This whole step is best-effort and never aborts the deploy.
if want 2b; then
  gate "STEP 2b — Verify ${API_SERVICE_PROD} is publicly invokable (for Hosting rewrites)?"
  step "2b — Public invoker check"
  if gcloud run services get-iam-policy "$API_SERVICE_PROD" \
       --region="$REGION" --project="$PROJECT_ID" 2>/dev/null | grep -q "allUsers"; then
    ok "Service already allows allUsers invoke — Hosting rewrites will work. Nothing to do."
  else
    echo "Service is not public yet; granting allUsers run.invoker…"
    if gcloud run services add-iam-policy-binding "$API_SERVICE_PROD" \
         --region="$REGION" --project="$PROJECT_ID" \
         --member=allUsers --role=roles/run.invoker; then
      ok "Granted public invoker."
    else
      echo "⚠️  allUsers binding failed; falling back to --no-invoker-iam-check…"
      gcloud run services update "$API_SERVICE_PROD" \
        --region="$REGION" --project="$PROJECT_ID" --no-invoker-iam-check \
        && ok "Invoker IAM check disabled — Hosting rewrites will work." \
        || echo "⚠️  Manual action needed: make ${API_SERVICE_PROD} publicly invokable."
    fi
  fi
fi

# ───────────────────────────── 3. frontend → Hosting ─────────────────────────────
# VITE_PYTHON_URL must go through Firebase Hosting (same origin) so the Hosting rewrites
# forward API calls to Cloud Run with proper OIDC auth. Do NOT set it to the Cloud Run URL
# directly — that would bypass Hosting and hit CORS/auth errors.
# VITE_DEMO_ENABLED must NOT be set here — demo mode is detected by hostname (demo.herofy.ai)
# at runtime. Setting it in the build would force demo mode on every host.
if want 3; then
  gate "STEP 3 — Build the frontend and deploy it to Firebase Hosting?"
  step "3 — Build frontend & deploy Hosting"
  cat > frontend/.env.production << 'EOF'
VITE_PYTHON_URL=https://herofy.ai
EOF
  ( cd frontend && npm run build )
  firebase deploy --only hosting --project "$PROJECT_ID"
  ok "Frontend deployed to Hosting."
fi

step "🎉 Production deploy complete"
echo "  Backend : https://console.cloud.google.com/run/detail/${REGION}/${API_SERVICE_PROD}?project=${PROJECT_ID}"
echo "  Frontend: ${APP_URL_PROD}  (and https://${PROJECT_ID}.web.app)"
