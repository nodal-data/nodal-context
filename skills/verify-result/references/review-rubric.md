# Result Review Rubric

## Fidelity findings

`FAIL` for a material mismatch in metric definition, governed filter, population,
grain, join cardinality, time semantics, or requested comparison. `WARN` for a
non-material output/presentation mismatch or when the plan is unavailable.

For each finding report:

- severity and concise title;
- approved plan clause;
- SQL/result evidence;
- likely directional impact when supportable (`overcount`, `undercount`, `wrong
  population`, `wrong period`, or `unknown`);
- smallest safe next action.

## Post-query confidence v0

Score each feature `0`, `0.5`, or `1`; multiply by weight and sum. Do not
renormalize missing features.

| Feature | Weight | `1` means |
|---|---:|---|
| plan fidelity | 0.30 | every material plan clause is implemented |
| grain/cardinality safety | 0.20 | joins and aggregation preserve the intended grain |
| execution integrity | 0.15 | query completed with no truncation or runtime warning |
| result-shape match | 0.10 | rows/columns/grouping match the plan |
| anomaly evidence | 0.15 | bounded checks find no material anomaly |
| trusted verification | 0.10 | confirmed seed/dashboard snapshot agrees |

Levels are `high` at >= 0.75, `medium` at >= 0.45, and `low` below 0.45. Use
`unknown` when artifacts cannot be inspected enough to score. Always label the
score `calibrated: false` and display it as an uncalibrated heuristic, not a
probability.

Overall confidence is the lower of pre-query plan confidence and post-query
confidence. If plan confidence is absent, overall confidence is `unknown`.

## Escalation gates

Recommend escalation when:

- a `FAIL` affects a reported business value;
- a governed definition or mandatory filter is unresolved;
- grain or join cardinality cannot be established;
- a trusted snapshot materially disagrees after matching filters and dates;
- the result is being used for a consequential decision and confidence is low or
  unknown.

Use the domain owner from context when available; otherwise name the data or
analytics owner, never an invented person.
