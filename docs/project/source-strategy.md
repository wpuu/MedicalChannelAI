# Source strategy

Updated: 2026-08-31

## Core rule

Discovery and verification are separate stages.

A source may help discover a procurement opportunity without being sufficient to verify all critical facts. Anything that has only been seen in a search list or third-party index remains `DISCOVERY_ONLY` until accepted official evidence is attached to critical fields.

## China Government Procurement Network (CCGP)

Use the public CCGP search surface as the primary centralized discovery layer for government-procurement notices.

- Public search endpoint: `https://search.ccgp.gov.cn/bxsearch`
- Discovery is low-frequency and cache-first.
- If the site reports that requests are too frequent, stop and retry later.
- Search-list metadata is discovery metadata and does not by itself make a canonical opportunity `VERIFIED`.
- A detail notice or another accepted official publication is required for critical facts such as budget, exact deadlines, product items and contacts.

CCGP's formal data-interface specification is useful as a data-contract reference, but its official onboarding process targets government procurement networks and requires formal application. MedicalChannelAI does not assume access to that integration interface.

## Tianjin open-data procurement dataset

The Tianjin open-data platform exposes a government-procurement tender-announcement REST/JSON dataset with useful structured fields. The dataset metadata observed on 2026-08-31 showed an old last-update date (2021-10-25).

Therefore:

- keep it as an optional source-adapter candidate;
- do not use it as the primary current-opportunity source unless a deterministic freshness probe proves recent records are available;
- stale datasets may still be useful for historical research, schema comparison and backfill.

## Official institution websites

Hospital, university, CDC, health-authority and other official institution websites are the second M1 source class. They are especially important before formal tenders because market research, procurement intention, demand survey and in-hospital sourcing notices may appear there earlier.

A site-specific adapter must restrict accepted hosts to configured official domains, preserve the source URL and observation time, retain unsupported fields as null, expose semantic locators for extracted critical facts, and fail closed when the page no longer matches its known structure.

## Architecture consequence

Collectors are replaceable adapters. The canonical fact/evidence contract is the durable layer.

`source adapter -> DISCOVERY_ONLY candidate -> official evidence extraction -> strict validator -> VERIFIED canonical opportunity -> public snapshot/API`

This prevents a blocked source, stale open-data endpoint or model failure from corrupting the product's fact layer.
