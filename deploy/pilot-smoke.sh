#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-}"
if [[ -z "${BASE_URL}" ]]; then
  echo "usage: $0 https://pilot-domain" >&2
  exit 2
fi
BASE_URL="${BASE_URL%/}"

TMP_BODY="$(mktemp)"
trap 'rm -f "${TMP_BODY}"' EXIT

printf '[1/3] healthz... '
curl --fail --silent --show-error --max-time 10 "${BASE_URL}/api/healthz" >"${TMP_BODY}"
python3 - "${TMP_BODY}" <<'PY'
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8') as fh:
    value = json.load(fh)
expected = {"schema_version": "0.1", "status": "ok", "mode": "SINGLE_HOST_PILOT"}
if value != expected:
    raise SystemExit(f"unexpected health response: {value!r}")
PY
echo OK

printf '[2/3] H5 SPA... '
curl --fail --silent --show-error --max-time 10 "${BASE_URL}/today" >"${TMP_BODY}"
if ! grep -Eqi '<div[^>]+id=["'"']root["'"']' "${TMP_BODY}"; then
  echo "FAILED: /today did not return the H5 index" >&2
  exit 1
fi
echo OK

printf '[3/3] unauthenticated API boundary... '
HTTP_CODE="$(curl --silent --show-error --max-time 10 -o /dev/null -w '%{http_code}' "${BASE_URL}/api/today")"
if [[ "${HTTP_CODE}" != "401" ]]; then
  echo "FAILED: expected /api/today without session to be 401, got ${HTTP_CODE}" >&2
  exit 1
fi
echo OK

echo "Public Pilot smoke passed. Authenticated business smoke is still required separately."
