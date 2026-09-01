# Opportunity pool logic

## Product meaning

“商机池” is not every hospital procurement notice and is not a win-probability list. It is the set of currently actionable, evidence-backed medical-channel opportunities that deserve a sales/channel user's attention.

## Current production logic

An item can enter the public opportunity pool only after these gates:

1. Official evidence is parsed into a VERIFIED canonical record.
2. Duplicate project identities are reconciled.
3. Official correction/termination events are applied. A termination or unresolved material correction suppresses the stale card.
4. Closed opportunities are archived when the applicable registration/bid window is over.
5. Medical-channel scope filtering excludes generic hospital security, training, finance and other administrative procurement.
6. Remaining records are ranked by a public-fact score:
   - intervention/action window: 40 points while the normal registration/file-acquisition window is open, 15 points in a late window;
   - published budget: 0–20 points.
7. The public pool is sorted by that score. “今日重点” is the first 5 after locally completed/snoozed items are removed.
8. If the user has supplied private resources, the current trial can locally rerank with up to 30 product-execution points and 10 hospital-relationship points.

The score is a business/action priority, never a predicted probability of winning.

## Planned ranking v2

The public score should remain explainable but become less dependent on budget alone. Target public score: 60 points.

- Actionability / intervention stage: 25
- Deadline urgency: 10
- Project value / budget: 10
- Product specificity and executable procurement detail: 8
- Publication freshness: 7

Target private personalization: 40 points.

- Product execution fit: 25
- Hospital/department relationship: 10
- Sourcing / partner / rental execution capability: 5

Tie-break order:

1. higher total action priority;
2. nearer actionable deadline without being closed;
3. fresher official publication;
4. stable opportunity id for deterministic order.

## Pool vs today vs follow-up

- 已核验项目: official records that entered evidence validation; not all must become user opportunities.
- 商机池: verified + in medical-channel scope + not terminated/unresolved + currently actionable.
- 今日重点: up to 5 highest-priority pool items that are not completed or snoozed by the current user.
- 我的跟进: persistent user-owned work list. Once followed, a project remains historically available even after it expires from the live pool.

## Future cloud behavior

After account/cloud persistence is introduced, the private 40-point personalization and today-list suppression must run from server-synced user data so phone changes do not change ranking. Public evidence scoring remains common to all users.

## Guardrails

- Do not use AI output to manufacture procurement facts or raw ranking facts.
- Do not treat hospital name alone as medical-product relevance.
- Do not equate missing facts with a likely future correction.
- Do not expose internal enum/status codes in UI.
- Do not present priority score as win probability, relationship certainty, authorization, or competitor intelligence.
