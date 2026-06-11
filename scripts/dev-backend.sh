#!/usr/bin/env bash
# Start the Herofy Python backend with env setup and dependency checks.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

parse_dev_flags "$@"

cd "${HEROFY_ROOT}"

log_info "Herofy backend startup"
echo ""

# Environment file
ensure_env_file \
  "${HEROFY_ROOT}/backend/.env" \
  "${HEROFY_ROOT}/backend/.env.example" \
  "backend/.env"

# Pydantic loads backend/.env from the working directory (see config.py)
python_install_if_needed

warn_empty_env_var "${HEROFY_ROOT}/backend/.env" "GEMINI_API_KEY" "GEMINI_API_KEY"
check_postgres_optional
check_firebase_cli_optional

echo ""
PORT="${PORT:-8081}"
if [[ -f "${HEROFY_ROOT}/backend/.env" ]]; then
  # Read PORT without sourcing (avoids breaking on $ in secrets)
  port_from_env="$(grep -E '^PORT=' "${HEROFY_ROOT}/backend/.env" | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'" || true)"
  [[ -n "$port_from_env" ]] && PORT="$port_from_env"
fi

log_info "Starting uvicorn on http://localhost:${PORT}"
log_info "API docs: http://localhost:${PORT}/docs"
echo ""

cd "${HEROFY_ROOT}/backend"
exec uvicorn main:app --reload --host 0.0.0.0 --port "${PORT}"
