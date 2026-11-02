---
type: llm
focus: last_message
weight: 1
---
Pass only if the answer retains the supplied ordering constraint between order_date and customer_created_date in its evidence or applicable plan checks. It may express order_date >= customer_created_date directly, or an equivalent violation check (for example, count rows where order_date < customer_created_date and require zero violations). Both columns must remain identifiable. A checks list in prose counts even if a separate YAML plan does not repeat it; the literal phrase “cross-column” is not required. A full-model fetch without a column list is allowed and needs no projection-specific explanation.

Fail if the constraint is omitted, replaced by only generic “tests”, made optional because fewer columns were selected, reversed in meaning, or silently added as a business row filter. Do not fail solely because the answer checks for violations instead of repeating the positive predicate. A proposed zero-violation expectation is not a claim that the test has already run or passed.
