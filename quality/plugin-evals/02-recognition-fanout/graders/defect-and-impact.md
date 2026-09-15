---
type: llm
focus: last_message
weight: 1
---
The answer is a review of executed SQL against an approved plan. Score it against these claims; each must be clearly true of the answer to count.

1. It identifies the specific defect: the SQL joins stg_revenue_recognition on order_id, which is one-to-many (up to 12 rows per business-subscription order), and then aggregates with COUNT(*) and SUM(gross_amount) without deduplicating, so rows fan out.
2. It ties the defect to the plan clause (the plan specifies stg_orders alone, joins: [], grain one row per order) and to the SQL construct (the JOIN and/or the aggregation over the joined rows).
3. It states the directional impact as an overcount for both order_count and gross_order_value, and notes the effect is concentrated on business_subscription (d2c and marketplace have one recognition row each, so those channels are barely affected or unaffected).
4. It uses the trusted evidence: the reported 441 total orders (348 + 78 + 15) versus the captured 122, or the reported gross value versus the 419,204.12 GMV seed, and treats the gap as material.
5. It recommends escalation or hold and names the domain owner from context or a generic data/analytics owner, without inventing a person's name.
6. It gives confidence guidance (a level or a score labeled uncalibrated/heuristic).
7. It does NOT make a corrected or replacement query its deliverable. A full replacement query presented in a code block, or under a heading such as "Corrected SQL" / "Corrected query", fails this claim. Restating the plan's own predicate or computation inline inside a next-action or re-run sentence (for example, "re-run with `AND measure_name = ...` added") does NOT fail it.

Pass only if claims 1, 2, 3, and 7 all hold and at least two of 4, 5, 6 hold. Otherwise fail.
