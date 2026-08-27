# Challenge Result Rubric

Use this rubric to choose material hypotheses, preserve independence, and reach
one of the three challenge outcomes. It supplements rather than replaces the
plan uncertainty and result-review rubrics.

## Independence protocol

Prefer the strongest mode the host supports:

### Context-isolated review

Give a fresh reviewer the original business question, governed context needed
for the question, relevant schema, executed SQL, and raw result or result
metadata. Initially withhold the original narrative conclusion, the user's
expected answer, and prior review verdict. Ask the reviewer to reconstruct the
intended interpretation, plan shape, and highest-risk failure hypotheses.

After that reconstruction is fixed, reveal the original plan, conclusion, user
concern, and prior review so the reviewer can compare them. The reviewer remains
read-only and returns evidence to the active session; it does not execute a new
analysis or edit artifacts.

### Structured same-context review

When isolation is unavailable, explicitly reconstruct the expected analysis from
the original question and governed evidence before comparing plan clauses and
results. Label the review `independence: structured-same-context`; do not claim it
was independent in the strict sense.

## Hypothesis surface

Prioritize hypotheses by their plausible material impact and the evidence needed
to distinguish them. Do not enumerate every theoretical failure mode.

### Meaning and scope

- competing metric or entity definitions;
- wrong population, cohort, status, or eligibility rule;
- omitted mandatory filter or exclusion;
- dimension semantics that differ from their labels;
- cumulative versus period value, amount versus count, or percentage versus
  percentage-point interpretation.

### Time

- inclusive or exclusive boundary mismatch;
- event time versus processing time;
- timezone, fiscal calendar, partial period, or comparison-window mismatch;
- late-arriving facts, backfills, or restatements.

### Grain, joins, and aggregation

- base or output grain mismatch;
- fanout, many-to-many joins, slowly changing dimensions, or deduplication;
- non-additive metrics, distinct-count scope, window partitions, or filters
  applied after aggregation;
- null, zero, signed-value, or divide-by-zero handling.

### Sources and operations

- noncanonical source, stale model, incomplete load, schema change, or freshness
  gap;
- truncation, row limits, cached results, failed partitions, or execution
  warnings;
- dashboard comparison with different filters, dates, refresh time, units, or
  rounding;
- query history or precedent that reflects common practice but not governed
  meaning.

### The user's expectation

- expectation uses a different definition, scope, time window, or unit;
- comparator is stale or filtered differently;
- a business event affected a different population or period;
- an expected range is anecdotal or no longer current.

## Challenge ledger

Use a compact table or equivalent structure:

| Hypothesis | Why plausible | Distinguishing evidence | Check performed | Finding | Likely impact | Missing evidence |
|---|---|---|---|---|---|---|

Use `supported`, `not supported`, or `unknown` for the finding. Do not turn
`unknown` into `not supported`.

## Assumption ledger

Separate assumptions into four groups:

1. **Inherited:** present in the approved plan and still supported.
2. **Challenged:** inherited assumptions that evidence contradicts or weakens.
3. **Introduced:** new assumptions needed to test or explain an alternative.
4. **Approval required:** material assumptions that only a domain owner or user
   can resolve.

An introduced assumption cannot become part of a replacement analysis merely
because it produces a more expected number.

## Outcomes

### UPHELD

Use only when no tested material hypothesis identifies a defect and no unresolved
critical gate remains. State the scope of the review and every material hypothesis
that could not be tested. `UPHELD` means “no material defect found in available
evidence,” not “proven correct.”

Do not raise the original confidence merely because the challenge found no defect.
An increase requires new evidence that closes a previously recorded gap.

### REPLAN

Use when evidence establishes a material defect in meaning, population, source,
filter, grain, join, time semantics, computation, or execution—or establishes a
more credible interpretation that materially changes the analysis.

Create a replan brief for `analytics-plan`:

```yaml
replan_brief:
  original_question: "..."
  original_plan_reference: "..."
  defect:
    summary: "..."
    evidence: []
    likely_impact: "overcount | undercount | wrong population | wrong period | unknown"
  corrected_interpretation: "..."
  required_changes:
    metric: []
    population: []
    sources: []
    joins: []
    filters: []
    grain: []
    time: []
  retained_assumptions: []
  assumptions_requiring_approval: []
  unresolved: []
```

`analytics-plan` owns the revised plan, uncertainty score, user approval, and any
later execution. The challenge itself owns only the diagnosis and handoff.

### INCONCLUSIVE

Use when a material concern remains plausible but cannot be resolved from the
available artifacts or authorized tools. Name the missing evidence, why it
matters, the smallest next diagnostic, and the appropriate owner. Do not replan
around an unresolved assumption merely to produce another number.

## Confidence and escalation

Carry forward pre-query uncertainty and post-query confidence. The challenge may
downgrade either when it uncovers a new gap or contradiction. It may improve a
score only when new evidence satisfies a feature that was previously missing;
record that evidence explicitly.

Recommend escalation regardless of prior score when:

- governed sources conflict on a load-bearing definition;
- a material grain, join, population, or time assumption remains unresolved;
- a trusted comparator still disagrees after filters, dates, units, and freshness
  are aligned;
- authorized evidence cannot distinguish two materially different readings;
- the result informs a consequential decision and the outcome is
  `INCONCLUSIVE` or confidence remains low or unknown.

Use the domain owner named in context. Otherwise recommend the data or analytics
owner; never invent a person.
