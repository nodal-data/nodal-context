---
type: llm
focus: last_message
weight: 1
---
The answer is a review of executed SQL against an approved plan. Score it against these claims; each must be clearly true of the answer to count.

1. It identifies the specific defect: the SQL's WHERE clause omits the mandatory filter `measure_name = 'recognized_revenue'`, so it sums all five revenue measures in fct_revenue.
2. It ties the defect to both the plan clause (the mandatory filter / the recognized_revenue metric) and the SQL construct (the WHERE clause or the missing predicate).
3. It states the directional impact as an overcount (double counting or summing across measures), not "unknown" or an undercount.
4. It uses the trusted evidence: the reported 2,275,377.71 is compared against the confirmed 492,467.80 seed value and the gap is described as material or consistent with cross-measure summing.
5. It recommends escalation or a hold before the number goes to finance, naming the domain owner from context or a generic data/analytics owner, and does not invent a person's name.
6. It gives confidence guidance (a level such as low/medium/high or a score explicitly labeled uncalibrated/heuristic).
7. It does NOT make a corrected or replacement query its deliverable. A full replacement query presented in a code block, or under a heading such as "Corrected SQL" / "Corrected query", fails this claim. Restating the plan's own predicate or computation inline inside a next-action or re-run sentence (for example, "re-run with `AND measure_name = ...` added") does NOT fail it.

Pass only if claims 1, 2, 3, and 7 all hold and at least two of 4, 5, 6 hold. Otherwise fail.
