# Opportunity pool logic

## Product meaning

“商机池” is not every hospital procurement notice and is not a win-probability list. It is the set of currently actionable, evidence-backed medical-channel opportunities that deserve a sales/channel user's attention.

## Admission gates

An item can enter the public opportunity pool only after these gates:

1. Official evidence is parsed into a VERIFIED canonical record.
2. Duplicate project identities are reconciled.
3. Official correction/termination events are applied. A termination or unresolved material correction suppresses the stale card.
4. Closed opportunities are archived when the applicable registration/bid window is over.
5. Medical-channel scope filtering excludes generic hospital security, training, finance and other administrative procurement.
6. Remaining records are ranked only from verified public facts before optional customer-specific reranking.

The score is a business/action priority, never a predicted probability of winning.

## Production v0.3.8

The currently promoted production build still uses the legacy public ranking:

- intervention/action window: 40 points while the normal registration/file-acquisition window is open, 15 points in a late window;
- published budget: 0–20 points;
- local private reranking: up to 30 product-execution points and 10 hospital-relationship points.

This remains documented until the v0.4.1 Preview passes regression and mobile acceptance and is explicitly promoted.

## v0.4.1 ranking v2 candidate

The candidate ranking is designed to prioritize what a medical sales/channel user should act on today rather than allowing project amount to dominate.

### Public facts: 60 points

- Actionability / intervention stage: 25
  - normal actionable window: 25
  - late window after registration closes but before the bid deadline: 8
- Deadline urgency: 10
  - uses the next still-actionable registration or bid deadline;
  - date-only registration deadlines are interpreted through the Shanghai/Tianjin calendar boundary.
- Project value / published budget: 10
- Product specificity and executable procurement detail: 8
  - product items, product category, department and procurement method increase explainable execution detail.
- Publication freshness: 7

No AI-generated conclusion is used to create these raw ranking facts.

### Customer-private personalization: 40 points

- Product execution fit: 25
- Hospital/department relationship: 10
- Sourcing / partner / rental execution flexibility: 5

The final 5-point execution-flexibility component is evidence-constrained by the user's own saved capabilities and policy:

- rental capability can boost a rental-like opportunity when the user confirms they can execute rental projects;
- a matching “needs manufacturer / can source partner” capability can receive a boost when the user confirms they can find a manufacturer;
- a matching partner capability can receive a boost when the user confirms they can cooperate with another channel;
- broad global flags alone do not turn an unrelated opportunity into a product match.

### Tie-break order

1. higher total action priority;
2. nearer still-actionable deadline;
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
