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
  45-day session-age cutoff unless told otherwise, and EXCLUDE PAYER X
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

## Cross-references
- collections (claims subset of this table); client-lifecycle (dim_client).
