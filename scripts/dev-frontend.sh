#!/usr/bin/env bash
# Start the Herofy Vite frontend with env setup and dependency checks.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

parse_dev_flags "$@"

cd "${HEROFY_ROOT}"

log_info "Herofy frontend startup"
echo ""

use_node_version 20
npm_install_if_needed

ensure_env_file \
  "${HEROFY_ROOT}/frontend/.env" \
  "${HEROFY_ROOT}/frontend/.env.example" \
  "frontend/.env"

# Vite loads frontend/.env automatically (see vite.config.ts)
#VITE_PYTHON_URL=ttps://herofy-api-staging-gzw7mkdv7q-uc.a.run.app

VITE_PYTHON_URL="http://localhost:8081"
VITE_USE_EMULATOR="false"
if [[ -f "${HEROFY_ROOT}/frontend/.env" ]]; then
  py_url="$(grep -E '^VITE_PYTHON_URL=' "${HEROFY_ROOT}/frontend/.env" | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'" || true)"
  use_emu="$(grep -E '^VITE_USE_EMULATOR=' "${HEROFY_ROOT}/frontend/.env" | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'" || true)"
  [[ -n "$py_url" ]] && VITE_PYTHON_URL="$py_url"
  [[ -n "$use_emu" ]] && VITE_USE_EMULATOR="$use_emu"
fi

if [[ ! -d "${HEROFY_ROOT}/frontend/src/dataconnect-generated" ]]; then
  log_warn "dataconnect-generated SDK missing. Generate with:"
  log_warn "  firebase dataconnect:sdk:generate --project herofy-496505"
fi

check_firebase_cli_optional

echo ""
log_info "Starting Vite on http://localhost:3000"
log_info "Python backend expected at ${VITE_PYTHON_URL}"
if [[ "${VITE_USE_EMULATOR}" == "true" ]]; then
  log_info "Data Connect emulator mode enabled (localhost:9399)"
else
  log_warn "Using production Data Connect — set VITE_USE_EMULATOR=true in frontend/.env for local emulator"
fi
echo ""

cd "${HEROFY_ROOT}/frontend"
exec npm run dev
