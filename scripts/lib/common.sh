#!/usr/bin/env bash
# Shared helpers for Herofy dev startup scripts.

set -euo pipefail

HEROFY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export HEROFY_ROOT

# Colors (disabled when not a tty)
if [[ -t 1 ]]; then
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  BLUE='\033[0;34m'
  NC='\033[0m'
else
  RED='' GREEN='' YELLOW='' BLUE='' NC=''
fi

log_info()  { printf "${BLUE}→${NC} %s\n" "$*"; }
log_ok()    { printf "${GREEN}✓${NC} %s\n" "$*"; }
log_warn()  { printf "${YELLOW}!${NC} %s\n" "$*" >&2; }
log_error() { printf "${RED}✗${NC} %s\n" "$*" >&2; }

die() {
  log_error "$1"
  exit "${2:-1}"
}

require_cmd() {
  local cmd="$1"
  local hint="${2:-}"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    die "Required command not found: ${cmd}${hint:+ — $hint}"
  fi
}

# Load nvm when available (respects .nvmrc in repo root)
use_node_version() {
  local min_major="${1:-20}"
  if [[ -s "${HOME}/.nvm/nvm.sh" ]]; then
    # shellcheck source=/dev/null
    source "${HOME}/.nvm/nvm.sh"
    if [[ -f "${HEROFY_ROOT}/.nvmrc" ]]; then
      nvm use --silent 2>/dev/null || nvm install --silent
    fi
  fi

  require_cmd node "Install Node.js ${min_major}+ (https://nodejs.org or: nvm install ${min_major})"

  local version major
  version="$(node -p "process.versions.node")"
  major="${version%%.*}"
  if (( major < min_major )); then
    die "Node.js ${min_major}+ required (found v${version}). Run: nvm use"
  fi
  log_ok "Node.js v${version}"
}

# Require Python 3.12+
use_python_version() {
  local min_minor=12
  local python=""
  local candidates=(python3.13 python3.12 python3 python)
  # Homebrew / framework installs on macOS
  for ver in 13 12; do
    candidates+=("/opt/homebrew/bin/python3.${ver}" "/usr/local/bin/python3.${ver}")
    candidates+=("/Library/Frameworks/Python.framework/Versions/3.${ver}/bin/python3.${ver}")
  done

  for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1; then
      local py_ver minor
      py_ver="$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
      [[ -z "$py_ver" ]] && continue
      minor="${py_ver#*.}"
      if [[ "${py_ver%%.*}" -eq 3 ]] && (( minor >= min_minor )); then
        python="$candidate"
        break
      fi
    fi
  done

  if [[ -z "$python" ]]; then
    die "Python 3.${min_minor}+ required. Try: pyenv install 3.12 && pyenv local 3.12"
  fi
  export HEROFY_PYTHON="$python"
  log_ok "Python $($python --version 2>&1 | awk '{print $2}') ($python)"
}

ensure_env_file() {
  local target="$1"
  local example="$2"
  local label="${3:-$(basename "$target")}"

  if [[ -f "$target" ]]; then
    log_ok "${label} exists"
    return 0
  fi

  if [[ ! -f "$example" ]]; then
    log_warn "No ${label} and no ${example} template — create ${target} manually"
    return 0
  fi

  cp "$example" "$target"
  log_warn "Created ${target} from template — edit secrets (API keys) before production use"
}

needs_npm_install() {
  [[ "${HEROFY_SKIP_INSTALL:-}" == "1" ]] && return 1
  [[ ! -d "${HEROFY_ROOT}/node_modules" ]] && return 0
  [[ ! -f "${HEROFY_ROOT}/node_modules/.herofy-install-stamp" ]] && return 0
  [[ "${HEROFY_ROOT}/package-lock.json" -nt "${HEROFY_ROOT}/node_modules/.herofy-install-stamp" ]] && return 0
  return 1
}

npm_install_if_needed() {
  cd "${HEROFY_ROOT}"
  if needs_npm_install; then
    log_info "Installing npm dependencies (package-lock changed or node_modules missing)..."
    npm install
    touch node_modules/.herofy-install-stamp
    log_ok "npm dependencies up to date"
  else
    log_ok "npm dependencies already installed"
  fi
}

needs_python_install() {
  [[ "${HEROFY_SKIP_INSTALL:-}" == "1" ]] && return 1
  local venv="${HEROFY_ROOT}/backend/.venv"
  [[ ! -d "$venv" ]] && return 0
  [[ ! -f "${venv}/.herofy-install-stamp" ]] && return 0
  local trigger="${HEROFY_ROOT}/backend/requirements.txt"
  [[ -f "${HEROFY_ROOT}/backend/pyproject.toml" ]] && trigger="${HEROFY_ROOT}/backend/pyproject.toml"
  [[ "$trigger" -nt "${venv}/.herofy-install-stamp" ]] && return 0
  return 1
}

ensure_python_venv() {
  local venv="${HEROFY_ROOT}/backend/.venv"
  use_python_version

  if [[ ! -d "$venv" ]]; then
    log_info "Creating Python virtualenv at backend/.venv..."
    "$HEROFY_PYTHON" -m venv "$venv"
  fi

  # shellcheck source=/dev/null
  source "${venv}/bin/activate"
  export VIRTUAL_ENV="$venv"
  export PATH="${venv}/bin:${PATH}"
  log_ok "Virtualenv active"
}

python_install_if_needed() {
  ensure_python_venv
  if ! needs_python_install; then
    log_ok "Python dependencies already installed"
    return 0
  fi

  log_info "Installing Python dependencies..."
  python -m pip install --upgrade pip --quiet

  if command -v poetry >/dev/null 2>&1 && [[ -f "${HEROFY_ROOT}/backend/pyproject.toml" ]]; then
    (cd "${HEROFY_ROOT}/backend" && poetry install --no-interaction --no-ansi)
  else
    python -m pip install -r "${HEROFY_ROOT}/backend/requirements.txt" --quiet
  fi

  touch "${HEROFY_ROOT}/backend/.venv/.herofy-install-stamp"
  log_ok "Python dependencies up to date"
}

warn_empty_env_var() {
  local file="$1"
  local var="$2"
  local label="${3:-$var}"
  if [[ -f "$file" ]] && grep -q "^${var}=" "$file" 2>/dev/null; then
    local val
    val="$(grep "^${var}=" "$file" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
    if [[ -z "$val" || "$val" == *"your-"* || "$val" == *"MY_"* ]]; then
      log_warn "${label} is not set in ${file} — some AI/agent features will be limited"
    fi
  fi
}

check_postgres_optional() {
  if command -v docker >/dev/null 2>&1; then
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^herofy-db$'; then
      log_ok "PostgreSQL container (herofy-db) is running"
      return 0
    fi
    log_warn "PostgreSQL container not running. Start with: npm run db:up"
    return 0
  fi
  log_warn "Docker not found — skip db:up or run Postgres yourself on localhost:5432"
}

check_firebase_cli_optional() {
  if command -v firebase >/dev/null 2>&1; then
    log_ok "Firebase CLI available"
    return 0
  fi
  log_warn "Firebase CLI not installed — needed for Data Connect emulator. Run: npm install -g firebase-tools"
}

parse_dev_flags() {
  HEROFY_SKIP_INSTALL="${HEROFY_SKIP_INSTALL:-0}"
  for arg in "$@"; do
    case "$arg" in
      --skip-install) HEROFY_SKIP_INSTALL=1 ;;
      -h|--help)
        echo "Usage: $0 [--skip-install]"
        echo "  --skip-install  Skip npm/pip install checks (faster restarts)"
        exit 0
        ;;
    esac
  done
  export HEROFY_SKIP_INSTALL
}
