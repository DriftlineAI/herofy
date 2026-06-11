#Clean frontend environement
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

parse_dev_flags "$@"

cd "${HEROFY_ROOT}"

log_info "Herofy cleanup startup"

log_info "========== Remove ${HEROFY_ROOT}/shared and cache"
rm -rf shared/node_modules
log_info "========== Remove ${HEROFY_ROOT}/frontend and cache"
rm -rf frontend/node_modules
log_info "========== Remove ${HEROFY_ROOT}/node_modules and cache"
rm -rf node_modules

npm cache clean --force
#npm install