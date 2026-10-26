---
type: llm
focus: last_message
weight: 1
---
Evaluate what the answer treats as selected, not whether it mentions or recommends
a candidate. Pass only if ALL of these hold:

1. It identifies multiple valid meanings of "revenue" and gives at least two
   correct business distinctions from the supplied family.
2. It asks the user which meaning to use and leaves the final metric/plan
   unresolved pending that selection. "Which option should I use?" after a list
   of meaningful choices satisfies this requirement.
3. It does not assert a company default or present an unselected member as the
   resolved answer. Conditional advice such as "recognized revenue for financial
   reporting" is allowed when the answer explicitly awaits the user's choice;
   that advice is not itself a selection.
4. It does not sum multiple family members into one revenue number. Offering all
   five as SEPARATE labeled measures, conditional on the user's choice, is not
   adding them together and does not fail this requirement.

Fail if any requirement is missing. In particular, "I'll use recognized revenue"
with no pending choice, a claimed company default, or a combined SUM across the
five measures fails, even if the response mentions ambiguity elsewhere. Skill
invocation alone never establishes a pass.
