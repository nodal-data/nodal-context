# Analytical Plan Format

Produce this information as compact Markdown for people. Include the YAML block
when another agent/session will execute the plan or when the user requests the
artifact explicitly.

```yaml
analytical_plan:
  version: 1
  interpreted_question: "..."
  domain: "..."
  ir:
    metric: "..."
    dimensions: []
    filters: []
    grain: "..."
    time_window: "..."
  evidence:
    - claim: "..."
      source: "..."
      authority: confirmed
      used: true
  sources:
    base: "database.schema.table"
    joins:
      - relation: "..."
        condition: "..."
        relationship: "many-to-one"
        approval: governed
  computation:
    measure: "..."
    mandatory_filters: []
    grouping: []
  expected_output:
    shape: "single value | time series | grouped table | rows"
    columns: []
  assumptions: []
  unresolved: []
  uncertainty: {}
  approval:
    status: pending
```

## Completeness rules

- Use explicit inclusive/exclusive time boundaries and timezone when material.
- State base grain and final output grain separately when they differ.
- Name join cardinality and deduplication before aggregation.
- Preserve every governed mandatory filter, even when the user did not mention it.
- Do not name a table or column that was not found in evidence.
- Mark a source or join `inferred` when only schema shape supports it.
- A plan with unresolved blocking decisions cannot be approved or executed.

When approved, retain the artifact unchanged beside the SQL. A necessary change to
tables, joins, filters, grain, or time semantics creates a new plan revision and
requires renewed approval.
