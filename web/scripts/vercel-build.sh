#!/usr/bin/env bash
set -euo pipefail

# GitHub Actions currently fails before runner assignment. For the Pilot development
# branch only, use Vercel's already-working build environment as an independent
# execution gate for the deterministic Python suite. Production/main static Demo
# builds do not depend on backend source files and therefore skip this step.
if [[ "${VERCEL_GIT_COMMIT_REF:-}" == "dev/tianjin-pilot-v0.1" ]]; then
  echo "[pilot-verify] running deterministic Python tests"
  command -v python3 >/dev/null 2>&1 || {
    echo "[pilot-verify] python3 is required on the Vercel build image" >&2
    exit 1
  }
  (
    cd ..
    python3 -m unittest discover -s tools/medical_pilot -t . -p 'test_*.py'

    # This marker is committed only for a deliberate one-shot network validation and
    # removed immediately afterwards. The SQLite database lives in Vercel /tmp and
    # never contains customer context or credentials.
    if [[ -f deploy/.verify-live-bootstrap-once ]]; then
      echo "[pilot-live-bootstrap] verifying registered official URLs against isolated temporary SQLite"
      live_db="/tmp/medicalchannelai-live-bootstrap-${VERCEL_GIT_COMMIT_SHA:-manual}.sqlite"
      rm -f "${live_db}" "${live_db}-wal" "${live_db}-shm"
      python3 -m tools.medical_pilot.pilot_live_seed \
        --db "${live_db}" \
        --manifest deploy/tianjin-pilot-bootstrap-urls-2026-08-30.json
      rm -f "${live_db}" "${live_db}-wal" "${live_db}-shm"
    fi
  )
fi

echo "[web] running TypeScript check"
npx tsc --noEmit

echo "[web] building Vite bundle"
npx vite build
