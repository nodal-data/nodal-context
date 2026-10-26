# Eval-seed harvesting

Every confirmed disambiguation produces a seed or a reviewed equivalent variant.
Capture the analyst's wording and selected interpretation at the moment of review.
A seed pairs a real question with its correct handling; it is an evaluation answer
key, not material for an answering agent to copy.

## Author a 0.3 seed

Use `evals/seeds/<name>.seed.yaml`. This fictional draft illustrates the structure;
replace its business rules through interview, not by copying the example as truth:

```yaml
question: "What was recognized revenue last quarter?"
domain: executive-revenue
intent: >
  Use recognized revenue, excluding test orders. Bookings is a different metric;
  do not substitute it or subtract refunds again.
ir:
  metric: recognized_revenue
  dimensions: []
  time_window: last_quarter
expected:
  kind: sql_shape
  must_include:
    - "recognized revenue for the requested quarter, with the test-order exclusion"
  must_exclude:
    - "bookings substituted for recognized revenue"
    - "refunds subtracted a second time"
provenance: interview
```

Record the analyst's selected interpretation as evidence on a working branch.
Definitions become approved through protected human-reviewed merge. The referenced
metric must exist and dependencies must be current. Live authority evidence binds
approval to the exact revision; missing evidence blocks governed use. Preserve
historical attribution in `review_history`. Snapshot result verification is a
separate operation and never grants definition approval.

## Choose the expected kind

| Kind | What it establishes | Required evidence |
| --- | --- | --- |
| `semantic_entity` | Correct resolution to a governed entity | `expected.entity`; reviewed entity meaning |
| `sql_shape` | Required interpretation, filters, joins and grain | Reviewable `must_include` / `must_exclude` obligations; method disclosures and checks where applicable |
| `value_at_snapshot` | A value or table for pinned inputs | `value`, `as_of`, actual reference evidence and analyst confirmation |
| `negative` | An appropriate decline or escalation | `reason: lack_data|unresolved_semantics|not_sql` and reviewed intent |

Entity and shape seeds can become stale when their definitions, dependencies or
interpretations change. They avoid fluctuating live-number expectations; they are
not immune to drift. A rejected interpretation of an answerable question belongs
in `intent` and `must_exclude`, not automatically in a negative-kind seed.

For snapshots, fix the time window, as-of date, dimensions, filters and input
snapshot. Tabular expectations use row objects and `key_columns` (required for
multiple rows); compare by keys rather than row order. Declare nonnegative
`tolerance.absolute` / `.relative` before running the comparison. Default is exact
comparison; nulls and nonnumeric values always compare exactly. A live number
without pinned inputs is not durable ground truth.

## Record metric or method IR

Confirmed positive metric/method seeds require IR. Use exactly one target:

- Metric: canonical `metric`, optional `dimensions`, typed `filters`, `grain`
  and `time_window`. A qualified name is `<domain>.<metric>`; unqualified names
  resolve in the seed's domain. Resolve family/alias ambiguity before writing it.
- Method: canonical `method`, `metrics` resolved for this question, and bound
  `parameters`, optionally `dimensions` and `time_window`. A changed cohort
  selector can change the resolved metric set as well as its parameter value.

Entity-only and negative seeds may omit IR; supplied IR must still validate.
Use time tokens declared in `context.config.yaml`. Absolute `{start,end}` bounds
are for `value_at_snapshot` seeds with `as_of`. Do not invent missing IR during
migration: leave the seed draft until the interpretation is reviewed.

Shared fragments, transitive metric references, ratio policies and method
constraints apply before evaluating a seed. For methods, harvest the decisions
that prevent wrong answers and `output.must_state` disclosures, not just an
aggregate total. Checks against result relationships require actual execution;
a proposed query or a model assertion cannot satisfy them.

## Preserve the alternatives and observed wording

When the analyst selects among plausible readings, include the rejected readings
and reasons in `intent`, and appropriate exclusions in `expected.must_exclude`.
Capture a materially new interpretation as a new draft seed for review.

An equivalent, reviewed phrasing can become a variant:
`{text, observed_at, provenance, approver?}`. Preserve its wording and timestamp.
The default cap is 20 (`variants.max_per_seed`); reviewed insertion drops normalized
near-duplicates and replaces the oldest at capacity. Preserve overflow and review
history locally, not in answering prompts. Use Stage 6's
`review_observed.py prepare|apply|resume` workflow for queue entries; string
similarity alone does not establish equivalence. See `observed-demand.md`.

## Verification sources and approval

Interview confirmation establishes intended handling. A dashboard or notebook
comparison adds result evidence for a specific parameterization:

- Dashboard: Stage 5 independently answers with context off/on and checks the
  on-answer against a reviewed dashboard value and its active filters. A browser
  capture alone is not human approval. See `live-verification.md`.
- Notebook: static import creates a draft method. After reviewing its decisions,
  rerun the source notebook and independently generate and execute an answer from
  the method on identical pinned inputs. The answering context receives no source
  notebook code, reference outputs or seed expectations. A matched run remains
  unconfirmed until human review. See `notebook-verification.md`.

Confirmed notebook snapshot seeds use `provenance: notebook` and
`verification_source: {kind: notebook, repo?, path, ref, output}`, identifying the
revision/content hash and agreed output. Python-only analyses need no fabricated
SQL sidecar. Source/method/input changes require another comparison; an unsuccessful
attempt never overwrites the historical expected value to make it pass.

When approved SQL exists, use `scripts/verified.py capture` to store ignored
`evals/verified/<name>.sql` and configured age/SOPS ciphertext in one operation.
The seed's `verified_query_file` points to the plaintext path; only ciphertext
travels with a clone. Explicit `none` is local-only; crypto failure is
`local_unpublished`. Neither form enters answer generation. See `verified-sql.md`.
Keep notebook runs, traces and row evidence in ignored local evidence directories.

## Measurement and drift

The harness reports measured context-on minus context-off accuracy on comparable,
actually graded positive cases. It does not assume a perfect 100% answer. Report
negative escalation accuracy separately; skipped execution and draft/blocked
cases do not become passes. Definition, slicing and verification coverage are
separate; an equivalent structural match cannot transfer a snapshot across inputs.

Keep evaluated seeds, expected values, variants and verified queries out of
answer-generation retrieval. The grader may use their expectations after the
independent answer has been produced. Effective draft dependencies exclude a
stored-confirmed seed from confirmed evaluation until reconciled.

Fresh re-grading may restore an already human-approved shape/entity seed only
under the spec's unchanged-semantics and ready-dependency rules. It cannot approve
new meanings, metrics or methods; snapshots need renewed human verification.
See `drift-review.md` for batching affected cases.

Prefer a small set of meaningful caveat and disambiguation cases over redundant
questions. Optional generated long-tail candidates stay `provenance: generated`,
proposed working-branch content until a human reviews them. Simulation also stays draft; it cannot
create human approval or execution evidence.
