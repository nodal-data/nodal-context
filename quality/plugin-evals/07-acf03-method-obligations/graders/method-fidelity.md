---
type: llm
focus: last_message
weight: 1
---
Pass only if the review rejects this analysis as materially unfaithful (FAIL or an
equally explicit do-not-use conclusion) and identifies BOTH defects with evidence:
(1) `cohort_size = len(followup_ids)` counts the follow-up population instead of
the fixed base cohort; (2) source_id is used without the required canonical
identity mapping, so deduplication and return membership can be wrong. It must
explain that equal aggregate counts/rate do not establish method fidelity. Do not
require a direction of numerical bias: the supplied evidence does not establish
it. Passing based on the notebook's matching total fails this grader.
