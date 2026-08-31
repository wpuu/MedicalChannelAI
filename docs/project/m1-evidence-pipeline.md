# M1 Evidence Pipeline

## Objective

Build the first executable evidence-first pipeline for the Tianjin pilot:

`official source -> source artifact -> evidence/provenance -> canonical opportunity facts -> optional customer context -> action ranking -> frontend-safe public view`

The deterministic fact layer must work without any LLM. Model assistance is downstream and optional.

## Source authority

Priority order:

1. Official China Government Procurement Network and official government procurement/public-resource platforms.
2. Official hospital, university, CDC and health-authority websites.
3. Official procurement-intent, market-research, demand-survey and sourcing notices.
4. Third-party aggregators may be used only for discovery. A third-party page cannot be the sole authority for a critical procurement fact when an official source can be located.

## Critical fact rule

The following fields may only be emitted as verified facts when provenance exists:

- buyer / hospital
- project number and project name
- notice type and lifecycle stage
- publish date
- registration / document-acquisition deadline
- bid / response deadline
- budget
- procurement method
- product / service items and quantities or specifications
- official contact
- award supplier, amount, brand and model when processing award notices

If a source does not establish a field, output `null`/empty rather than infer it.

Each critical fact must be traceable to an evidence record containing at least the source URL and a stable semantic locator such as `公告概要/预算金额`. Store locators, not large copied passages.

## Model boundary

Models such as Agnes may later perform classification, taxonomy matching, explanation, query expansion and recommendation drafting. They must not become the authority for procurement facts.

A model-generated value cannot populate a critical fact unless it is independently grounded in an accepted source and passes deterministic validation.

## Customer context boundary

Customer hospital relationships, brands, manufacturer access, channel partners and leasing capability are private/customer-confirmed context. They are never represented as official public facts.

Zero-config trial remains the default: public opportunity facts and generic action value must be visible without requiring customer data. Customer context is an optional personalization layer.

## M1 data contracts

### SourceRecord

Captures source identity, URL, source class, fetch/observation time and content fingerprint.

### EvidenceRecord

Binds a canonical field path to a source URL and semantic locator.

### CanonicalOpportunity

Contains normalized procurement facts plus evidence references. Unsupported values remain null.

### PublicOpportunity

Frontend-safe projection compatible with the contract consumed by `web/src/services/ApiTodayActionsService.ts`. It must not expose model/provider/API-key/internal task fields.

## Failure behavior

The pipeline must fail closed for unsupported critical facts:

- missing provenance -> reject VERIFIED status for that fact/opportunity
- invalid URL/source class -> reject evidence
- malformed money/date -> keep the original source artifact, but do not silently coerce to a plausible value
- conflicting official sources -> retain both provenance records and mark partial/conflict for human review
- stale/closed opportunity -> preserve the record, update lifecycle/freshness status, do not present it as currently actionable

## M1 implementation order

1. Canonical schema + strict validator.
2. Verified seed records migrated from the existing Tianjin demo, with public facts separated from demo customer context.
3. Deterministic public-snapshot builder.
4. China Government Procurement Network source adapter.
5. Official hospital-site source adapter for pre-tender demand/market-research notices.
6. Deduplication + freshness/lifecycle handling.
7. Only then add model-assisted classification and customer personalization.

## Acceptance gates

M1 is not accepted until all of these are true:

- at least 5 independently traceable Tianjin records can pass the canonical validator
- at least 2 official source classes are represented (government procurement + official hospital/medical institution site)
- every verified critical fact has provenance
- one negative regression proves an unsupported critical fact is rejected rather than invented
- duplicate notices can be identified without relying only on title text
- deadline/freshness logic prevents expired opportunities from being labeled as immediately actionable
- a generated public snapshot can be consumed by the existing frontend API mapping contract
- internal fields such as provider, model name, API key and task payload never appear in the public snapshot
- executable test evidence exists; while GitHub Actions issue #2 remains unresolved, CI must stay marked `BLOCKED_RUNNER_NOT_ASSIGNED`

Until all gates pass: `production_ready=false`.
