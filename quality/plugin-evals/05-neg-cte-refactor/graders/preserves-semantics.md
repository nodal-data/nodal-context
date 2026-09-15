---
type: llm
focus: last_message
weight: 1
---
The user asked only for a readability refactor of a working query into CTEs. Score the answer against these claims; each must be clearly true to count.

1. The answer contains a rewritten SQL query that uses one or more CTEs (a WITH clause).
2. The rewritten query still restricts to activity_date between 2026-06-01 and 2026-06-30 inclusive (same window, not widened or narrowed).
3. The rewritten query still produces exactly two output columns named billed_revenue and collected_cash, each summing amount for only its own measure_name, rounded to 2 decimals.
4. The answer does not issue a PASS/WARN/FAIL verdict, does not run a fidelity or plausibility review, and does not challenge the signed-off numbers.

Pass only if all four claims hold. Otherwise fail.
