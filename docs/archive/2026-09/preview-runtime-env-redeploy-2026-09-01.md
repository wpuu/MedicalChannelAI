# Preview runtime env redeploy trigger — 2026-09-01

Purpose: trigger a fresh Vercel Preview deployment after the product owner configured `AGNES_API_KEYS` in the Preview environment.

No credential values are stored in this repository.

Validation required after deployment:
- `/api/status` reports `ai.configured=true`.
- One same-origin `POST /api/ai/analyze` succeeds for a VERIFIED open opportunity.
- Response remains grounded in server-owned VERIFIED public facts and does not expose provider credentials or internal routing details.
- Latest Preview remains `production_ready=false` until explicit owner approval.
