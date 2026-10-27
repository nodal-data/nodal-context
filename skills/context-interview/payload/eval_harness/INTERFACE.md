# Eval harness interface — NCR v2

The harness is format-agnostic. Adapters translate context into plain normalized
records; matching, coverage and grading operate on those records. ACF is one
adapter. Unsupported capabilities must be reported explicitly.

## Inputs and normalized representation

`--adapter acf|ktx|dbt|raw|skill` selects an implemented adapter. Non-ACF adapters
may provide only context text. Attach external ground truth with `--seeds <dir>`;
seed domains must correspond to the chosen context source.

`eval_harness/ncr.py` defines `NCR_VERSION = 2`:

- `context_by_domain`: domain-to-text fallback for all adapters.
- `seeds`: question, domain, intent, expected obligations, provenance, stored
  status, optional IR and path. v2 adds approvals, variants, verification pointers,
  effective status and blockers.
- `definitions`: optional canonical metric/method records with aliases,
  dimensions, parameters, dependencies, lineage, method decisions/output/checks
  and effective eligibility. Optional `time_tokens` declares the allowed relative
  window vocabulary; an empty list accepts no relative token, while omission
  means this adapter supplies no vocabulary constraint. ACF supplies its config
  tokens so extraction, matching and coverage reject unknown tokens consistently.
  Optional `column_aliases` maps proven equivalent column spellings to one
  qualified form; `ambiguous_columns` lists spellings with multiple known owners.
  Normalize both requested and allowed dimensions through that map, including
  nested filter fields. ACF supplies evidence only from complete, unambiguous
  manifest lineage; missing evidence never licenses guessed qualification.
- `context_components`: optional definitions/reference/reasoning/orientation
  components for the relation-driven document ladder.
- `capabilities`: explicit `matching`, `methods` and/or `coverage` support.
- `diagnostics`: adapter-reported issues; unknown capability is not success.

`Seed.eligibility` uses effective status when present, otherwise stored status.
The confirmed baseline excludes draft/blocked seeds. `--status draft` is an
explicit draft/simulated measurement and is labeled accordingly. ACF discovery,
fragments, path rules and approvals belong in its adapter and `acf_runtime/`.
Generic adapters need not import ACF. The ACF 0.3 adapter rejects earlier versions
and legacy single-file metric wrappers immediately.

The external seed loader rejects duplicate mapping keys (including conflicting
YAML merges), non-string mapping keys and cyclic values instead of silently
choosing ground truth. YAML date/timestamp values normalize to ISO strings for
portable matching and JSON prompts. These parsing rules do not require external
seed sources to adopt ACF configuration or approval schemas.

## Answering and routing

When matching is supported, inject mode independently extracts question IR from
the question and definitions. It excludes the evaluated seed and its variants
from retrieval. Unsupported adapters keep their ordinary context text and do not
claim ACF routing/coverage. Ambiguous or unresolved semantics are surfaced.

Generation receives the question and, for context-on, appropriate governed
context. It never receives expected answers, verified SQL, grading-only seed
obligations or answer-key variants. Method decisions and output requirements are
legitimate context. Aliases suggest candidates; structural IR and reviewed
semantics determine relations. Text similarity cannot prove a match.

Answers carry `outcome: answer|escalate|decline`, proposed `sql` and/or `python`,
assumptions, explanation, disclosures and an escalation reason when applicable.
Proposal generation cannot claim execution. Negative answers must give the
expected reason (`lack_data|unresolved_semantics|not_sql`) without executable
analysis or fabricated results.

## Grading and reporting

`grader.py` grades separate components:

| Obligation | Evidence |
|---|---|
| SQL shape / entity | Code plus an explicit judge |
| Method decisions | Implementation and declared decisions |
| Required disclosures | User-facing explanation/disclosures, not code alone |
| Output structure | Actual rows and declared columns |
| Method relationships | Actual rows; narrow deterministic comparisons or explicit judge |
| Snapshot | Actual execution at pinned `as_of`, keyed rows/scalar and tolerance |
| Negative outcome | Correct escalation/reason without invented results |

Qualitative checks are never evaluated as arbitrary Python. Typed snapshot
comparison distinguishes booleans from numbers and nulls from zero; nonfinite
numbers are invalid. Multiple rows need unique declared keys, and row order is
irrelevant. Numeric tolerance is `max(absolute, relative * abs(expected))`, with
both tolerances defaulting to zero. Other values compare exactly.

An overall pass requires every required component to pass. Missing execution,
judge capability or valid verdict is skipped. Partial method results remain
visible without claiming full verification. Positive on/off delta uses only
paired, fully scored positive seeds. Negative escalation accuracy has separate
on/off denominators excluding skips. Reports show skipped counts, routing
uncertainty and truncation. Human ground truth is the target, not an automatically
measured “perfect 100%” result.

## Execution modes

- **Inject** (`python -m eval_harness.run`): one generation per condition, with
  optional independent IR extraction and separate grading calls. No warehouse or
  implicit execution. Numeric checks skip without actual execution evidence.
- **Interactive Stage 5**: customer read-only answers reconciled with a dashboard
  or independently rerun notebook. A real human confirms evidence before snapshot
  promotion. Notebook import alone is drafting.
- **Customer regression** (`scripts/regress.py` for ACF): replay approved query
  answer keys with explicit customer executors and pinned snapshots. This checks
  replay fidelity, not a new AI answer or context uplift. It bundles no database
  connector, hosted service or credential acquisition.

Notebook verification separately orchestrates a reference notebook, independent
method-derived answer and explicit semantic judgment. Customer executors enforce
fresh agent sessions, read-only access, input consistency and reference isolation;
subprocess separation is not an OS sandbox. See the context-interview notebook
verification reference and `scripts/verify_notebook.py --help`.

## Approved-query executor contract

A customer command is a JSON argv array, launched without a shell in a private
workspace. It reads one JSON request from stdin and returns one JSON receipt to
stdout. Other diagnostics go to stderr and remain local. Models cannot invent
these execution receipts.

Requests contain:

```text
protocol: nodal-execution/1
request_id: unique invocation ID
role: regression
seed_id: canonical seed ID
query_path: private temporary plaintext filename
query_hash: sha256 of exactly the query bytes
warehouse: single resolved customer warehouse
parameters: reviewed bindings
parameters_hash: digest of bindings
as_of: pinned snapshot date or null
require_historical_snapshot: boolean
require_read_only: true
```

No expected value, grading obligation or private identity content is included.
Successful actual execution returns:

```text
request_id: matching ID
status: ok
executed: true
read_only: true
query_hash, warehouse, parameters_hash: actual matching execution bindings
rows: array of JSON row objects
columns: unique column names in every row, including for an empty result
as_of: actual pinned date when requested
historical_snapshot: true only if historical inputs were actually used
explanation, disclosures, assumptions: optional actual method answer evidence
```

Never assert historical execution just because the request asks for it.
Unavailable history, permissions or execution returns `status: skipped|blocked`
with the request ID. Do not substitute current data. Scalar expectations require
exactly one row/column, object expectations exactly one row; keyed array
expectations use declared keys. Model claims cannot replace executed rows.

The package parses SQL and rejects writes, mutating CTEs, multiple statements,
unsupported syntax/dialects and unbound angle-bracket placeholders. Parsing cannot
prove arbitrary SQL functions harmless. Customer database privileges are the
read-only boundary. Cross-warehouse definitions are unsupported by this contract.

An optional judge command receives `role: judge`, `evidence` and `obligations`,
and returns the request ID, `status: ok`, and
`verdict: {passed: boolean, reason: string}`. SQL, rows and judge evidence stay
local; a remote judge requires the customer's explicit choice. No judge runs
implicitly during validation, coverage or crypto probes.

`scripts/regress.py` stdout contains only seed IDs, `pass|fail|skipped` and
sanitized categories. Exit codes: 0 all selected checks pass; 1 a failure;
2 configuration error; 3 skipped/incomplete or no checks. Private receipts live
in ignored `.nodal/regressions/<run>/`. Owned temporary plaintext is removed on
success/failure; local tools never delete caller-provided identity files.

The manually dispatched `verified-regression.yml` uses a trusted default-branch
checkout and protected customer environment. It creates an owned temporary
checkout/identity workspace and removes it in an always-run cleanup step. An
unconfigured executor is explicitly skipped. Only sanitized statuses reach the
job summary; no raw artifacts or PR comments are published. Ordinary PR
validation and inject eval neither decrypt nor execute warehouse SQL.

## Coverage, portability and hosted operation

Coverage separately reports definition, slicing and verification. Availability,
ciphertext existence, decryption and checked pass are distinct. Historical
human-confirmed dashboard/notebook snapshots are separately identified. Local
regression receipts apply only while seed/definition/config/query fingerprints
match; stale receipts cannot establish a current pass.

Approved plaintext stays ignored under `evals/verified/`. Public recipients and
`encryption: age|sops|none` are customer config. Portable `.sql.age`/`.sql.sops`
artifacts are never answering context. Explicit `none` is local-only; encryption
failure is local/unpublished and never silently downgraded. Private identities
stay in customer files or protected CI secrets. Recipient rotation does not
retroactively re-encrypt git history.

Open-source includes adapters, matching/coverage/grading, one-shot inject and
customer regression, interactive dashboard/notebook verification and customer
workflows. Hosted ingestion, scheduling, history, observability and managed
reconciliation remain separate. Local tools do not imply hosted services ran.

## Versioning

NCR is pre-1.0 and may change between minor releases. Pin the repo revision for
third-party adapters. v1 added metric IR; v2 adds methods, explicit capabilities,
approvals/effective eligibility, variants and verification metadata while retaining
text-only adapters. ACF 0.3 and plugin semver are independent version streams.
