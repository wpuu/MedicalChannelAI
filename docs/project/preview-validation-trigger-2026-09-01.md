# Preview validation trigger — 2026-09-01

Purpose: request one fresh Preview build for the current M1 branch after the prior Hobby build-rate-limit block.

This commit changes no product behavior, no public procurement facts, and no deployment target. It does not merge `main` and does not promote production.

Validation target:

- current pipeline regression suite
- verified snapshot checks
- runtime status checks
- AI boundary checks
- TypeScript `tsc --noEmit`
- Vite production build
- packaging of `/api/public-snapshot`, `/api/ai/analyze`, and `/api/status`

AI credentials remain runtime-only and must never be committed to the repository.
