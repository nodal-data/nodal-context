---
name: refund-impact
kind: method
status: draft
domain: revenue
aliases:
- refund impact
description: Counterfactual refund timing analysis blocked on the attribution date policy.
metrics:
- recognized_revenue
lineage: inherit
parameters:
- name: window
  note: Requested reporting window.
decisions:
- id: date_policy
  rule: Ask the owner which attribution date to use in <window>.
  without_this: Choosing a refund date silently shifts recognized revenue across periods.
output:
  grain: reporting window
  columns:
  - impact
  must_state:
  - Chosen refund date policy
checks:
- Do not claim an impact while the refund attribution decision is open.
---

## When to use

For refund timing counterfactuals; currently blocked.

## Procedure

1. Resolve the date_policy with a human before analyzing <window> (`date_policy`).
