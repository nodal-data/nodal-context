---
name: verify-result
description: Review analytics SQL and results against an approved plan for metric, filter, grain, join, and time fidelity, then assess plausibility and escalation needs. Use after analytics execution or when asked to audit a query/result. Do not use to define metrics or modify data.
---

Approval contract: new and changed context stays on a named working branch and
has no authored approval status. Human-reviewed protected merge grants definition
approval; consult the live authority through the runtime for the exact revision
and freshness. Missing/expired evidence or stale dependencies blocks governed
use. Explicit branch-test mode is proposed context only. Query/notebook result
verification is separate from definition approval; retain source and review
evidence. See the context-interview SPEC approval-through-merge contract.


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
- A review describes the required correction; it does not deliver a complete
  replacement SQL/Python implementation, even in a next-step section. Cite the
  relevant predicate or operation inline and hand implementation back to the
  analyst or `analytics-plan` for the approved rerun.
- Any diagnostic warehouse query must be read-only, bounded, and necessary to
  evaluate a named risk. Use only an already-authorized connection.
- Do not treat query history or typical ranges as ground truth. They support a
  plausibility finding, not a semantic definition.
- Missing evidence stays `unknown`; it is never converted into a pass.
  Do not infer data completeness from how long ago a period ended, or declare
  null handling safe without evidence about the metric. Unobserved schema risks
  are questions to resolve, not findings that those columns or defects exist.

## Review

1. **Plan fidelity.** Compare the approved interpretation and IR against the SQL:
   metric expression, source tables, joins and cardinality, mandatory filters,
   exclusions, grain, dimensions, time boundaries/timezone, comparison, ordering,
   limits, and expected output shape.
   Use the same expanded ACF definitions and canonical metric/method IR as the
   plan. Check inherited/grouped filters, entity-filter stages, allowed dimensions,
   zero-denominator policy, and effective status/open decisions. For a method,
   check selected metric branches, parameter defaults, decision IDs, declared
   overrides and stock/flow alignment against the actual SQL/Python implementation.
2. **Query risks.** Check fanout, deduplication, slowly changing dimensions,
   many-to-many joins, null behavior, divide-by-zero handling, signed values,
   mixed grains, non-additive metrics, and filters applied after aggregation.
3. **Execution evidence.** Record success/failure, row count, returned columns,
   null/duplicate symptoms, and whether the result shape matches the plan.
   For methods, verify required disclosures, output grain/keys/columns and each
   qualitative check against actual results. A generated implementation or a
   model's assertion cannot establish execution or a result relationship. Missing
   execution/check evidence requires `WARN`, even if proposed SQL looks correct.
4. **Plausibility.** When evidence exists, compare with a confirmed seed, trusted
   dashboard capture, bounded prior result, or historical range. Preserve the
   source and snapshot/filter state. Do not invent a range.
   A reviewed independent notebook comparison is also eligible evidence. Compare
   the same inputs, as-of date and bindings; compare keyed row sets, reject duplicate
   keys, preserve nulls and use only pre-agreed numeric tolerances. Equal totals
   cannot excuse wrong cohort membership, output grain or missing disclosures.
   Stale method/source/dependency revisions invalidate the prior comparison.
5. **Confidence and escalation.** Apply `references/review-rubric.md`. Post-query
   confidence may downgrade plan confidence; overall confidence is the lower of
   the two. A trusted snapshot match supports verification but does not erase an
   unresolved semantic conflict.

## Output

Lead with one outcome:

- `PASS`: implementation is faithful, required checks have supporting evidence,
  and no material anomaly was found.
- `WARN`: no proven defect, but evidence is incomplete or a plausible risk remains.
- `FAIL`: SQL departs materially from the plan, execution failed, or trusted
  verification evidence contradicts the result.

Then list findings by severity with the exact plan clause, SQL construct, and
impact. Include post-query confidence, overall confidence, evidence checked and
unavailable, and a concrete escalation recommendation. Avoid generic advice such
as “double-check the query.”

State plan fidelity explicitly as `faithful`, `unfaithful`, or `unavailable`.
With no approved plan, use `Plan fidelity: unavailable`; an apparent plan inferred
from SQL does not fill that gap or authorize upgrading the result to a pass.
