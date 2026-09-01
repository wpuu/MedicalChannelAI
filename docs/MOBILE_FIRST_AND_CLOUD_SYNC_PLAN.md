# Mobile-first and cloud sync plan

## Product rule

MedicalChannelAI is primarily a phone product for Chinese medical sales/channel users. Mobile usability has higher priority than desktop density.

For widths below the desktop breakpoint:

- keep the top bar limited to product identity and essential account/reset action;
- use a fixed bottom navigation for 今日、商机、跟进、资源;
- never place trial-mode labels beside the active navigation item;
- do not show build/version diagnostics over user content;
- all user-visible lifecycle/status text must be Chinese; internal enums remain machine-only;
- one browser page may have at most one live AI generation request at a time; all other AI buttons must be disabled until it settles.

Real-device screenshots from `medicalai.qd.je` are the acceptance baseline. Static build checks prevent obvious responsive regressions, but they do not replace real-device verification.

## Current persistence boundary

The current public trial stores private user interaction state in browser storage:

- follow-up status/history/reminders;
- customer product capabilities and hospital relationships;
- cached AI decisions.

This is acceptable only for an anonymous, single-device trial. It is not sufficient for a real external pilot because clearing browser data, changing phones, switching between WeChat/browser containers, or using multiple devices can lose the user's work.

## Target cloud-sync architecture

Before a wider pilot, introduce account identity and make the server the source of truth for private user data.

Recommended shape:

1. Browser/mobile web app on `medicalai.qd.je`.
2. Same-origin authenticated APIs under `/api/*`.
3. Managed PostgreSQL behind the server API (a Vercel Marketplace Postgres provider such as Neon is suitable; provider choice remains replaceable).
4. Browser storage remains only an offline/cache layer and pending-write queue.
5. Public procurement evidence remains separate from private customer data.

Do not connect the browser directly to the database and do not expose database credentials to the client.

## Minimum private data model

- users / organizations
- product_capabilities
- hospital_relationships
- followups
- followup_events
- reminders
- ai_decisions (optional cached result + snapshot/context fingerprint, not raw provider credentials)

Every private row must be scoped by user/organization identity. Public evidence records remain globally readable through the verified snapshot API.

## Migration order

1. Mobile-first UI and Chinese copy.
2. Account identity.
3. Cloud followups/reminders.
4. Cloud customer resources/relationships.
5. Cross-device AI decision cache and durable per-user AI quota.
6. Keep local storage as cache/offline fallback and migrate existing local trial data after explicit user sign-in.

Do not upload existing local private relationship/resource data silently before account identity and user consent exist.
