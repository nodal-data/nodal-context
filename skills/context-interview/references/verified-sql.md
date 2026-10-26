# Approved SQL: local capture, encryption and one-shot regression

Use this within Stage 5 after the real analyst has reviewed the comparison and
approved the executed SQL. The query is an answer key, never analytics context or
an input to answer generation. Encryption does not establish business approval or
correctness; it makes an already reviewed answer key portable.

## Configure the lifecycle

Fresh repos use explicit local-only mode:

```yaml
verified_sql:
  encryption: none
  decrypt_to: evals/verified/
```

For portable keys, the owner installs `age` or `sops`, sets `encryption` to that
backend, and supplies public age recipients in `recipients`. Both adapters use
the configured age public recipients; SOPS wraps the SQL as an encrypted binary
payload in JSON. No package code generates cryptographic identities, implements
cryptography or asks the analyst to paste private-key text. Obtain a filename
for a customer-managed identity or use the customer's CI environment.

`verified_query_file` stays `evals/verified/<name>.sql`; derive the portable
ciphertext as `<name>.sql.age` or `<name>.sql.sops`. Use a filename beginning with
a letter, digit or underscore and containing only letters, digits, underscores,
dots and hyphens before `.sql`. `decrypt_to` must stay under `evals/verified/`.
Traversal and symlink paths are rejected. Plaintext writes are atomic and private.

## Capture and encrypt in the verification operation

Once the analyst approves the actually executed query, use:

```bash
python3 scripts/verified.py capture --root <context-root> \
  --file evals/verified/<seed-name>.sql --approved-input <local-executed-sql-file>
```

This writes approved plaintext and immediately invokes the configured encryption
backend. Record `verified_query_file` on the reviewed seed. Read the returned
status before describing the artifact:

- `encrypted`: ciphertext was created; it is eligible for the normal review and
  commit process after ignore rules are checked. Nothing is committed automatically.
- `local_only`: `encryption: none` was deliberately chosen. The answer key is
  local and will not survive a clean clone.
- `local_unpublished`: plaintext was saved, but encryption failed. Preserve it
  locally, explain the sanitized failure category, and repair encryption before
  claiming portability. An older ciphertext may still exist; it has not been
  refreshed and must not be presented as the new approved query.

Invalid configuration, missing executables, crypto failures, unsafe paths,
conflicts and I/O failures are distinct diagnostics. There is no fallback from
broken encryption to `none`. `--overwrite` is required to replace differing
plaintext or an existing ciphertext. Do not overwrite unrelated authored files.

Explicit maintenance commands are:

```bash
python3 scripts/verified.py encrypt --seed evals/seeds/<name>.seed.yaml
python3 scripts/verified.py decrypt --seed evals/seeds/<name>.seed.yaml --identity <customer-key-file>
python3 scripts/verified.py probe --seed evals/seeds/<name>.seed.yaml
python3 scripts/verified.py probe --seed evals/seeds/<name>.seed.yaml --check-decryption --identity <customer-key-file>
```

The seed selector may be replaced with `--file evals/verified/<name>.sql`.
Decryption never prints SQL. A probe without `--check-decryption` only inspects
availability. An explicit decryption probe checks in memory without publishing
plaintext. age accepts `--identity` or a customer-set `NODAL_AGE_IDENTITY` filename;
SOPS also supports its customer-managed `SOPS_AGE_KEY_FILE` environment. These
are paths, not private-key text in an agent conversation. Subprocess errors are
sanitized rather than echoing potentially sensitive backend diagnostics.

## Ignore rules and recipient rotation

Upgrades preserve authored `.gitignore`; therefore existing repos need an
explicit review of their ignore rules. The old blanket rule hides ciphertext
too. Keep plaintext ignored and add the ciphertext exceptions after that rule:

```gitignore
evals/verified/*
!evals/verified/.gitkeep
!evals/verified/*.sql.age
!evals/verified/*.sql.sops
.nodal/
evals/runs/*
!evals/runs/.gitkeep
```

Use `git check-ignore --no-index` to verify plaintext/temp evidence are ignored
and the two ciphertext suffixes are eligible. Keep temporary identities outside
the repo or inside the caller's private CI workspace. Do not add private keys.

When recipients rotate, decrypt with an existing authorized identity, update the
public recipient list, and explicitly re-encrypt the approved SQL with
`encrypt --overwrite`. Review the new ciphertext. This does not remove access to
old ciphertext in git history; history is not retroactively re-encrypted.

## Customer-run regression

`scripts/regress.py` replays approved answer keys with a trusted customer executor.
It is a one-shot check, not hosted scheduling/history and not a context-on/off AI
generation measurement. It adds no warehouse drivers or credential acquisition.

```bash
python3 scripts/regress.py --root <context-root> \
  --executor '["/absolute/customer-executor", "--read-only"]' \
  --identity <customer-key-file>
```

Use repeated `--seed` selectors to bound the run. Optional `--parameters` is a
local JSON file mapping canonical seed IDs to reviewed binding objects. Method
seed bindings and definition defaults are applied; unresolved or extra bindings
are skipped. Optional `--judge` is a JSON argv command for local semantic grading.
Without it, snapshot numeric checks can run, while shape/method semantic checks
remain explicitly incomplete. The generic executor protocol is in the generated
repo's `eval_harness/INTERFACE.md`.

The runner decrypts only for the selected execution, rejects writes/multiple
statements before calling the executor, and removes its temporary plaintext even
on failures. Customer database privileges remain the read-only boundary; parsing
cannot prove arbitrary database functions harmless. The executor must bind the
requested parameters, use the requested warehouse and genuinely read the pinned
historical snapshot. Cross-warehouse dependencies and unavailable history are
unsupported/skipped. Never substitute current data for a snapshot.

Stdout contains seed IDs, `pass|fail|skipped` and sanitized categories. Raw rows,
SQL, stderr, local component evidence and judge transcripts stay under ignored
`.nodal/regressions/`. Exit 0 means all selected checks passed; 1 means a failed
check; 2 means configuration failure; 3 means skipped/incomplete or no selected
checks. Skips are not included in a passing denominator.

The shipped `verified-regression.yml` runs only when explicitly dispatched on the
default branch. Configure a protected `nodal-regression` environment and a trusted
customer runner with its executor, authentication and age/SOPS installation.
`NODAL_REGRESSION_RUNNER` may name a customer runner label (default is
`ubuntu-latest`; add provisioning steps there if using a hosted runner).
Set repository/environment variables `NODAL_REGRESSION_EXECUTOR` and optional
`NODAL_REGRESSION_JUDGE` to argv JSON. A private identity may be provisioned through
the protected `NODAL_VERIFIED_IDENTITY` secret; the workflow materializes it only
in its owned temporary workspace, removes it from the child's environment, and
cleans it on success/failure. Warehouse authentication is separately provided by
the customer's executor/runner; no Nodal connector is bundled.

The workflow never checks out fork PR code with secrets. It copies tracked files
into an owned workspace, excludes plaintext/cache state, and removes the whole
workspace in an always-run cleanup step. Only sanitized IDs/status categories
reach the job summary; no raw artifacts or PR comments are published. An
unconfigured executor is explicitly skipped. Ordinary validation and inject eval
do not decrypt or execute warehouse SQL.

For coverage, query existence/decryptability are capabilities, not a fresh checked
pass. `.ci/coverage.py --check-decryption --identity <file>` explicitly probes
keys; `--regression-run .nodal/regressions/<run>/evidence.json` checks a local run
against current seed/definition/config and query revisions. A changed artifact or
dependency marks evidence stale. Human-confirmed dashboard/notebook snapshots
remain separately identified; Python-only notebook snapshots need no SQL sidecar.
