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

if [[ "${MODE}" == "demo" ]]; then
  # Mainland-China business Demo must not depend on third-party runtime assets.
  # Evidence URLs may exist as plain application data, so only executable/style
  # dependency patterns are blocked here.
  if grep -RniE \
    '(<script[^>]+src=["'"']https?://|<link[^>]+href=["'"']https?://|@import[[:space:]]+(url\()?['"'"']?https?://)' \
    dist; then
    echo "ERROR: demo build contains external runtime script/style dependency" >&2
    exit 3
  fi
fi

mkdir -p "${WEB_DIR}"
find "${WEB_DIR}" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
cp -a dist/. "${WEB_DIR}/"

echo "H5 deployed in ${MODE} mode to ${WEB_DIR}"
if [[ "${MODE}" == "demo" ]]; then
  echo "Demo mode: VITE_BUILD_MODE=demo, synthetic/local Mock data, no real API login, no external runtime script/style dependency."
else
  echo "Pilot mode: VITE_BUILD_MODE=pilot, same-origin API required at /api."
fi
