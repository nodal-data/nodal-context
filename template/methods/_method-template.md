---
name: <method-slug>
kind: method
domain: <owning-domain>
aliases: []
description: <the analysis and when to use it>
metrics: []
lineage: inherit
parameters:
- name: window
  note: <reporting window; require explicit bounds>
decisions:
- id: population
  rule: <which population is included in <window>>
  without_this: ''
output:
  grain: <one row per what>
  columns: []
  must_state: [window used]
checks: []
---

## When to use

<The questions this method answers; offer alternatives when ambiguous.>

## Procedure

1. Resolve the population in <window> (`population`).

## Worked parameterization

<An illustrative question mapped to declared parameters.>

## Known traps in this warehouse

<Qualitative failure modes, not result statistics.>
