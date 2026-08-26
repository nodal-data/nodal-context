---
name: verify-result
description: Review analytics SQL and results against an approved plan for metric, filter, grain, join, and time fidelity, then assess plausibility and escalation needs. Use after analytics execution or when asked to audit a query/result. Do not use to define metrics or modify data.
---

# Verify Result

Review an analytical result the way a careful analytics reviewer examines a code
change: first determine whether the query implemented the approved intent, then
determine whether the observed result is plausible. A successful query is not by
itself a verified answer.

## Inputs

Use the approved analytical plan, executed SQL, result or result metadata, and the
context evidence used by the plan. Ask for a missing artifact only when it cannot
be recovered from the current conversation or workspace. If no approved plan
exists, reconstruct the apparent plan from the SQL, label plan fidelity
`unavailable`, and return at most `WARN`.

## Hard boundaries

- Never modify SQL, context, warehouse data, dashboards, or configuration.
- Any diagnostic warehouse query must be read-only, bounded, and necessary to
  evaluate a named risk. Use only an already-authorized connection.
- Do not treat query history or typical ranges as ground truth. They support a
  plausibility finding, not a semantic definition.
- Missing evidence stays `unknown`; it is never converted into a pass.

## Review

1. **Plan fidelity.** Compare the approved interpretation and IR against the SQL:
   metric expression, source tables, joins and cardinality, mandatory filters,
   exclusions, grain, dimensions, time boundaries/timezone, comparison, ordering,
   limits, and expected output shape.
2. **Query risks.** Check fanout, deduplication, slowly changing dimensions,
   many-to-many joins, null behavior, divide-by-zero handling, signed values,
   mixed grains, non-additive metrics, and filters applied after aggregation.
3. **Execution evidence.** Record success/failure, row count, returned columns,
   null/duplicate symptoms, and whether the result shape matches the plan.
4. **Plausibility.** When evidence exists, compare with a confirmed seed, trusted
   dashboard capture, bounded prior result, or historical range. Preserve the
   source and snapshot/filter state. Do not invent a range.
5. **Confidence and escalation.** Apply `references/review-rubric.md`. Post-query
   confidence may downgrade plan confidence; overall confidence is the lower of
   the two. A trusted snapshot match supports verification but does not erase an
   unresolved semantic conflict.

## Output

Lead with one outcome:

- `PASS`: SQL is faithful and no material anomaly was found in available evidence.
- `WARN`: no proven defect, but evidence is incomplete or a plausible risk remains.
- `FAIL`: SQL departs materially from the plan, execution failed, or trusted
  verification evidence contradicts the result.

Then list findings by severity with the exact plan clause, SQL construct, and
impact. Include post-query confidence, overall confidence, evidence checked and
unavailable, and a concrete escalation recommendation. Avoid generic advice such
as “double-check the query.”
