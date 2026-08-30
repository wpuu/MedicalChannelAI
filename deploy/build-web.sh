#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
APP_DIR="${MCAI_APP_DIR:-/srv/medical/app}"
WEB_DIR="${MCAI_WEB_DIR:-/srv/medical/web}"
DEMO_MAX_DIST_KB="${MCAI_DEMO_MAX_DIST_KB:-3072}"

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
  # Plain evidence URLs may exist in JS data; only executable/style dependencies
  # are rejected here.
  if grep -niE '<(script|link)[^>]+(src|href)="https?://' dist/index.html; then
    echo "ERROR: demo index.html contains external runtime script/style dependency" >&2
    exit 3
  fi

  if find dist -type f -name '*.css' -print0 | xargs -0 -r grep -niE '(@import[^;]*https?://|url\([[:space:]]*https?://)'; then
    echo "ERROR: demo CSS contains external runtime dependency" >&2
    exit 3
  fi

  DIST_KB="$(du -sk dist | awk '{print $1}')"
  if (( DIST_KB > DEMO_MAX_DIST_KB )); then
    echo "ERROR: demo dist is ${DIST_KB} KiB, over mainland-access budget ${DEMO_MAX_DIST_KB} KiB" >&2
    exit 4
  fi
  echo "Demo dist size: ${DIST_KB} KiB / ${DEMO_MAX_DIST_KB} KiB budget"
fi

mkdir -p "${WEB_DIR}"
find "${WEB_DIR}" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
cp -a dist/. "${WEB_DIR}/"

echo "H5 deployed in ${MODE} mode to ${WEB_DIR}"
if [[ "${MODE}" == "demo" ]]; then
  echo "Demo mode: synthetic/local Mock data, no real API login, no external runtime script/style dependency, size budget enforced."
else
  echo "Pilot mode: VITE_BUILD_MODE=pilot, same-origin API required at /api."
fi
