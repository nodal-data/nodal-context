---
name: cohort-retention
kind: method
status: confirmed
approver: fictional-example-reviewer
confirmed_at: '2026-10-01'
domain: customers
aliases:
- customer retention
- repeat rate
description: Share of a fixed canonical customer cohort with an eligible return order in the follow-up
  window.
metrics:
- active_customers
- new_customers
lineage: inherit
parameters:
- name: base_window
  note: Half-open base date bounds.
- name: followup_window
  note: Half-open follow-up bounds; if omitted, ask or derive an equal-length adjacent window explicitly.
- name: cohort_anchor
  note: activity or acquisition; changes the resolved metric set.
  default: activity
- name: cohort_key
  note: Optional approved dimension; omission means one cohort total.
  dimension: true
- name: as_of_date
  note: Pins relative dates and follow-up completeness.
decisions:
- id: identity
  rule: Use canonical customers and exclude test customers and orders in both windows.
  without_this: Multiple source identities and test accounts inflate retention.
  references:
  - entities/customer-subjects.yaml#canonical-customer
- id: anchor
  rule: Use active_customers for activity and new_customers for acquisition in <base_window>; report <cohort_anchor>.
  without_this: Activity and acquisition cohorts have different denominators.
- id: fixed_membership
  rule: Freeze the base cohort before applying <followup_window>; count each member at most once.
  without_this: Adding later acquisitions or counting repeat orders changes the denominator or overstates
    returns.
- id: completeness
  rule: Compare followup_window end with <as_of_date>; disclose partial follow-up rather than presenting
    it as final.
  without_this: An unfinished follow-up window looks like excess churn.
- id: empty_cohort
  rule: For an empty cohort, return a null retention_rate; preserve the requested <cohort_key> slice.
  without_this: An empty population falsely appears to have complete churn.
output:
  grain: cohort or cohort by cohort_key
  columns:
  - cohort_label
  - cohort_key
  - cohort_size
  - returned
  - retention_rate
  - followup_complete
  optional_columns:
  - cohort_key
  must_state:
  - cohort_anchor used
  - base_window and followup_window as explicit dates
  - whether follow-up is complete
  dimensions: []
checks:
- returned <= cohort_size for every row
- retention_rate is null wherever cohort_size = 0
- cohort_size reconciles to the selected anchor metric in base_window with the same cohort_key.
- A false followup_complete value requires a partial-window disclosure.
not_this:
- target: subscriptions.renewal_rate
  reason: Subscription terms renewing are not customers returning.
provenance:
  kind: interview
---

# Cohort retention

## When to use

Use for canonical customers returning after a base window. Clarify whether cohort_anchor
is activity or acquisition, and whether an optional cohort_key is requested. This
fictional method is a complete reviewed-shape fixture, not an executed customer notebook.

## Procedure

1. Resolve <base_window>, <followup_window>, <cohort_anchor>, <cohort_key> if present,
   and <as_of_date>. Select the matching anchor metric (`anchor`, `completeness`).
2. Resolve canonical identities and both eligibility exclusions (`identity`).
3. Freeze cohort membership at base-window end, then test for at least one eligible
   follow-up order per member; never add new customers to that cohort (`fixed_membership`).
4. Aggregate cohort_size and returned for the selected slice, with null rate for an
   empty cohort (`empty_cohort`). The optional cohort_key column appears only for a
   requested slice. For a requested dimension, include all of its non-test customer
   values in the as_of_date snapshot, including empty base cohorts.
5. Compare the follow-up end with the as_of_date, emit followup_complete, state both
   windows and the anchor, and label partial follow-up (`completeness`).

## Worked parameterization

The fixture seeds distinguish activity and acquisition anchors. The activity default
resolves only active_customers; acquisition resolves new_customers plus active_customers
for the return test. Explicitly selecting activity is equivalent to omitting its default.
Changing the anchor must change the resolved metric set, not just a parameter value.
