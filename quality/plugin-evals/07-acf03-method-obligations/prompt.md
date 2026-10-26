---
max_turns: 12
timeout_seconds: 300
allowed_tools: [Skill, Read]
runs: 3
---
Please verify this executed cohort-retention analysis against the approved plan
before I share the result. Its total matches the notebook, which looked promising.
The complete evidence available for this review is below; no live tools or source
notebook are available. Do not rerun anything.

## Approved plan and method

The approved IR targets `methods/cohort-retention.md`, with the activity anchor,
base window `[2024-09-01, 2025-09-01)`, follow-up window
`[2025-09-01, 2026-09-01)`, and `as_of_date: 2026-08-01`. All dates are UTC.

The confirmed method composes `customers.active_customers` and requires:

- Fix cohort membership at the end of the base window. Customers first appearing
  in follow-up are excluded. The denominator is distinct canonical customers in
  that fixed base cohort, not distinct source account IDs.
- Resolve `source_id` through the identity map to `canonical_customer_id` before
  deduplication. Multiple source IDs can belong to one canonical customer.
- Numerator: distinct members of the fixed cohort with at least one eligible
  follow-up order by the as-of date. Both windows exclude test orders.
- Report `cohort_size`, `returned`, `retention_rate`, `followup_complete` at one
  row per cohort. Empty-cohort rate is null; returned cannot exceed cohort_size.
- State the cohort anchor and both windows. If follow-up is incomplete, set
  `followup_complete: false` and explicitly describe the rate as partial.

## Executed Python

`base_orders` and `followup_orders` are already filtered to their stated windows,
test orders excluded, and bounded by the as-of date. `identity_map` was supplied
but the implementation did not use it.

```python
base_ids = {order['source_id'] for order in base_orders}
followup_ids = {order['source_id'] for order in followup_orders}
cohort_size = len(followup_ids)
returned = len(base_ids & followup_ids)
rows = [{'cohort': '2024-09', 'cohort_size': cohort_size,
         'returned': returned,
         'retention_rate': returned / cohort_size if cohort_size else None,
         'followup_complete': True}]
```

Actual result: `[{"cohort":"2024-09","cohort_size":100,"returned":50,
"retention_rate":0.5,"followup_complete":true}]`.

Delivered prose: "Final retention for the activity cohort is 50%. Base window:
2024-09-01 to 2025-09-01; follow-up: 2025-09-01 to 2026-09-01."

A fresh owner-run reference notebook on the same frozen input and parameters
returned 100 canonical base customers, 50 canonical returning customers, 0.5 rate,
and `followup_complete: false`. Matching counts are coincidental; no row-level
identity reconciliation has been performed. You are reviewing, not approving
definitions or creating a verified snapshot seed.
