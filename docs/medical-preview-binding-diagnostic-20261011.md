# Approved Preview database binding diagnostic

This independent test branch is based on frozen candidate
`69082cbc058704a330a1cea68d0514a2f5971c45`. It is for Preview deployment and
read-only binding inspection only. Do not merge it into main or deploy it to
production. The original candidate, build and earlier evidence remain separate.

## Diagnostic changes relative to the candidate

- Add `GET /api/preview-binding`, with a core that requires the exact approved
  Preview branch and a full deployed commit SHA before opening a connection.
- Use the existing `DATABASE_URL || POSTGRES_URL` precedence without importing
  schema initialization or business services. Open a short connection using the
  existing postgres dependency, default read-only sessions and `BEGIN READ ONLY`.
- Execute only the boolean comparison `current_database() = 'neondb'` and the
  boolean read-only transaction check. Never return the database name, URL,
  credentials, driver exception, business rows or account information. A mismatch
  or unknown result stops the check. No writes, account creation/deletion or AI.
- Keep the public frontend mode unchanged. Private mode and real-account
  acceptance are outside this diagnostic's scope.
- Replace this branch's build entry with a Preview/branch guard followed by
  TypeScript compilation and Vite build. Historical prebuild tests and data
  refresh are skipped; this build is not a full release gate. Build children
  receive a small noncredential environment allowlist. No new dependencies.
- Set an install command that ignores package lifecycle scripts. Remove this
  branch's cron and queue trigger registrations to avoid background processing.
  Project configuration and production resources are not changed.
- Add synthetic unit checks for the diagnostic guard, confirmed test database,
  mismatch, unknown/read-only failure, connection closure and error redaction.
  These do not establish a live database binding.

## Required live evidence

Record the pushed branch SHA, corresponding Preview ID/URL/state, the platform
commit metadata and the diagnostic deployed commit, then the boolean database
binding result. Do not infer binding from a Neon project/branch/host name: this
Neon branch can contain both test and production databases. If the deployed
check cannot confirm `neondb`, stop downstream tests and report the blocker.
Never run `pilot-preview-smoke.mjs`; it includes permanent account deletion.

This file describes the diagnostic contract, not a deployment success claim.
The local evidence package records actual commands and observations separately.
