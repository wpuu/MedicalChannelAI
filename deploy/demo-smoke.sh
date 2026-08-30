#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${MCAI_DOMAIN:-medicalai.qd.je}"
BASE="https://${DOMAIN}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

INDEX_HEADERS="${TMP_DIR}/index.headers"
INDEX_BODY="${TMP_DIR}/index.html"

curl --fail --silent --show-error \
  --connect-timeout 10 --max-time 30 \
  -D "${INDEX_HEADERS}" -o "${INDEX_BODY}" "${BASE}/"

grep -qi '^x-robots-tag:.*noindex' "${INDEX_HEADERS}" || {
  echo "ERROR: missing X-Robots-Tag noindex" >&2
  exit 10
}

grep -q '<div id="root"></div>' "${INDEX_BODY}" || {
  echo "ERROR: H5 root element missing" >&2
  exit 11
}

ASSET_PATH="$(sed -nE 's#.*<script[^>]+src="(/assets/[^"]+)".*#\1#p' "${INDEX_BODY}" | head -n 1)"
if [[ -z "${ASSET_PATH}" ]]; then
  echo "ERROR: built JS asset not found in index.html" >&2
  exit 12
fi

curl --fail --silent --show-error \
  --connect-timeout 10 --max-time 30 \
  -o /dev/null "${BASE}${ASSET_PATH}"

# SPA deep links must return the H5 shell rather than a server-side 404.
curl --fail --silent --show-error \
  --connect-timeout 10 --max-time 30 \
  -o "${TMP_DIR}/deep.html" "${BASE}/today"
grep -q '<div id="root"></div>' "${TMP_DIR}/deep.html" || {
  echo "ERROR: SPA deep-link fallback failed" >&2
  exit 13
}

ROBOTS="$(curl --fail --silent --show-error --connect-timeout 10 --max-time 30 "${BASE}/robots.txt")"
printf '%s' "${ROBOTS}" | grep -qi 'Disallow:[[:space:]]*/' || {
  echo "ERROR: robots.txt does not disallow indexing" >&2
  exit 14
}

API_STATUS="$(curl --silent --show-error --connect-timeout 10 --max-time 30 \
  -o /dev/null -w '%{http_code}' "${BASE}/api/healthz")"
if [[ "${API_STATUS}" != "404" ]]; then
  echo "ERROR: static Demo must return 404 for /api/*, got ${API_STATUS}" >&2
  exit 15
fi

printf 'PASS: static Demo smoke %s\n' "${BASE}"
printf 'PASS: HTTPS / H5 shell / JS asset / SPA fallback / noindex / API isolation\n'
