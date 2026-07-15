# Session Financials Reference

> Agent-facing retrieval doc for Example Healthcare Company session financials.

## Quick Reference
- **Business context** — revenue, collection, and volume for delivered sessions.
- **Entity grain** — one row = note × authorized_service. Use
  `COUNT(DISTINCT note_id)` for session counts, never `COUNT(*)`.
- **Standard hygiene filter** — exclude sessions <45 days old for any
  collection/realization metric (claims take time to adjudicate).
- **Canonical table** — `FCT_SESSION_FINANCIALS`.

## Routing triggers
- IF question is about **collection rate / payment realization** → apply the
  45-day session-age cutoff unless told otherwise, and EXCLUDE PAYER Y
  (different reimbursement cycle).
- IF question filters by **payer** → roughly half of sessions have a blank
  `payer_name`; excluding blanks materially changes aggregates — say so.
- IF question says **"provider"** → DO NOT assume; clarify individual therapist
  (`dim_provider`) vs care provider company (`dim_care_provider_company`).
  Cost-of-care relationships are at the CPC level.
- IF a **payer** like "Payer X" appears → it is state-specific ("Payer X-TX" vs
  "Payer X-FL" are different contracts/rates); DO NOT aggregate across states.
- IF question involves **"Example Healthcare Company"** as a provider → Example Healthcare Company is an internal customer; separate
  internal from external partner customers.

## Gotchas
- `COUNT(*)` overcounts sessions because of the service-level grain.
- Blank `payer_name` is meaningful, not missing-at-random.
- Collection rates on recent sessions look artificially low.

## Common query patterns

### Session counts at the right grain
Without this: `COUNT(*)` overcounts sessions — the grain is note × authorized_service.
```sql
SELECT COUNT(DISTINCT note_id) AS sessions
FROM FCT_SESSION_FINANCIALS
WHERE <standard hygiene filters>
```

### Collection rate, adjudication-safe
Without this: sessions under 45 days old haven't adjudicated, so the rate reads
artificially low — and Payer Y's different reimbursement cycle skews it further.
```sql
SELECT SUM(collected_amount) / SUM(allowed_amount) AS collection_rate
FROM FCT_SESSION_FINANCIALS
WHERE session_date < DATEADD('day', -45, <as_of_date>)
  AND payer_name NOT ILIKE 'Payer Y%'
```

## Cross-references
- collections (claims subset of this table); client-lifecycle (dim_client).
