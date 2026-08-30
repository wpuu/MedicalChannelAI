#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
APP_DIR="${MCAI_APP_DIR:-/srv/medical/app}"
WEB_DIR="${MCAI_WEB_DIR:-/srv/medical/web}"

case "${MODE}" in
  demo)
    API_BASE=""
    ;;
  pilot)
    API_BASE="/api"
    ;;
  *)
    echo "usage: bash $0 demo|pilot" >&2
    exit 2
    ;;
esac

cd "${APP_DIR}/web"
npm ci
npx tsc --noEmit

VITE_BUILD_MODE="${MODE}" VITE_API_BASE_URL="${API_BASE}" npm run build

mkdir -p "${WEB_DIR}"
rsync -a --delete dist/ "${WEB_DIR}/"

echo "H5 deployed in ${MODE} mode to ${WEB_DIR}"
if [[ "${MODE}" == "demo" ]]; then
  echo "Demo mode: VITE_BUILD_MODE=demo, synthetic/local Mock data, no real API login."
else
  echo "Pilot mode: VITE_BUILD_MODE=pilot, same-origin API required at /api."
fi
