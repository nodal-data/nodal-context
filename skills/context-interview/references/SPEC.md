# Analytics Context Format (ACF) — v0.3

ACF is the Markdown and YAML contract produced by the Nodal context interview
and consumed by analytics agents and the format-agnostic evaluation harness.
Definitions are human-owned; a model may draft but cannot confirm them.

## Migration decisions for review

The implementation must include all four requirements below. They are part of
the 0.3 release scope, not optional follow-up work.

| Requirement | Required behavior |
| --- | --- |
| Retire legacy metrics immediately | ACF 0.3 accepts only per-metric YAML files. Reject `metrics.LookML`, legacy `metrics.yaml` and version 0.2 repositories; retain only an explicit, one-time YAML conversion tool. |
| Verify methods imported from notebooks | Rerun the source notebook, independently generate and execute an AI answer using the reviewed method, and compare both results on identical inputs. Human review is required before confirming a snapshot seed. |
| Ignore local planning specifications | Add `/specs/` to the root `.gitignore` during implementation and exclude that directory from package and clean-room copies. Root `SPEC.md` remains canonical. |
| Keep quick simulated analyst runs | Preserve the `clean-test.sh` entry points and isolated brief-based responder so a maintainer can quickly derive draft 0.3 context from the working tree, including resume support. |

This document is the review deliverable. The changes described here, including
ignore rules and generated distribution updates, belong to implementation after
approval.

For this review, the release decision is final: remove legacy metric support in
0.3 rather than scheduling its removal for a later release. Notebook verification
is an explicit follow-up to importing a method. Quick simulated interviews remain
a supported way to derive draft context without completing that verification.

These decisions override the compatibility language in `SPEC-0.3.md`, specifically
A1, D4 and its Versioning section. “Deprecated” here means removed from supported
inputs in 0.3, not accepted with a warning. The examples in
`~/Downloads/acf-examples/` inform the metric and method design; their approval
names, notebook pointers and example results are not evidence of verification in
this repository.

## Version and migration

`context.config.yaml` declares `version: "0.3"` (numeric `0.3` is also accepted).
The 0.3 runtime rejects earlier versions and the legacy `metrics.yaml` wrapper,
including mixed layouts. Retirement is effective immediately in 0.3: no 0.2
support, warning-only fallback, dual-layout reader or grace period through 0.4.
This is a breaking format migration: retaining 0.2 runtime support is explicitly
out of scope, even when an older repository uses no newly introduced fields.
`metrics.LookML` is not a supported ACF metric artifact or compatibility path;
the legacy single-file format in this repository is `metrics.yaml`. Only
`domains/<domain>/metrics/<metric_name>.yaml` is supported for metric definitions.
Reject legacy `metrics.lookml` filenames case-insensitively, so capitalization
cannot bypass this rule. No LookML compatibility reader or LookML converter is
required. A migration diagnostic identifies the offending version/path and the
supported layout; readers must not silently ignore a legacy artifact alongside
otherwise valid 0.3 metrics.
Run the one-time
`scripts/split_metrics.py domains/<domain> --check` before explicit conversion.
The converter preserves comments and meaning, backs up the original under ignored
`.nodal/migrations/`, and removes it only after successful conversion. It never
invents approval, ratio policy, or a business definition. Review remaining 0.3
requirements before changing the config version and upgrading support tooling.
The converter may read legacy YAML solely as migration input; validation,
compilation, scaffold upgrades and the ACF harness adapter must reject unmigrated
repos with an actionable migration-required diagnostic. Conversion must not
change business meaning or manufacture human confirmations.

Plugin semver is independent of the ACF version. The seven skills share this
contract; ACF remains only one adapter of the evaluation harness.

Release acceptance must exercise the unsupported inputs explicitly: a 0.2 repo,
a 0.3 repo containing only `metrics.LookML`, and a 0.3 repo mixing legacy files
with per-metric YAML must all fail with migration guidance. Do not retain a
compatibility flag that makes these inputs valid. Historical fixtures may remain
solely to test rejection or the explicit YAML converter.

## Optional semantic lint

`.ci/semantic_lint.py` checks reference routing against normalized metric
definitions, method prose against declarations, and domain context against
reference prose. It requires `ANTHROPIC_API_KEY`, imports its SDK lazily, and
returns structured warning candidates with short quotes from both comparison
inputs. Quote checking establishes attribution, not semantic truth. A human
reviews every warning; the linter never changes definitions or approval fields.

Inputs are limited to authored context documents. Do not read notebooks, queue
entries, seed expectations, verified SQL or execution results into model prompts.
Limit each request to 32,000 UTF-8 bytes and each invocation to 20 new requests;
skip oversized or excess comparisons explicitly rather than truncating their
meaning. Cap each response at five warnings. Missing keys, unavailable models,
malformed responses and unresolved input graphs are nonblocking skips, never
successful semantic verification. Deterministic schema/graph validation remains
a separate blocking check.

Cache only derived warnings under `.nodal/semantic-lint/`, keyed by comparison
content, model, prompt/lint version and response schema. Invalid cache entries
must be rechecked. Public output labels warnings unconfirmed and exposes skipped
comparisons; absence of warnings does not prove semantic agreement.

The optional `semantic-context` workflow runs trusted default-branch/base code,
fetches PR context as data-only Git objects, and uses trusted schemas. It never
checks out or executes PR code with a model key. Publish the warning report as a
nonblocking PR comment and retain only that derived report as an artifact.
The customer's model provider receives the selected context comparisons; no
warehouse query or notebook execution is part of semantic lint.

## Load-bearing rules

1. Definitions are approved only by protected human-reviewed merge into the
   designated approval branch. Authored fields and successful tests cannot approve them.
2. Qualitative business logic belongs in context; statistics and execution output
   stay outside it. Expected values at a pinned date belong in snapshot seeds.
3. Definitions carry or inherit lineage, and dependency changes invalidate their
   consumers. Missing manifests mean unchecked lineage, never verified columns.
4. Every confirmed disambiguation emits a seed or an equivalent reviewed variant.
5. Every structured kind has a JSON Schema. Deterministic errors block validation;
   semantic disagreements in prose are warnings for review.
6. Production observations feed the interview. They do not silently rewrite
   confirmed definitions or establish a second source of truth.
7. Warehouse and browser actions are read-only, executed in the customer's
   environment. Nodal never collects credentials or bundles an MCP server.

## Directory contract

```text
context.config.yaml
SPEC.md, README.md, AUTHORING.md, AGENTS.md, CLAUDE.md
company/{overview,terminology,org-structure}.md
entities/<group>.yaml
domains/<domain>/domain.yaml
domains/<domain>/{context,reference,known-issues}.md
domains/<domain>/entities.yaml
domains/<domain>/metrics/<metric_name>.yaml
domains/<domain>/metrics/_shared.yaml
methods/<slug>.md
evals/seeds/<name>.seed.yaml
evals/verified/<name>.sql.age          # committed ciphertext (age)
evals/verified/<name>.sql.sops         # committed ciphertext (SOPS binary)
evals/verified/<name>.sql              # ignored plaintext
evals/observed/queue.jsonl             # ignored review input
evals/runs/, evals/captures/           # ignored execution evidence
evals/playbooks/<slug>.md             # authored, committed
.nodal/                              # ignored caches, migration backups
schemas/, acf_runtime/, .ci/, scripts/, eval_harness/
```

Only the contract paths are loaded. Do not recursively discover definitions inside
cached output, nested repos or generated distribution copies. Subject entities
belong at root; domain-specific statuses/types remain under the owning domain.
Methods live at root and declare an owning `domain` because they may compose
metrics across several domains.
YAML mapping keys must be strings. Reject non-string keys before schema validation
so YAML's boolean/numeric key equivalence cannot silently overwrite authored data.
Date values remain normalized to ISO strings.

## Configuration

`context.config.yaml` requires `version`, `warehouse`, and `lineage_sources`.
Each source has an `id`, `type` (`dbt|sqlmesh|raw_sql|none`) and optional `repo`,
`ref`, `manifest_path`, and per-source `warehouse` override. `domains` maps domain
names to lineage. A lineage pointer is a list of `{source, models: [...]}`.
Source IDs are unique. Multi-warehouse context does not imply federated execution.

Additional configuration:

```yaml
time_tokens:
  calendar: [last_month, last_quarter, last_year, ytd, all_time]
  fiscal: [last_fiscal_quarter, fiscal_ytd]
fiscal_calendar: {year_start_month: 2}
variants: {max_per_seed: 20}
verified_sql:
  encryption: none  # explicit local-only default; use age or sops when configured
  decrypt_to: evals/verified/
  # recipients: [<public-recipient>]
```

Tokens are unique across both lists. Fiscal start month is 1–12; omission means
fiscal equals calendar. Relative execution also requires explicit as-of/boundary
semantics; an unfamiliar token must be clarified. Encryption recipients are public
keys; private identities belong in customer-controlled environment/CI secrets.
`.nodal.local.json` is unrelated local setup classification, written only by
`setup-nodal`.

## Metrics and shared fragments

Each metric file contains one object; its `name` must equal the filename stem.
Required fields are `name` and `definition`. Approval is revision-level authority state. An
expression also requires `grain`. Confirmed metrics require approval metadata.

Other fields are `aliases`, `alias_notes`, `parameters[{name,note?,default?}]`,
`lineage`, `caveats`, `common_filters`, `family`, `open_decisions`,
`temporal_kind: stock|flow|rate`, and either an `expression` or the paired
`expression_blocked_by` / `deterministic_form`. Unknown fields are rejected.

An expression contains:

- `measure`: restricted aggregates (`SUM`, `COUNT`, `AVG`, `MIN`, `MAX`),
  arithmetic, parentheses, numeric constants and `metric(name)` references.
  `metric(domain.name)` is explicitly cross-domain; bare names resolve locally.
  No SQL statements, joins, window functions, CASE expressions or execution.
- `mandatory_filters`: conjunctive filters `{field,op,value?,reason?}`, or nested
  `any_of` / `all_of` groups. Reasons explain the wrong answer being prevented.
- `entity_filters`: `{entity,having:[{measure,op,value}],reason?}`. Row filters run
  before entity grouping; preserve both stages.
- `allowed_dimensions`: confirmed slices. Omission is not unrestricted slicing.
- `ratio: {zero_denominator,reason}` on any measure containing division. Policy is
  actual YAML `null`, `zero`, or `error`; string `"null"` is invalid.
- `include_filters`: domain-local shared filter set references, expanded before
  semantic checks and removed from the normalized definition.

Column/row measures require their own lineage. Reference-only arithmetic declares
`lineage: inherit` and receives the transitive union of referenced lineage and
constraints. Overlay filters must apply on every referenced branch; dimensions
must be a subset of every referenced metric's allowed dimensions. References
must be acyclic, including metric-to-method deterministic-form dependencies.

`_shared.yaml` contains named `lineage`, `filter_sets`, and `parameters` maps.
`lineage: {shared: name}` replaces the lineage list;
`parameters: [{shared: name}]` splices parameter lists; and
`expression.include_filters: [name]` appends filters conjunctively. A filter set
is `{description?, filters: [...]}`. Names resolve only within the metrics folder.
Nested fragments, missing names, duplicate parameter names and conflicting direct
equality constraints are errors. Fewer than two distinct metric referrers warns.
Fragment diagnostics retain the metric reference field and the `_shared.yaml`
definition field in `related` locations, including errors detected after expansion.

`family: {name,discriminator,siblings}` records metrics sharing a measure and
other filters but differing on one mandatory discriminator constraint. Members
must declare the same mutual family; the constraints must differ. Family or alias
ambiguity asks the user to select a definition, never guesses a default.

Aliases live on metrics, methods and entities. Colliding metric/method aliases
within a domain require `alias_notes` on every owner; notes do not remove the
ambiguity. Glossary headings without a matching alias warn. Dependency references
use canonical names, not aliases.

`open_decisions: [{id,question,blocks}]` records unresolved choices. `blocks`
uses local/qualified metric names or `methods/<slug>`. The owner may remain
confirmed; named targets and their dependents are effectively draft. Validation
computes dependency eligibility without rewriting definitions or authority state.

For an inexpressible metric, name the unsupported construct and point
`deterministic_form` at `reference.md#pattern-<slug>` or `methods/<slug>`. The
confirmed target supplies definition coverage, not generated executable SQL.
Such metrics use optional top-level `allowed_dimensions`; expression metrics use
only `expression.allowed_dimensions`. A ratio may reference deterministic-form
components. Prose-only metrics have no deterministic definition coverage.

## Query patterns

A domain's `reference.md` may contain a few confirmed query patterns where the
exact form prevents a named wrong answer. Each has a leading `Without this:`
rationale, real lineage model/column names, and placeholders instead of report
parameter literals. It is not a runnable report or a query-log paste. Draft
patterns stay on working branches; new patterns have no status marker. Deterministic-form patterns have explicit
`<a id="pattern-<slug>"></a>` anchors. Their models must belong to domain lineage.
Pattern rationales map to filter/ratio reasons or method decisions; unmapped
paraphrases warn for review rather than claim semantic disagreement.

## Methods

`methods/<slug>.md` starts with YAML frontmatter and a Markdown body. Required
frontmatter: `name` (= slug), `kind: method`, `domain`, `aliases`,
`description`, `metrics`, `parameters`, `decisions`, `output`, `checks`.
Merge-ready methods require complete review items. Historical attribution is retained separately.

`metrics` resolve to expressions or deterministic forms. Lineage defaults to
inheritance; an explicit lineage list must be a subset of the dependency union
and cannot narrow drift coverage. A blocked/draft dependency blocks the method.

- Parameters: `{name,note,default?,dimension?}`. Every value placeholder is
  declared, and every parameter is used. `dimension: true` marks a bound slice
  such as `cohort_key`; validate it against all composed metrics.
- Constants: optional `{name,value,note}` entries for intentional business
  constants. Runtime windows and dates remain parameters.
- Decisions: `{id,rule,without_this,references?,overrides?,constraints?,alignment?}`.
  Every confirmed rationale names a failure mode. Explicit constraints are
  `{metric,filter}` using the filter grammar. A changed mandatory constraint
  requires `overrides: {metric,filter_field,reason}`. `alignment` lists the stock
  and flow metrics reconciled by this decision. Unknown temporal kinds warn.
  References to governed entity anchors, metrics or methods add dependency edges;
  a whole entity file conservatively references every entity it contains. Draft
  referenced entities block the method and its seeds, and their lineage changes
  enter the same drift review. Link existence alone does not establish readiness.
  Referenced metrics must also be declared in the method's `metrics` list.
  Constraint checks follow every arithmetic metric component's mandatory filters;
  matching one branch does not excuse changing another. Keep branch predicates
  separate rather than combining distinct populations into one filter list.
- Output: `{grain,columns,must_state,dimensions?,optional_columns?}`. Optional
  columns must be a subset of columns; decisions explain their presence.
- Checks: qualitative relationships against actual result evidence, never code
  to execute with eval and never expected business statistics.
- `not_this`: `{target,reason}` entries for adjacent resolvable concepts.
- Provenance: `{kind: interview|notebook|dashboard,repo?,path?,ref?,extracted_at?,extracted_by?}`.
  Store pointers, not notebooks or their results.

The body requires `## When to use` and `## Procedure`. Numbered procedure steps
cite decision IDs. `## Worked parameterization` and `## Known traps in this
warehouse` are recommended. Methods contain no runnable SQL/Python. Runtime
literals belong in parameter defaults/constants; dates/numbers in metadata,
citations, numbering and illustrative worked parameterizations are allowed.
Ambiguous prose requires review; it cannot establish a deterministic constraint.
Imported draft methods may have empty rationale/unresolved review items, but
malformed syntax, unsafe paths and cycles are invalid even in drafts.

## Seeds and IR

`evals/seeds/<name>.seed.yaml` requires `question`, `intent`, `domain`, `expected`,
`provenance`. Seed approval comes from reviewed merge; snapshot verification attribution remains evidence.
Provenance is `interview|dashboard|correction|generated|observed|notebook`.
Metric/method positive confirmed seeds require IR. Entity and negative seeds may
omit IR; supplied IR must still validate. No invented extraction during migration.

Exactly one IR target is present:

- Metric: `metric`, optional `dimensions`, `filters`, `grain`, `time_window`.
- Method: `method`, `metrics` (resolved for this question), `parameters` (bound
  name to value/placeholder), optional `dimensions`, `time_window`.

Evergreen time windows are declared tokens. Absolute `{start,end}` bounds require
`expected.kind: value_at_snapshot` and `as_of`, with start before end.

Expected kinds:

- `semantic_entity`: requires `entity`.
- `sql_shape`: `must_include` / `must_exclude` obligations. Methods additionally
  check output disclosures and relationships against actual result evidence.
- `value_at_snapshot`: requires `value` and ISO-date `as_of`. Tabular values are
  row objects with `key_columns` (required for multiple rows); order is irrelevant.
  Optional nonnegative `tolerance.absolute` and `.relative` default to exact
  comparison: absolute difference <= max(absolute, relative * abs(expected)).
  Nulls/non-numeric values compare exactly.
- `negative`: requires `reason: lack_data|unresolved_semantics|not_sql`. Passing
  requires an appropriate decline/escalation, not an empty SQL string or invented
  result. Report escalation accuracy separately from the positive accuracy delta.

Optional `variants` are `{text,observed_at,provenance,approver?}`. Preserve verbatim
text, but reject duplicates after Unicode normalization, case-folding and
whitespace collapse, including the seed question. Default cap is 20. Reviewed
insertion drops near-duplicates at normalized edit distance < 0.1 and otherwise
replaces the oldest at capacity. Preserve overflow/history in the local observed
archive or hosted store. Text similarity never establishes semantic equivalence.

`verified_query_file` points to ignored `evals/verified/<name>.sql`; ciphertext
is the portable committed answer key. Confirmed notebook snapshot seeds require
`verification_source: {kind: notebook,repo?,path,ref,output}` identifying a pinned
revision/content hash and agreed output. Python-only notebook verification does
not require or fabricate a SQL sidecar.

## Matching, coverage and document loading

Normalize canonical names, dimension sets, and typed recursive filter trees;
ignore filter reasons but retain values, operators, AND/OR and symbolic
placeholders. Qualify columns only with unambiguous lineage evidence. Fill omitted
metric grain from its definition. Retain time tokens but exclude them from match
identity. Method identity uses method, resolved metrics, dimensions and bound
parameter-name set; keep values for execution. Apply defaults consistently.

Manifest-backed column aliases apply to requested and allowed dimensions and to
nested filter fields. Model names and manifest unique IDs may identify the same
column; incomplete manifests or ambiguous owners cannot prove that equivalence.
Known ambiguous column spellings require clarification. Normalization never
rewrites authored metric or seed files.

Relations are `unresolved`, `ambiguous`, `equivalent`, `same_metric_new_slice`,
`decomposes`, and `related_only`. Compound questions classify each part. Resolve
ambiguity before matching. Equivalent requires identical structural identity;
different filters, grain, dimension or parameter sets are a new slice. A changed
cohort selector must also change the resolved metric set where appropriate.
Unsupported dimensions are gaps, and blocked definitions cannot be answered as
governed merely because an equivalent seed exists. Conflicting equivalent seed
expectations require review. Similarity only proposes nearby seeds.

Coverage has three separate levels: definition, slicing and verification. A
confirmed deterministic form is “defined, not expressible.” Slicing cells include
dimensions/filter/grain signatures and time tokens, plus method parameter sets.
A cross-token equivalent match does not transfer snapshot verification. Verification
separates ciphertext existence, decryptability, checked pass, missing/stale,
unknown-without-key, and human-confirmed dashboard/notebook snapshots.

Default uncovered cells come from observed demand and seed shapes, ranked by
queue count. `--all` adds zero-demand aggregate/singleton dimension x token cells
and observed/seeded dimension combinations, not an unbounded power set. Missing
queue means unknown demand. Reports include stale/orphan seeds, negatives,
variants and queue depth and never write computed statistics into context.

Structured definitions/entities are always read. The prose ladder adds:
`reference.md` for equivalent metrics; relevant `context.md` and method bodies
for new slices, decompositions or methods; company overview and terminology for
unresolved questions before escalation. Consumers without matching capability
must not claim coverage. The harness must not leak expected values, seed variants
or verified SQL into answer generation; leave evaluated seeds out of retrieval.

## Observed demand and notebook verification

`evals/observed/queue.jsonl` is ignored. Entries carry `id,text,asked_at,count,status`
and optional domain, partial IR, candidates, relation and nearest seeds. Statuses
are `pending|linked|promoted|declined`; reviewed dispositions record destination
paths. No answers, result values or user-identity fields belong in the queue.
Stage 6 reviews ambiguous/frequent questions first, eliciting choices and updating
variants, draft definitions/seeds, negative seeds or dismissals. Resume must not
duplicate promotions. Raw queue presence does not authorize context changes.

`scripts/review_observed.py list|prepare|apply|resume` separates local preview
from reviewed application. Preparation validates a complete proposed graph and
writes only a private proposal. Apply requires its reviewed digest and analyst
name, checks source revisions, and records a recoverable local transaction under
`.nodal/observed/`. New definitions/seeds and changed definitions remain draft;
an equivalent variant preserves the seed's existing approval. Overflow and
dropped duplicates remain in local history. Interrupted work must resume before
another transaction; conflicting edits are preserved for resolution. Queue
writers share its advisory lock. `scripts/match_question.py --ir` is read-only;
`--question` explicitly enables independent BYO-key extraction without seed
expectations or answer keys.

### Static notebook import

Implement `scripts/import_notebook.py` as a static drafting operation in Stage 6.
Parse cells to propose decisions, parameters, metric references and output shape;
leave every `without_this` empty for the analyst to explain and review. Never
execute cells during import or commit the notebook. Near-matching aggregations
are possible definition drift for review, not permission to replace a metric.
Store the source repo/path and pinned revision or content hash in provenance.
An imported method remains draft until a human reviews its business decisions.
Offer Stage 5 notebook validation after that review. Import completion and method
approval are separate from result verification; neither implies that the notebook
ran or that the AI reproduced its results.

The interview handoff is Stage 6 import → human method review → Stage 5 notebook
verification → human review of the comparison. Returning to Stage 5 must not
restart the interview. Present notebook verification alongside dashboard
verification as a source-specific route to a verified answer. If the analyst
defers execution, retain the draft verification candidate and record the source,
question, parameter bindings and remaining prerequisites for a later session.

### Independent notebook-to-method verification

Add `scripts/verify_notebook.py` and
`skills/context-interview/references/notebook-verification.md`. This extends
Stage 5 of context-interview, analogous to dashboard verification; it does not
add an eighth skill. The AI orchestrates two real executions in the customer's
environment: a fresh reference notebook run and an independently generated
analysis using the method. A static import or saved notebook output cannot pass
this verification. Ordinary import, validation and CI never execute notebooks
implicitly; execution uses an explicitly selected customer-controlled executor.

1. **Define the comparison.** Agree on the business question, source notebook
   revision/content hash, method revision, parameter bindings, as-of date, input
   snapshot, output tables, row keys and numeric tolerances before execution.
   Charts require their backing table. Record timezone, random seed where
   relevant, and dependency/environment versions.
2. **Rerun the reference.** Use a fresh kernel and execute the notebook's required
   cells in order against read-only, frozen or snapshot-consistent inputs.
   Preflight for warehouse writes, package installs, external side effects and
   missing dependencies. Temporary local outputs are allowed. Do not silently
   skip cells, depend on cached interactive state, or rewrite reference logic to
   obtain agreement. Block notebooks requiring unsupported mutations until the
   owner supplies a suitable read-only version.
3. **Answer independently.** A fresh answering-agent context receives the question,
   reviewed method, relevant metric/entity definitions and identical bindings and
   input snapshot. It receives no notebook implementation, reference results or
   expected seed values. It derives and actually executes its own SQL and/or
   Python. The agent that imported or inspected the notebook must not reuse that
   conversation as the independent answering context.
4. **Compare results and behavior.** Compare keys, grain, row sets, required
   columns, types, nulls and numeric values using the snapshot rules above.
   Evaluate method decisions, `output.must_state` disclosures and qualitative
   checks as separate obligations. Equal totals do not excuse a wrong cohort,
   duplicated identities or missing partial-window disclosure. Freeze agreed
   mappings and tolerances; changes after a mismatch require analyst review.
5. **Review the evidence.** Present discrepancies and limitations to the analyst.
   Distinguish import/definition gaps, AI implementation errors, reference defects
   and incomparable inputs. Correct the relevant source through review and rerun
   both sides. Only a human-confirmed match creates or promotes a confirmed
   `value_at_snapshot` seed; never adjust expected results merely to pass.

For example, after importing a retention notebook as a method, rerun the notebook
for the agreed cohort and date window, then ask a fresh AI context to answer that
same retention question using the reviewed method. Execute the AI's generated
analysis on the same inputs and compare the keyed output tables. Merely asking
the AI to rerun the original notebook twice, or to repeat its saved answer, does
not test whether the imported method preserves the analyst's reasoning.

Execution outcomes are `pass|fail|blocked|skipped`, separate from human approval.
Missing kernels, dependencies, authentication, stable inputs or extractable output
cannot pass. Mutable live inputs with unexplained changes prevent a conclusive
match. An optional context-off run is a third independent measurement, not the
reference answer. Python-only methods remain eligible; do not require or invent
a SQL sidecar for them.

Keep the reusable method's decisions and qualitative checks separate from the
snapshot's numerical answer key. A successful comparison adds a method-targeted
`value_at_snapshot` seed with the tested parameter bindings; it does not embed
notebook results in the method or replace its reusable behavioral checks. Method
snapshot grading must evaluate both result agreement and those behavioral checks.

Report the verification lifecycle explicitly:

| State | Evidence required | Effect on the seed |
| --- | --- | --- |
| Imported | Static notebook parsing only | Draft method and draft candidate seed; no verified result |
| Execution matched, awaiting review | Both fresh executions agree and method obligations pass | Record a run `pass`; the candidate seed remains draft |
| Human-confirmed match | Analyst reviews the matched outputs, interpretation and limitations | Confirm the snapshot seed with the real approver and confirmation date |
| Failed, blocked or skipped | Mismatch, incomplete execution or deliberately omitted execution | Keep the candidate draft and record the reason and next action |

For an existing confirmed snapshot, an unsuccessful re-verification must not
overwrite its historical expected value or refresh its verification date. Report
the latest attempt separately; changed dependencies make prior evidence stale.

Keep executed notebooks, generated code, row results, environment receipts and
comparison reports under ignored `evals/runs/` or `.nodal/`. Retain only source
pointers and the approved snapshot expectation in committed seeds, using
`provenance: notebook` and the `verification_source` contract above. Approved SQL,
when available, follows the encrypted verified-query lifecycle. Evidence must
identify both actual executions and their input/method/source revisions.

A match verifies only that parameterization and input snapshot. Changes to the
notebook, method, dependent metrics, parameters or relevant data require another
comparison. Local changes enter drift review; an external notebook revision is
checked when the executor next accesses its source, without implying continuous
external monitoring.

Coverage may explicitly recheck local notebook evidence with
`--notebook-run <seed>.seed.yaml=.nodal/notebook-runs/<run>/comparison.json`.
Bind the approval to the seed/context fingerprint and comparison digest, then
check the recorded local source's content hash. Changed evidence is stale and
missing evidence is unavailable; neither changes the historical seed expectation.
Ordinary coverage reports the historical confirmed snapshot with source revision
unchecked. A freshness check does not execute either analysis or supersede a
failed regression.

For the cohort-retention example, compare `cohort_size`, `returned`,
`retention_rate` and `followup_complete` by cohort and optional `cohort_key`.
Check the fixed denominator, distinct canonical customer identity,
`returned <= cohort_size`, null rate for an empty cohort, and explicit window and
cohort-anchor disclosures. Activity and acquisition anchors are separate cases.

### Quick simulated-analyst context derivation

Preserve the fast development loop represented by local `clean-test.sh` and
`skills/context-interview/references/simulated-analyst.md`: a maintainer supplies
a private knowledge brief and derives draft 0.3 context from the current working
tree without publishing a package or running the full release integration matrix.

Use the tracked `scripts/integration/clean_test.sh` harness as the implementation.
Retain an ignored local wrapper for familiar `./clean-test.sh --auto` and
`--auto=/path/to/brief.md` entry points. The direct source-checkout path is:

```bash
scripts/integration/clean_test.sh --package-source source-checkout --host claude --brief ./responses.md
```

Document the equivalent quick invocation explicitly:

```bash
./clean-test.sh --auto=/absolute/path/to/private-analyst-brief.md --package-source source-checkout --host claude
```

The bare `--auto` form uses the existing local default brief. If that brief is
missing, return an actionable instruction to supply `--auto=<path>`; do not
invent analyst knowledge. These entry points must remain available without a
package publish or a full integration-suite run.

The quick run's deliverable is the generated context repo path, valid draft
per-metric YAML and any method drafts, the interview exchange log, and a concise
list of pending human decisions and verification work. Report context derivation
separately from execution verification so a useful draft run can finish while
warehouse, dashboard or notebook validation remains pending.

Preserve host/package-source choices, `--prepare-only`, `--resume` and optional
non-interactive runs. The wrapper delegates copying, permissions and cleanup to
the tracked harness. Create a unique temporary room or reject an unsuitable
destination; never delete a caller-supplied directory.

Preserve `.sim-analyst.json` with `responses` and `log` paths, including marker
handoff when entering the generated context repo and resuming. Keep the brief
outside the interviewer's project; only a responder subagent may read it.
Ordinary interview questions, alias/family choices, method decisions and Stage 6
choices use the existing `CONFIDENT: ...` / `NOT_CONFIDENT: ...` protocol.
Uncertainty escalates to the real human, or pauses with a pending question in
non-interactive mode. Independent questions may be batched. Preserve a local
question/answer/escalation log; do not let the interviewer silently extract the
brief instead of conducting the interview.

A batch recorded as one exchange has one leading status prefix: `CONFIDENT:`
only when every item is supported, otherwise `NOT_CONFIDENT:`. Numbered content
follows that prefix. A confident header cannot mask an uncertain item. Malformed
or pending replies are not repaired by rewriting them, resetting shared state or
submitting a new simulated answer under another ID.

`scripts/simulated_analyst.py` manages marker handoff, idempotent question logs,
pending human questions and explicit human-confirmation receipts. It never reads
the brief or starts an agent. The harness passes the marker path in the launch
prompt, places it in both projects, and preserves it on resume, even when an
unanswered setup question paused before scaffolding. Non-interactive unresolved
questions exit with code 3 and preserve the room. A second simulated guess cannot
substitute for the pending human reply. Changed briefs require a new room.

Simulator-only definitions and seeds remain draft, with no invented `approver`
or `confirmed_at`, and are excluded from confirmed coverage. Explicit human
confirmation may promote individual artifacts. Draft-selection evaluations must
label these artifacts simulated. Simulation cannot attest to authentication,
notebook execution, dashboard agreement or warehouse results. Missing execution
capabilities may be skipped while still producing useful draft context, with
pending verification clearly recorded.

The quick path must distinguish a successful draft interview from a verified
analytics result: schema-valid drafts and logged exchanges can satisfy context
derivation, while unavailable warehouse, dashboard or notebook execution is
reported as pending. An unresolved business-definition question still pauses or
leaves an explicit open decision; missing execution access must not cause the
simulator to invent either an answer or a verification receipt.

Notebook import must also remain available in a quick simulated interview. The
responder can answer method-review questions from the brief, but its answers
cannot satisfy the real-human review or execution gates above. A quick draft run
must not require notebook validation, dashboard access or the full release matrix
to finish; the summary records each deferred check explicitly.

After each quick simulation launch, write a private `simulation-summary.json` in
the clean room, including paused runs before scaffolding. Include the context
path, draft metric/method paths, exchange log path, pending human questions,
open decisions and verification follow-ups. Report validation separately from
execution verification; simulation alone cannot establish the latter.

Post-run checks require draft context and logged exchanges, and reject confirmed
objects without matching explicit real-human receipts. A receipt records an
operator attestation of an already-reviewed artifact; it is not proof of identity
or external execution and never writes confirmation fields itself. Changed
confirmed artifacts need renewed review. Maintainer-operated live acceptance is
`tests/test_simulation.py --live claude|codex`; ordinary tests use a synthetic host
and do not establish actual AI interview or warehouse fidelity.

### Acceptance criteria for these changes

- Reject ACF 0.2, `metrics.LookML`, legacy `metrics.yaml`, legacy-only and mixed layouts across
  validation, compilation and ACF loading; no compatibility branch remains.
  Test converter equivalence, backups, failure rollback and actionable diagnostics.
- Prove static notebook import executes no cells and leaves review items draft.
  Test an actual synthetic reference rerun and independent method execution,
  matching/mismatching rows, duplicate or missing keys, nulls, agreed tolerances,
  method/disclosure failures and unavailable-executor outcomes. Verify that the
  answering request contains no notebook code or reference/expected results.
- Prove a numeric match alone cannot confirm a seed, and changed source/method
  revisions invalidate prior verification. Real warehouse/notebook checks remain
  opt-in customer-environment acceptance, reported separately from offline tests.
  Include one live acceptance case in which an AI actually derives and executes
  the method-based answer against the same inputs as the rerun notebook. A fixed
  fixture executor tests comparison plumbing but does not establish AI fidelity.
- Test clean-room preparation with a synthetic brief, marker handoff, resume,
  unanswered-question behavior, draft-only output and destination preservation.
  An opt-in short live simulated interview must produce valid per-metric 0.3
  context and method drafts without fabricated human or execution confirmation.
- Verify the root `/specs/` ignore rule and prove that package and clean-room
  copies exclude a synthetic file placed there. Keep root `SPEC.md` in the
  distribution. If planning files are already tracked, identify them for explicit
  index removal during implementation; an ignore rule alone does not untrack them.

## Local specifications

Keep `/specs/` in the root `.gitignore` as local planning material. Canonical root
`SPEC.md` remains tracked and distributed; on a case-insensitive filesystem,
`spec.md` and `SPEC.md` denote the same file. Exclude `specs/` from clean-room
package copies as well: an ignored directory is not automatically excluded by a
raw filesystem copy. Briefs, notebooks, credentials and local run evidence must
also remain outside copied package payloads and committed generated context.

The required ignore entry is exactly `/specs/`. If it already exists, preserve it
without adding a duplicate. This spec-only revision does not edit `.gitignore`,
remove tracked files from the index, or regenerate the skill payload; those are
implementation steps after approval.
The ignore rule applies to the root directory, not to the canonical root
`SPEC.md` or its generated distribution copy; do not use a broad `spec*` pattern.

This revision specifies future implementation work for review. Updating this
document does not authorize implementation or live notebook/agent runs.

## Verification, drift and distribution

`scripts/verified.py encrypt|decrypt` uses age or SOPS executables. `none` is
explicit local-only mode, never a fallback from encryption failure. Keep private
keys and plaintext out of logs/artifacts and restrict paths/permissions. Customer
regression commands execute read-only with customer authentication; trusted
workflows publish only seed IDs, status and sanitized categories. Missing keys,
executors, historical data or capabilities are explicit skips, never passes.

`capture --approved-input <file>` saves the analyst-approved, actually executed
SQL and encrypts in the same operation. A crypto failure returns
`local_unpublished` and retains the local file; it does not refresh any older
ciphertext. Both backends accept configured public age recipients; SOPS stores
the encrypted binary payload in JSON. Plaintext filenames use letters, digits,
underscores, dots and hyphens, starting with a letter/digit/underscore.
`decrypt_to` stays under ignored `evals/verified/` without traversal or symlinks.
`probe --check-decryption` is an explicit capability check, never a query run.

`scripts/regress.py` replays approved SQL with a customer executor and optional
local semantic judge. It is a separate one-shot operation from inject-mode AI
evaluation. Temporary plaintext is removed on failure as well as success.
`verified-regression.yml` is manually dispatched on the default branch, uses a
protected customer environment, and always removes its owned temporary checkout
and identity material. It never runs fork PR code with keys or publishes raw
query/results artifacts. `.ci/coverage.py --regression-run <local-evidence>`
checks seed/definition/config/query revisions before reporting a checked pass;
existence or decryptability alone does not prove result fidelity.

Drift follows the transitive definition graph across domains, methods, patterns
and seeds. The trusted workflow appends a block to the independent authority ref
before creating a repair proposal. Definition files are not the stale-state store.
No automatic re-grade, status edit, or unrelated merge clears a block. Re-grading
records verification evidence only; `--restore` is rejected. Repair clearance
requires reviewed merge and fresh checks and names the original block and exact
repair revision. Protected descendants may inherit a clearance only with proved
ancestry and unchanged affected definition/dependency/prose/config digests.
Source/config/schema changes invalidate applicable evidence.
Legacy status patch tools are conversion aids only, not an approval mechanism.

Canonical sources are root SPEC, schemas, template, CI, scripts, workflows and
runtime packages. `skills/context-interview/` contains generated distribution
copies. Edit canonical sources and run `scripts/sync_skill_payload.py --write`
then `--check`. Fresh scaffolds use 0.3; upgrades preserve authored content,
config, approvals, local evidence and `.ci/lineage-baseline.json`. Older versions
require explicit migration before support-file upgrades. No commit/push/publish
or global agent configuration change occurs without the user's request.

An upgrade writes a private `.nodal/migrations/scaffold-<hash>.md` review report
for preserved files that differ from incoming fresh templates. This comparison
includes customer edits because the previous template baseline is unknown; it is
not an automatically applicable migration patch. Missing authoring stubs are
reported without being recreated. Never temporarily overwrite the existing
lineage baseline during a support copy; it must survive a failed copy as well.

## Question attribution through analytics planning

This section explains commit `70c79ce` (plugin 1.6.4), “Preserve business
question attribution through analytics planning.” It specifies optional runtime
behavior in `skills/analytics-plan/SKILL.md`; it does not introduce ACF fields,
change the directory contract, or change which definitions count as confirmed.

### Problem and intended outcome

An analytics conversation often ends its planning phase with “yes, continue.”
If capture uses only the latest message, the resulting SQL can be attributed to
that acknowledgment instead of the substantive business question. Clarification
can also change the interpretation, while delegation can split one request
across several agents and SQL calls. A session ID alone cannot express those
relationships.

For example, “What was retention last year?” may become an approved
interpretation of “2025 retention for the agreed customer population.” After
approval and delegation, each query should retain the original wording, the
approved interpretation where permitted, and its assigned references. An
acknowledgment must not replace the business request.

The goal is to let an analyst follow SQL capture back to the question and plan
it served, and then locate the originating client conversation when available.

### Decisions and their reasons

| Decision | Reason |
| --- | --- |
| Copy the original request verbatim into advertised `_nodal_user_question`. | Preserves the user's wording across clarification and approval; reconstructing it from SQL could silently change intent. |
| Put the approved interpretation in `analysis_context.effective_question`. | Keeps the original request distinguishable from the interpretation used for execution. |
| Use supplied analysis/question/plan IDs and revisions only. | Invented IDs look authoritative but cannot reliably join to registered records. Missing references should remain missing. |
| Keep the plan revision fixed for its executions. | A later plan change must not silently reinterpret earlier queries. |
| Pass explicit assignments to children. | Parallel agents may serve different questions, and one query may serve several; a global last-question value would mix unrelated work. |
| Copy native session/turn/agent IDs only when supplied in scope. | Provides conversation correlation without guessing identifiers or accessing transcripts. |
| Apply attribution only when the tool advertises the fields. | Supports existing SQL tools and integrations without requiring every connector to implement attribution. |

The parent passes each child the original request, approved interpretation,
plan revision, and assigned question references. Children preserve their own
native agent IDs and supplied parent lineage. Unknown context is omitted rather
than borrowed from another task or inferred from private reasoning.

### Responsibility and trust boundaries

The plugin guides model behavior. The gateway advertises and strips cooperative
arguments, enforces its storage controls, and emits capture metadata. Query Hub
owns registration, immutable revisions, authenticated ownership, and reference
validation. These responsibilities avoid making the plugin a credential holder
or a second registry implementation.

The skill must not claim a supplied reference is validated or that reported
approval independently proves human approval. It must not read or transmit
transcripts, transcript paths, working directories, or private reasoning for
attribution. A native conversation ID is a locator, not permission to access a
conversation. Question text is supplied only when the advertised schema permits
it; gateway retention remains the enforcement boundary.

### Compatibility and remaining limits

The package manifests and marketplace entry were advanced together to 1.6.4,
with a matching package test and changelog entry, so both client distributions
identify the same guidance release. ACF itself is unchanged.

Model cooperation can still omit or miscopy fields. Existing analyst MCP tools
do not automatically register the new question/plan records; callers must
supply actual registry references. The guidance does not guarantee transcript
availability, reference validation, warehouse execution, or approval attestation.

Validation for the commit covered the 16 executable test files, skill lint,
schema validation, distribution synchronization, and strict plugin validation.
These checks establish package consistency; live Claude/Codex acceptance still
needs the original request → clarification → approval → delegation → SQL →
capture → local resume path, including concurrent questions and missing IDs.

Disabling optional gateway attribution or client-ID retention lets existing
analytics planning continue. Registry and deployment details belong to Query
Hub's `docs/analysis-context.md` and the gateway's
`docs/question-attribution.md`.

## Approval through merge (normative)

Context is proposed until its exact revision is merged into the designated
`approval_branch` (`main` by default) through enforced human review and checks.
A branch name, a local `status`, a passing test, or a copied receipt is insufficient.

### Authority setup (maintainer-operated)

1. Protect the approval branch: require at least one human review, CODEOWNER
   review, dismissal of stale reviews, strict `validate` and `approval-policy`
   checks, and all applicable behavior checks. Enforce on administrators; disable
   force pushes, deletion and review bypass. Add the context owners to CODEOWNERS.
2. Create a separate `acf-governance` branch containing `state.json`:
   `{"approval_branch":"main","events":[],"freshness":{}}`. Restrict writes to
   the governance service identity. Set `ACF_GOVERNANCE_WRITER` on consumer
   hosts and as a repository variable to that single service login or GitHub App
   slug. Enforce state-ref restrictions for administrators too. The live reader
   verifies these restrictions. Context authors and ordinary workflow tokens
   must not be able to update/delete/force-push this ref. Keep its Git history.
3. Provision the service identity through GitHub's own credential facilities.
   `ACF_GOVERNANCE_TOKEN` needs contents writes and read access to branch
   protection, PR reviews and checks. Nodal does not provision credentials.
   Restrict its use to the trusted approval and drift workflows. Protect workflow
   changes with CODEOWNERS. Both `nodal-governance` and `nodal-governance-repair`
   environments permit only the approval branch. The repair environment requires
   human review for clearance; routine merge recording needs no second approval.
   Drift revocations run promptly
   without waiting for repair approval. Set `ACF_APPROVAL_BRANCH` if not `main`.
4. On consumer hosts, install trusted tooling outside authored context. Set
   `ACF_GOVERNANCE_REPOSITORY=owner/repo` and `ACF_GOVERNANCE_COMMAND` to a JSON argv
   array with an absolute executable, for example
   `["/opt/nodal/bin/python","/opt/nodal/scripts/governance_github.py","read"]`.
   `gh` manages authentication. Never source commands from a context repository.

An absent authority, inaccessible protection settings, missing source checks,
expired checks, dirty content, or an unrecognized revision blocks governed use.
The reader also checks that the latest source workflow completed and published
its state; pending checks or failed publication block use immediately.
The reader always fetches live state; there is no offline approval fallback.
Local copies must retain their approved Git commit and exact content. Exports
carry deterministic generated files (independent of build date and checkout name)
and `governance.json` identifying the revision, content hash, approval event,
ledger head and freshness evidence. They are snapshots, not perpetual approval:
consumers must run `scripts/compile_skill.py APPROVED_SOURCE --verify-export EXPORT`
(using the original `--name` override if any) to recheck the live authority and
recompile/compare exported files before
using them as governed guidance. The skill evaluation adapter requires
`ACF_EXPORT_SOURCE` pointing to that approved checkout, or explicit branch-test
mode, for ACF exports. Plain exported text cannot enforce revocation.

### Detection and repair

`context-drift` writes an append-only block event to the authority ref before
publishing any repair proposal. It records target IDs, source evidence, revision
and reason. Dependency propagation blocks metrics, methods, patterns and seeds.
A source that cannot be checked blocks use too. Periodic source checks expire in
24 hours; live authority responses expire in five minutes. Source checks run on
each approval-branch push as well as dispatch and schedule, so a merge does not
wait for the six-hour scheduled refresh. Dispatch source
changes promptly; no system can detect changes that have not been reported.

Merge the reviewed repair, run fresh applicable behavior/source checks, then run
`context-approval` manually with the block ID, repair reason and passing checks
URL. Its protected environment requires human approval. The clearance names the
block and exact reviewed repair revision. It cannot clear a different block or
approve an older revision. A later protected merge inherits an existing clearance
only when the authority proves Git ancestry and the affected definitions,
dependencies, domain/company prose and configuration retain identical digests.
Changes to that scope require fresh review and clearance. An unrelated merge
never clears an uncleared block. Preserve every event and source record.
Repeated detection can create additional blocks; each must be addressed.

Consumers still reject missing approval/freshness evidence for the revision.
With valid authority evidence, eval and export exclude blocked definitions and
their dependents individually while retaining unrelated eligible definitions.
Unstructured prose from affected domains is withheld; domains with no eligible
definitions are omitted. Blocked seeds are excluded individually. Re-grading explicitly tests
proposed context without granting approval. CI regression workspaces preserve
the exact commit identity without copying Git credentials or plaintext SQL;
skipped execution returns a nonzero check result.

### Authoring and tests

Use a named working branch for interview, notebook and simulator output. New
objects have no authored `status`. Interview decisions and verification receipts
remain evidence; only reviewed merge grants definition approval. Query/notebook
verification is separate and may be missing, failed, or outdated even when the
definition is approved.

Use `.ci/validate.py --branch-test --require-ready` before merge. Consumers and
regression tools expose `--branch-test`; the eval adapter accepts
`branch_test=True`. `ACF_BRANCH_TEST=1` is an explicit process-wide test mode for
customer harnesses. This mode permits proposed definitions but never claims
approval or live freshness. Reports and exports identify it. Do not set it for
production answers. Dependency and structural failures remain failures.

Legacy conversion is `scripts/migrate_approval.py ROOT --admit-legacy` after the
owner authorizes admission of existing drafts. The converter retains original
fields in `review_history` and creates backups. Without that option it refuses
legacy drafts. Remove backups from the review tree before merging. The conversion
itself does not publish authority evidence. The repository owner has authorized
admission of the legacy content in this package's 0.3 migration; customer
repositories require their own explicit authorization. Existing history stays in
Git. Legacy fields accepted during conversion never grant live approval.

### Runtime compatibility

The format-neutral harness retains `effective_status: confirmed|draft` as an
eligibility wire field, not authored approval. `approval_state` is separately
`approved`, `proposed`, or `unavailable`; all reports carry governance mode.
Branch-test eligibility never proves approval. Deprecated authored statuses are
accepted only as migration input: legacy drafts block until explicitly converted,
and legacy confirmed fields cannot bypass the live authority. New authored
objects omit status; `review_history` preserves converted attribution.
