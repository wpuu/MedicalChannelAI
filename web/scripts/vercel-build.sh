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
  )
fi

echo "[web] running TypeScript check"
npx tsc --noEmit

echo "[web] building Vite bundle"
npx vite build
