# Notebook verification (Stage 5)

Use this when a method was imported from a notebook or the analyst names a
notebook as the reference for a method answer. Import is static drafting; this
stage requires actual execution. Reuse the dashboard verification discipline:
agree on the case, obtain independent evidence, reconcile differences, and ask
the real analyst to confirm a matched snapshot.

## Before running

Review the imported method's decisions and every `without_this` with the analyst.
Resolve its metrics, parameters, grain, output columns, keys, missing-value rules
and disclosures. The method and dependencies must be confirmed and unblocked.
Static extraction, a simulated analyst answer or plausible saved notebook output
cannot provide confirmation or execution evidence.

Pin the source notebook and method revisions. Agree on the question, parameters,
as-of date, immutable data snapshot/frozen inputs, timezone, random seed, output
table, row keys and numeric tolerances before seeing the answer. A chart needs
its backing table. Output mappings belong in the reviewed executor or notebook,
not an ad hoc transformation chosen to hide mismatches.

Keep the case JSON, executor configuration and receipts in ignored `.nodal/`.
Example case shape (illustrative, not business data):

```json
{
  "parameters": {"window": "last_month"},
  "as_of": "2026-10-01",
  "input_snapshot": "customer-owned-immutable-snapshot-id",
  "inputs": {"dataset": "customer-owned-read-only-input-locator"},
  "timezone": "UTC",
  "random_seed": 42,
  "output": "result_rows",
  "key_columns": ["cohort_label"],
  "tolerance": {"absolute": 0, "relative": 0}
}
```

Parameters must match the method's declared bindings (defaults are applied).
For methods composing several metrics, add `metrics: [<canonical-reference>, ...]`
to select the metrics resolved for this question and parameterization. Do not
include unused alternatives merely because the method lists them. A single
composed metric is filled automatically. Dimension bindings must be allowed by
each selected metric.
`inputs` are customer-approved data inputs, never reference results, notebook
implementation or expected seed values. Immutable snapshot IDs identify the
actual data used; they are not a substitute for ensuring both executions use it.

## Independent runs

Run `python3 scripts/verify_notebook.py --root <context-root> run <notebook>` with
`--method`, `--question`, `--case` and explicit executor commands. Each command
is a JSON argv array, passed without a shell. Use absolute executable/script paths
because each process starts in its own private evidence directory.

- `--reference-command`: preflight and rerun the pinned notebook in a fresh kernel,
  in order, with the agreed bindings and read-only data access. No hidden state,
  cached outputs, silent cell skipping or altered reference logic.
- `--answer-command`: launch a fresh independent answering agent with only the
  supplied question, method/metric/entity context and input bindings. Derive and
  execute SQL and/or Python. Do not reuse the importing interviewer's conversation
  or give this agent access to the reference workspace, notebook or seed answers.
- `--judge-command`: independently review the method decisions and disclosures
  against the generated implementation and actual results. It is separate from
  the answering process. Missing semantic judgment means partial checks only,
  never full verification.

These are trusted customer executors: they enforce read-only credentials,
input-snapshot consistency and fresh agent sessions. The Nodal subprocess wrapper
is not an OS sandbox, and an attestation from an untrusted executor is not proof
of execution. Configure process/container/tool access so the answering agent
cannot retrieve the notebook or reference outputs. Nodal never collects or stores
credentials. Keep executor settings local; do not bundle an MCP server.

The optional `scripts/notebook_reference.py` implements the reference side for
owner-reviewed Python notebooks using `nbformat`, `nbclient`, `ipykernel` and
`sqlglot`. Its command must include `--read-only-environment --immutable-input`
only after the owner establishes those conditions. It creates a local kernel
specification without changing host configuration, clears stored outputs and
restarts execution. Bindings replace literal assignments in one cell tagged
`parameters`; `acf_inputs` supplies the agreed input mapping. The selected output
must be a public variable containing JSON row objects or a pandas DataFrame.
It records an executed notebook locally. Conservative preflight blocks known
writes, unsafe magics and dynamic SQL; it is not a security sandbox. Unsupported
notebooks need an owner-reviewed read-only version or a customer executor.

## Executor protocol

Every executor reads one JSON object from stdin and writes one JSON receipt to
stdout. Diagnostic output belongs on stderr. Requests carry
`protocol: nodal-execution/1`, a unique `request_id` and a `role`.
On timeout the wrapper terminates the executor's process group. Executors must
keep subprocesses in that group or arrange reliable cleanup of detached jobs;
the built-in reference executor keeps its kernel in the group.

Reference and answer requests include the same `parameters`, `inputs`,
`input_snapshot`, `input_fingerprint`, `as_of`, `timezone`, `random_seed`,
`context_hash`, `resolved_metrics` and `require_read_only: true`. Only the reference receives
`notebook`, `source_hash` and `output`. Only the answer receives `question` and
`context`. The reference fingerprint is opaque to the answering process; it does
not contain notebook code or expected values. Neither executor may fetch hidden
information merely because both processes run on the same machine.

Successful execution receipts require:

- The matching `request_id`, `status: ok`, `input_fingerprint`, `as_of` and
  `context_hash`.
- `executed: true`, `read_only: true`, `fresh_session: true`,
  `immutable_input: true`, a nonempty `session_id` and an `environment` version
  map. Reference and answer session IDs must differ.
- `rows` as JSON objects and `columns` listing exactly the columns in every row.
  Empty results still need explicit columns. Nonfinite numbers are invalid JSON.
- Reference: matching `source_hash`.
- Answer: `reference_access: false` and `answer` containing `outcome: answer`,
  actual executed `sql` and/or `python`, `explanation`, `disclosures` and
  `assumptions` as appropriate. Model-written result claims cannot replace rows
  returned by the execution adapter.

If an execution cannot run, return `status: blocked|skipped` with the request ID;
do not invent rows or receipt attestations. The wrapper records detailed receipts
locally and publishes only a status/report path. A judge request has `evidence`
and `obligations`; its receipt has the request ID, `status: ok`, and
`verdict: {passed: true|false, reason: "..."}`. An unavailable/invalid judge is
skipped. A judge must fail an obligation whose evidence does not establish it.

## Reconciliation and confirmation

After a Stage 6 import, return directly to this flow once the human has reviewed
the method; no interview restart is needed. If the analyst defers the run, retain
the source pointer, question, known bindings and missing prerequisites in an
ignored `.nodal/notebook-candidates/<method>.json` case. Do not manufacture a
snapshot value to make a deferred candidate into a seed.

The comparator checks keyed row sets, columns, nulls, types and numeric values.
Duplicate or missing keys cannot pass. It also grades method decisions,
disclosures, required output structure and qualitative checks separately. A
matching number cannot excuse the wrong cohort, identity rule, denominator or
partial-window disclosure. Empty results with no declared schema are incomplete.

Read the ignored `comparison.json` and both execution receipts. Report
`pass|fail|blocked|skipped` honestly. Explain discrepancies as candidate definition,
implementation, reference or data problems; review changes and rerun both sides.
Do not widen tolerance or edit expected output to make an answer pass.

After the real analyst reviews and confirms a passing comparison, run:

```bash
python3 scripts/verify_notebook.py --root <context-root> confirm <comparison.json> \
  --seed-name <name> --approver <actual-human> --confirmed-at <YYYY-MM-DD>
```

This creates a new confirmed notebook snapshot seed and a local approval receipt.
It refuses existing seed files and stale source/method/dependency revisions.
Ordinary execution never promotes seeds automatically. Simulation cannot supply
the human approval. If the independently executed SQL is a complete approved
replay query, add `--approved-sql <local-file>` to confirmation. Its bytes must
match the executed answer's SQL; the tool captures/encrypts it in the same
operation and reports `encrypted`, `local_only` or `local_unpublished`. Follow
`verified-sql.md`; repair crypto failures before claiming portability. SQL needing
subsequent Python transformations is not a complete replay query by itself.
Python-only methods do not require a fabricated SQL sidecar.
The new seed targets the method and records the tested bindings. Keep the
method's reusable decisions, disclosures and checks in place; snapshot grading
requires both numerical agreement and method fidelity. Do not copy results into
the method body or replace behavioral checks with a matching total.

The pass applies to the selected parameterization and data snapshot. Changed
source, decisions, metrics, input data or parameters require another comparison.
Reverification belongs in the Stage 5 queue. An optional context-off measurement
is a third independent execution, not the notebook reference. Keep all notebooks,
code, raw rows and reports outside context prompts and committed payloads.

To recheck a confirmed snapshot against its local approval, current context and
source notebook bytes without executing anything:

```bash
python3 .ci/coverage.py --notebook-run '<seed-name>.seed.yaml=.nodal/notebook-runs/<run>/comparison.json'
```

This explicitly reads the notebook source path recorded in that local report.
Changed source/context/seed evidence is stale; missing source or approval evidence
is unavailable. It never overwrites a historical expectation or confirmation.
Without this option, coverage labels the committed human-confirmed snapshot and
reports `source_revision_checked: false`; it does not claim fresh external source
monitoring. A passing source check cannot erase a failing SQL regression. Re-run
Stage 5 when results need verification; this command checks evidence freshness only.

## Local validation

The direct notebook tests cover static import, request isolation, comparison and
promotion with synthetic offline executors. A separate opt-in check executes a
real synthetic notebook kernel:

```bash
python3 tests/test_notebooks.py --kernel
```

This proves fresh reference execution and comparison plumbing with a deterministic
test answer/judge. It does not establish live AI, warehouse or customer notebook
acceptance, which remain explicit customer-environment checks.
