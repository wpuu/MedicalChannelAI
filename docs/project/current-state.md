# MedicalChannelAI current state

Updated: 2026-08-31

## Product state

MedicalChannelAI is a medical-channel commercial intelligence / sales-agent pilot for medical devices, IVD and consumables. The first pilot region is Tianjin.

The product rule is **evidence first**: procurement facts must come from traceable source material. Models may classify, match, explain and recommend actions, but they are not allowed to invent hospitals, projects, budgets, dates, contacts, winning suppliers, brands or model numbers.

## Current deployed demo

- Demo URL: `https://medicalai.qd.je/`
- The H5 demo is represented by `web/`.
- Trial UX is zero-config first: a new user should be able to see useful public opportunities before entering customer resources.
- Customer hospital relationships, brands, manufacturer resources and channel capabilities are optional personalization inputs, not a prerequisite for the first trial.
- `web/src/data/today-actions.verified-demo.ts` contains a verified-public-facts demo snapshot dated `2026-08-30T13:30:00Z`.
- The snapshot contains five Tianjin examples with official evidence URLs. Customer-side relationship/capability fields in that demo are explicitly demo profile data.
- `claude/` and `grok/` are retained frontend candidates/reference implementations; do not treat them as the current production data source.

## Repository reality

At main HEAD `6221925212bbb663793d7e0305e2b98f440c0513`, the repository contains frontend implementations but **does not yet contain a real source-ingestion/fact pipeline**. The README statement `天津 Pilot v0.1 / M1 事实流水线迁移` therefore describes the intended milestone, not a completed backend.

The frontend already contains an API adapter contract (`web/src/services/ApiTodayActionsService.ts` and `GroundedApiTodayActionsService.ts`) for future server data. The next work should implement the upstream evidence pipeline against that public contract instead of redesigning the UI.

## Current blockers

GitHub Actions is currently unreliable for this repository because jobs have failed before being assigned a runner. See issue #2. Until runner assignment is restored, CI results must not be represented as executed PASS evidence.

## Active work

Branch: `chatgpt/m1-evidence-pipeline-v1`

Milestone: **M1 Evidence Pipeline**

Goal: turn official procurement / procurement-intent / market-research / hospital sourcing notices into deterministic, traceable canonical opportunity facts, then produce a frontend-safe public snapshot/API payload.

## Immediate sequence

1. Define canonical source/evidence/fact records and public-output contract.
2. Add deterministic validators that reject unsupported critical facts instead of guessing them.
3. Seed the pipeline with the already verified Tianjin examples used by the H5 demo.
4. Add the first source adapter for China Government Procurement Network (`ccgp.gov.cn`) pages.
5. Generate a public snapshot compatible with the existing frontend API adapter.
6. Only after the deterministic fact layer works, add model-assisted classification/matching and customer personalization.

`production_ready=false` until the evidence pipeline, freshness handling, deduplication, failure states and source coverage are validated with executable test evidence.
