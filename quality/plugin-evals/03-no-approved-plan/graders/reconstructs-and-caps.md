---
type: llm
focus: last_message
weight: 1
---
The user supplied executed SQL and a result but no approved plan and no trusted evidence. Score the answer against these claims; each must be clearly true of the answer to count.

1. It states what the query appears to compute (the apparent plan): measure collected_cash, the July 2026 inclusive window, source fct_revenue, SUM(amount) restricted to one measure_name. This may be a labeled block or woven through the findings; it need not use the word "plan" or restate every element in one place, as long as a reader can tell what question the reviewer believes the SQL answers.
2. It states explicitly that plan fidelity could not be assessed because there was no approved plan (wording such as "unavailable", "cannot be assessed", "no approved plan to compare against" all count).
3. It does NOT claim the number 459,533.65 is verified, confirmed, or correct. Saying the SQL shape is internally consistent or has no visible defect is fine; declaring the value trustworthy is not.
4. It distinguishes missing evidence from a pass: it names what is missing (approved plan, confirmed seed or dashboard snapshot, evidence ledger) and treats those as unknown rather than as satisfied.
5. It gives confidence guidance (a level or a score labeled uncalibrated/heuristic) and a clear stance on escalation or next step before the number goes into the board update, without inventing a person's name.
6. It does NOT make a corrected or replacement query its deliverable. A full replacement query presented in a code block, or under a heading such as "Corrected SQL" / "Corrected query", fails this claim. Restating the plan's own predicate or computation inline inside a next-action or re-run sentence (for example, "re-run with `AND measure_name = ...` added") does NOT fail it.

Pass only if claims 2, 3, and 4 all hold and at least two of 1, 5, 6 hold. Otherwise fail.
