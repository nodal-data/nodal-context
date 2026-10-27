# Subscription reference

## Routing

`renewal_rate` composes `renewed_terms` and `churned_terms`. It counts decided
subscription terms, not distinct customers. It is not `methods/cohort-retention`.
Both components use the same predecessor term-end window and plan/segment slices.

<a id="pattern-renewal-outcomes"></a>
### Decided renewal outcomes

Without this: An empty decided population has no rate.

The source enforces at most one successor per term. Count each predecessor once;
exclude undecided/test predecessors and test successors. Select a component only
after the successor lookup. The final ratio uses null for an empty population.

```sql
WITH decided_terms AS (
  SELECT subscription_terms.term_id, subscription_terms.plan, subscription_terms.segment,
         subscription_terms.renewed_from_term_id
  FROM subscription_terms
  WHERE subscription_terms.outcome_decided = TRUE
    AND subscription_terms.is_test = FALSE
    AND subscription_terms.term_end_date >= <period_start>
    AND subscription_terms.term_end_date < <period_end_exclusive>
), outcomes AS (
  SELECT predecessor.term_id, predecessor.plan, predecessor.segment,
         CASE WHEN successor.term_id IS NOT NULL THEN 'renewed' ELSE 'churned' END AS outcome
  FROM decided_terms AS predecessor
  LEFT JOIN subscription_terms AS successor
    ON successor.renewed_from_term_id = predecessor.term_id
   AND successor.is_test = FALSE
)
SELECT outcome, plan, segment, COUNT(DISTINCT term_id) AS decided_terms
FROM outcomes
GROUP BY outcome, plan, segment
```
