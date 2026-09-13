# Dynamic verified snapshot deployment

Status: **implemented in Preview candidate, Production configuration not approved**.

This contract separates medical-opportunity data refresh from frontend/code deployment. It does not change the evidence-first rule: only a public snapshot that passes the existing VERIFIED validation gates may enter the product data plane.

## Supported data planes

### A. Bundled Git snapshot

```text
Official sources
  -> evidence pipeline
  -> canonical VERIFIED records
  -> today-actions.public.json
  -> Git commit
  -> Vercel deployment
  -> bundled fallback snapshot
```

This remains the rollback-safe baseline embedded in every deployment.

### B. Same-origin Vercel Runtime Cache publish lane (preferred for gated Production)

```text
Official sources
  -> evidence pipeline
  -> canonical VERIFIED records
  -> combined Tianjin + regional today-actions.public.json
  -> authenticated HTTPS PUT /api/public-snapshot
  -> validated Production Runtime Cache
  -> HTTPS GET /api/public-snapshot readback
  -> round-trip verifier
  -> browser + /api/ai/analyze
```

The stable published cache key is separate from both the exact bundled-revision cache and the Vercel-native collector's legacy Tianjin-only cache key. A published Runtime Cache snapshot may override the bundle only when it passes the full public VERIFIED contract and has a strictly newer `snapshot_as_of`. Older, conflicting, invalid, oversized, or implausibly future snapshots fail closed.

Vercel Runtime Cache is isolated by project and deployment environment, so Preview and Production do not share this published snapshot state.

### C. External read-only snapshot

The existing `VERIFIED_SNAPSHOT_URL` path remains supported for a separately hosted HTTPS snapshot object. If configured, this remote read path has priority and fails closed when unavailable or invalid.

## GitHub Actions secrets

`VERIFIED_SNAPSHOT_PUBLISH_URL`

- HTTPS upload endpoint used only by refresh workflows.
- Expected method: `PUT`.
- For same-origin mode, set this to the Production `/api/public-snapshot` endpoint only after Production activation is explicitly approved.
- It may alternatively be a pre-signed external object-storage upload URL.
- Never expose a sensitive publish URL to browser code or a `VITE_*` variable.

`VERIFIED_SNAPSHOT_PUBLISH_TOKEN`

- Bearer token added by `pipeline/scripts/publish_snapshot_http.py`.
- Required for the same-origin Runtime Cache endpoint.
- The same strong value must exist as the Vercel server-only `VERIFIED_SNAPSHOT_PUBLISH_TOKEN` and the GitHub Actions secret.
- It may be omitted only when an external publish URL already carries its own write authorization, such as a pre-signed object URL.

`VERIFIED_SNAPSHOT_READ_URL`

- Required whenever `VERIFIED_SNAPSHOT_PUBLISH_URL` is configured.
- HTTPS read-only URL used immediately after upload.
- In same-origin mode this is the same Production `/api/public-snapshot` URL, but without write credentials.
- The workflow retries readback up to three times and fails closed if critical snapshot identity differs.

Both the Tianjin refresh and the later regional refresh perform this optional publish/readback step. `publish_web_snapshot.py` automatically includes `regional_live_ccgp_records.json` when present, so the externally published artifact is the combined Tianjin + regional public snapshot rather than a Tianjin-only payload. The regional refresh at 08:50 Beijing time is the later daily reconciliation and republishes after regional data has been refreshed.

## Vercel server environment

`VERIFIED_SNAPSHOT_PUBLISH_TOKEN`

- Server-only secret protecting PUT/POST on `/api/public-snapshot`.
- Missing/short configuration disables writes; unauthorized writes return 401.
- Never expose it through `VITE_*` variables.

`VERIFIED_SNAPSHOT_URL`

- Optional HTTPS read-only URL for mode C.
- Do **not** point this variable at the same deployment's `/api/public-snapshot`; that would create a recursive read path.
- If configured but unavailable or invalid, the server fails closed instead of silently substituting stale remote data.

### Browser override

`VITE_VERIFIED_SNAPSHOT_URL` is only for controlled local/testing scenarios. Production should normally keep the browser on same-origin APIs. Never place a write credential here.

## Same-origin publish endpoint contract

`/api/public-snapshot`:

- `GET`: returns the currently accepted verified public snapshot and is `no-store` so immediate post-publish readback cannot be hidden by CDN cache;
- `PUT` / `POST`: requires `Authorization: Bearer <VERIFIED_SNAPSHOT_PUBLISH_TOKEN>`;
- missing server publish configuration fails closed;
- validates the same public VERIFIED schema, evidence, private-context boundary and zero-config ranking contract used by normal reads;
- rejects payloads above the Runtime Cache safety limit;
- rejects snapshots older than the deployment bundle;
- rejects rollback relative to an already-published runtime snapshot;
- rejects a different payload using the same `snapshot_as_of`;
- rejects timestamps beyond the allowed future-skew window;
- validates Runtime Cache readback before returning success.

The Vercel-native collector key `medicalchannelai:verified-snapshot:latest:v1` is intentionally **not** consumed by this product snapshot reader because that collector currently covers Tianjin sources only. The multi-region product snapshot uses the separate authenticated published key.

## Publisher and round-trip verifier

`pipeline/scripts/publish_snapshot_http.py`:

- accepts only HTTPS publish URLs;
- rejects URL-embedded username/password userinfo;
- accepts only `PUT` or `POST`;
- validates the basic public snapshot contract before network I/O;
- rejects payloads larger than 5 MiB;
- sends `Content-Type: application/json`, `X-Content-SHA256`, and optional Bearer authorization;
- does not follow redirects;
- treats non-2xx/network failure as failed publication;
- does not print the full publish URL or Bearer token.

`pipeline/scripts/verify_snapshot_roundtrip.py` reads the snapshot back through the separate read URL and compares:

- `snapshot_as_of`;
- Top 5 opportunity IDs and order;
- full `opportunity_pool` IDs and order;
- `card_count`;
- `matched_count`;
- `opportunity_pool_count`.

It also records local/remote SHA256 and byte identity. A configured publisher without a valid readback path fails closed.

## Safe Production activation sequence

Production activation remains an explicit release action, not a consequence of this PR being merged.

1. Keep PR acceptance on Preview and confirm Full Verify and exact-head Vercel Preview are green.
2. Generate one strong publish token.
3. Only after explicit Production authorization, configure the token as a Vercel Production server variable and as the GitHub Actions `VERIFIED_SNAPSHOT_PUBLISH_TOKEN` secret.
4. Configure GitHub `VERIFIED_SNAPSHOT_PUBLISH_URL` and `VERIFIED_SNAPSHOT_READ_URL` to the Production `/api/public-snapshot` endpoint.
5. Promote/deploy the exact accepted code release through the controlled Production gate.
6. Publish one already-verified combined snapshot and require round-trip verification to pass.
7. Confirm Production `/api/status` and `/api/public-snapshot` report the accepted `snapshot_as_of`, Top 5, and full pool counts.
8. Confirm a deliberately unauthenticated write is rejected and normal GET remains available.
9. Leave `main` Git auto-deployment disabled; future verified data updates travel through the authenticated data lane rather than redeploying code.

Until steps 2-8 are explicitly authorized and proven, Production configuration must remain untouched.

## Important release rule

`web/vercel.json` disables automatic Git deployments from `main` in the release candidate. That is safe as a permanent code-release gate only when mode B or C has been activated and round-trip verified in Production. Before that activation, the existing Production deployment can still depend on its bundled snapshot and may become stale; this is therefore a release blocker rather than a reason to silently change Production settings.

## Current state

- Combined Tianjin + regional public snapshot generation: implemented.
- Bundled rollback-safe snapshot: implemented.
- Same-origin authenticated Runtime Cache publish/read lane: implemented in Preview candidate.
- Tianjin and regional optional HTTPS publish/readback workflows: implemented in Preview candidate.
- External read-only snapshot mode: implemented.
- Production publish token / URLs: **not configured by this acceptance work**.
- Production promotion: **not approved**.
- `main`: remains unchanged by this acceptance work.
