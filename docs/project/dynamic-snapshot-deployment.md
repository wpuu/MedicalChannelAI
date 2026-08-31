# Dynamic verified snapshot deployment

Status: **implemented, not configured by default**.

This contract separates medical-opportunity data refresh from frontend code deployment. It does not change the evidence-first rule: only a snapshot that passed the pipeline validation gates may be published.

## Data flow

```text
Official sources
  -> evidence pipeline
  -> canonical VERIFIED records
  -> today-actions.public.json
  -> optional HTTPS publisher
  -> public read-only snapshot URL
  -> /api/public-snapshot
  -> browser + /api/ai/analyze
```

The browser and the AI function must consume the same verified snapshot version.

## Configuration roles

### GitHub Actions secrets

`VERIFIED_SNAPSHOT_PUBLISH_URL`

- HTTPS upload endpoint used only by the refresh workflow.
- Expected method: `PUT`.
- May be a pre-signed object-storage upload URL.
- May contain sensitive query parameters. Never expose it to browser code or a `VITE_*` variable.

`VERIFIED_SNAPSHOT_PUBLISH_TOKEN` (optional)

- Optional Bearer token added by `pipeline/scripts/publish_snapshot_http.py`.
- Leave empty when the publish URL is already pre-signed.

### Vercel server environment

`VERIFIED_SNAPSHOT_URL`

- HTTPS **read-only** URL for the published public snapshot.
- Used by `/api/public-snapshot` and `/api/ai/analyze` on the server.
- It should not grant write access.
- If this URL is configured but unavailable or invalid, the server fails closed instead of silently returning the bundled snapshot.

### Browser override

`VITE_VERIFIED_SNAPSHOT_URL`

- Intended only for controlled local/testing scenarios.
- Production should normally use same-origin `/api/public-snapshot` so browser CORS and snapshot-version drift are avoided.
- Never place a pre-signed upload URL or write credential here.

## Publisher behavior

`pipeline/scripts/publish_snapshot_http.py`:

- accepts only HTTPS publish URLs;
- rejects URL-embedded username/password userinfo;
- accepts only `PUT` or `POST`;
- validates the basic public snapshot contract before network I/O;
- rejects payloads larger than 5 MiB;
- sends `Content-Type: application/json`;
- sends `X-Content-SHA256` for integrity/audit correlation;
- optionally sends `Authorization: Bearer <token>`;
- does not follow redirects;
- treats non-2xx or network failure as a failed publish;
- does not print the full publish URL or Bearer token.

The scheduled workflow publishes externally only after the generated snapshot passes pipeline tests. If no publish URL is configured, the external step is skipped and the existing Git-backed snapshot flow remains unchanged.

## Safe activation sequence

1. Provision a storage object or endpoint that supports HTTPS upload and public/read-only HTTPS GET.
2. Configure GitHub `VERIFIED_SNAPSHOT_PUBLISH_URL` and optional `VERIFIED_SNAPSHOT_PUBLISH_TOKEN`.
3. Run one refresh and verify the external object contents/hash.
4. Configure Vercel server-only `VERIFIED_SNAPSHOT_URL` to the read-only GET URL.
5. Verify `/api/public-snapshot` returns the remote snapshot and that `/api/ai/analyze` resolves the same `snapshot_as_of`.
6. Verify remote-source failure returns an explicit unavailable error rather than bundled stale data.
7. Only after steps 1-6 are proven should Vercel builds for pure `data: refresh Tianjin verified opportunities` commits be skipped.

## Important build rule

Do **not** skip Vercel builds for data-only commits while `VERIFIED_SNAPSHOT_URL` is not configured and proven.

Without the remote read path, production still depends on the bundled `web/public/data/today-actions.public.json`; skipping a data-only build in that state would leave production stale.

## Current state

- Remote read support: implemented.
- Same-origin public snapshot API: implemented.
- Optional HTTPS publish support: implemented.
- Publisher unit tests: local PASS (5 tests, 2026-08-31).
- External storage: not claimed configured.
- GitHub scheduled runtime: not active until workflow exists on the default branch and a runner completes it.
- Production promotion: not approved; `main` remains unchanged.
