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
- Before a family/alias choice is resolved, present options and a conditional
  plan without executable SQL. A side-by-side comparison is a user-selectable
  interpretation, not a default answer to an unresolved singular metric request.
- For ACF, record the effective status of every selected definition and any
  matching/coverage limitations. Preserve grouped filters, entity-filter stages,
  inherited constraints and declared ratio policy; an override must cite the
  method's explicit override decision.

For a method, replace the metric `ir` mapping with:

```yaml
ir:
  method: cohort-retention
  metrics: [customers.active_customers]
  parameters:
    cohort_anchor: activity
    base_window: {start: "2026-01-01", end: "2026-02-01"}
    followup_window: {start: "2026-02-01", end: "2026-03-01"}
    as_of_date: "2026-03-01"
  time_window: last_month
```

The dates above illustrate bindings, not a default for real questions. Use the
customer's declared token and explicitly agreed as-of/timezone. Include the method
decision IDs, selected metric branches, defaulted parameters, output grain/columns,
required disclosures and checks in `computation` and `expected_output`. Do not
place expected snapshot values or a verified-query answer key in the plan.

When approved, retain the artifact unchanged beside the SQL. A necessary change to
tables, joins, filters, grain, or time semantics creates a new plan revision and
requires renewed approval.
