# Complete ACF 0.3 example: Example Orchard

Every company fact, reviewer identity and expected value here is synthetic. A
`fictional-example-reviewer` confirmation demonstrates the schema and does not
claim that a real analyst approved these definitions or that a notebook ran.
No customer identifiers, notebook code, warehouse rows or credentials were copied
from the supplied migration examples.

This graph includes five revenue-family siblings and reusable fragments; two
non-expression renewal components with a real deterministic query-pattern target;
a ratio with null empty-denominator policy; two cohort anchors, a complete method
and canonical customer entity; blocking policy decisions; variants, shape/entity,
negative and synthetic snapshot seeds. The notebook snapshot stays draft until
an actual independent comparison is reviewed. The refund-impact method is draft
and also blocked by an explicit decision on recognized_revenue.

From the tool repository root:

```bash
python3 .ci/validate.py examples/example-acf-03-company --schemas schemas
python3 tests/test_acf_example.py
python3 scripts/compile_skill.py examples/example-acf-03-company
```

The executable example test checks the complete graph, family ambiguity, dependency
impact, cohort selector/default matching and synthetic keyed/null/partial-window
results. It is an offline contract exercise, not live warehouse or model acceptance.
Use `evals/playbooks/verify-cohort.md` for the notebook verification exercise.

No manifest is supplied, so validation must report column lineage as unchecked.
No encryption backend or executor is configured. `verified_sql.encryption: none`
is explicit local-only mode, not a fallback from failed encryption. Customer
repos should choose their own public recipients and execution capabilities.
