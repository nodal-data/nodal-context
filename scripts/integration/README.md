# Clean-room integration testing

## Scoped dbt retrieval probe

`retrieval_probe.py` prepares a deterministic synthetic dbt project and reports
operator-exported retrieval captures. It does not start an agent, implement an
MCP server, access a warehouse, or change any host configuration.

```bash
.venv/bin/python scripts/integration/retrieval_probe.py prepare /tmp/nodal-dbt-probe-UNIQUE
.venv/bin/python scripts/integration/retrieval_probe.py report /tmp/retrieval-captures.json
```

Preparation requires an absent directory, never deletes caller data, and prints
the fixture digest. The project has `fct_orders`, its customer dependency, thirty
unrelated supplier models, a shared schema YAML, model-level/cross-column tests,
and an upstream account exclusion. The context's revision-specific governance
statement is synthetic exercise evidence, not a live receipt. Expected answers
and adjudication records belong outside the agent's evidence directory.
All sources are declared, and the cross-column test uses a bundled generic macro;
no dbt packages are required. To smoke-test manifest generation with a separately
installed `dbt-duckdb`, run:

```bash
RETRIEVAL_PROBE_DBT=/path/to/dbt .venv/bin/python tests/test_retrieval_probe.py
```

This runs `dbt parse` with a temporary in-memory DuckDB profile and checks the
manifest's models, sources and cross-column test. It does not execute models or
connect to a warehouse. The ordinary offline test skips this opt-in parser check.

For maintainer-operated comparisons, give baseline and changed agents the same
question, fixture and authorized test connector capabilities. Keep host/model
settings fixed. Record baseline and skill-only arms first; server-only and
combined arms require the separately implemented external server. Do not simulate
their success with hand-written traces. Local file reads can test selection but
do not establish cold-cache MCP behavior or transport savings.

Export a JSON array of runs in this format (the strings below are placeholders,
not measurement evidence):

```json
[
  {
    "configuration": "skill-only",
    "host": "host/version",
    "model": "exact-model",
    "settings_id": "digest-of-matched-nonsecret-settings",
    "fixture_sha256": "digest-printed-by-prepare",
    "run_id": "unique-run-id",
    "tokenizer": "tokenizer-name/version-or-omit-if-unavailable",
    "events": [
      {
        "kind": "evidence",
        "raw_response": "full response before runtime selection",
        "emitted_response": "full response actually exposed to the model",
        "capture_complete": true,
        "overview": false,
        "business_execution": false,
        "model_bodies": ["model.retrieval_fixture.fct_orders"]
      }
    ],
    "review": {
      "constraints_retained": true,
      "approval_preserved": true,
      "evidence_complete": true,
      "evidence": "Reviewer findings with trace and final-plan locations"
    }
  }
]
```

Use event kinds `discovery`, `evidence`, or `execution`. `model_bodies` records
actual exposed bodies, including repeated exposures, not compact index hits.
Set `overview` for broad overview calls and `business_execution` for business
result execution (metadata reads do not count). Include failed calls, warnings,
continuations and revision changes. Do not mark captures complete if only a
truncated transcript is available. Remove secrets before recording; these fixtures
need no credentials or real customer data.

Optionally supply nonnegative integer `emitted_tokens` for every discovery and
evidence event with the exact tokenizer used. Without complete token measurement,
the report gives UTF-8 byte counts and null token counts, never a token estimate.
Execution-only captures also have null token counts. Token medians are emitted
only when every supplied run has complete retrieval measurements using the same
nonempty tokenizer identifier; otherwise `token_comparison` is `incomparable`.
Per-run measurements and byte medians remain available.
It reports raw versus emitted bytes separately; runtime filtering does not prove
reduced server transfer, and neither count includes host-injected tool schemas.

Review the actual plan and trace for distinct-customer counting, first-ever and
time semantics, account exclusions, join cardinality, retained model/cross-column
constraints, provenance/continuations, and approval before execution. Record
unsupported or contradictory evidence as a failed review field. Those fields are
operator adjudication, not independently attested approval. Reports preserve
per-run failures and configuration medians; missing arms remain explicit. Compare
tokens only with the same tokenizer. A combined-path acceptance additionally
requires no overview or unrelated bodies, complete required evidence, preserved
approval, and a strictly lower median of per-run total emitted discovery plus
evidence tokens than the matched baseline. `combined_acceptance` reports `pass`,
`fail`, or `not_evaluated` with a reason. Missing baseline/combined arms or
incomparable measurements cannot pass; any failed run prevents acceptance.
The report exits 1 for failed review/execution checks or a failed reduction,
and 2 when a supplied combined arm cannot be evaluated. Reports without a
combined arm may exit 0, but do not establish combined acceptance.
Do not infer improvement from byte counts alone or hide failed runs in a median.

`tests/test_retrieval_probe.py` checks fixture preservation and measurement
behavior offline. Plugin eval cases 10–13 check supplied-evidence decisions.
Neither is a substitute for the opt-in real retrieval comparison.

## Clean-room workflow

This opt-in harness exercises Nodal from a clean project without copying ignored
operator data out of the source checkout. It complements the deterministic tests
in `tests/`; authenticated agent, warehouse, and dashboard runs are release
checks and do not run in ordinary CI.

The harness creates a unique directory under the operating system's temporary
directory by default, never deletes a supplied directory, and preserves the room
after every run. It copies the current source worktree through `git ls-files`, so
tracked edits and non-ignored new files are tested while `responses.md`, `.env`,
`.nodal.local.json`, `.mcp.json`, browser profiles, local Claude settings, and
other ignored operator files remain private.

By default this is clean-project isolation: the launched host can still see its
normal user authentication, plugins, and configuration. Add `--isolated-host`
for release-candidate testing when user-level customization must not influence
the result.

## Package sources and hosts

Package source and host are separate dimensions. Source-checkout and skills.sh
modes support either host; each native-plugin mode must use its matching host:

```bash
# Clone-and-run development path; defaults to Claude.
scripts/integration/clean_test.sh --package-source source-checkout

# The enabled Claude native plugin. Its installed cache path is verified.
scripts/integration/clean_test.sh --package-source claude-plugin --host claude

# The enabled Codex native plugin. Its marketplace payload is verified.
scripts/integration/clean_test.sh --package-source codex-plugin --host codex

# A project or collection already populated by skills.sh.
scripts/integration/clean_test.sh \
  --package-source skills \
  --package-root /tmp/skills-install-project \
  --host codex
```

Codex runs use the `workspace-write` sandbox because the generated context
repository is an intentional sibling of the clean project and is passed through
`--add-dir`. Interactive runs retain normal approval prompts; non-interactive
runs additionally use Codex's automated approval review.

For a real skills.sh release check, first install into an otherwise empty
temporary project with the canonical `npx skills@latest add` command, then pass
that project as `--package-root`. The harness copies those installed artifacts
into a second clean project so the test cannot silently fall back to this source
checkout.

Use `--prepare-only --host none` to inspect the clean room without invoking an
agent. Use `--work-dir` only with an absent or empty path beneath the operating
system's temporary directory; the harness refuses a non-empty or non-temporary
directory.

## Isolated host state and native installation

For Codex, `--isolated-host` creates a fresh `CODEX_HOME` inside the preserved
room. In `codex-plugin` mode it adds a marketplace snapshot, installs
`nodal-analytics@nodal` into that home, and discovers the installed cache payload
there. It does not copy authentication from the maintainer's normal profile.

Prepare a local-worktree release candidate first:

```bash
scripts/integration/clean_test.sh \
  --package-source codex-plugin \
  --host codex \
  --isolated-host \
  --prepare-only
```

The command prints the preserved room, an exact isolated-home authentication
command using `codex login --device-auth`, and the matching `--launch-prepared`
command. Authenticate that isolated home, then launch the prepared room. This
two-step flow keeps credentials out of the harness and ensures plugin
installation happened before the host session began.

To test what users receive from Git rather than the current worktree, provide a
marketplace source and release ref:

```bash
scripts/integration/clean_test.sh \
  --package-source codex-plugin \
  --host codex \
  --isolated-host \
  --marketplace-source nodal-data/nodal-context \
  --marketplace-ref v1.5.1 \
  --prepare-only
```

For Claude, `--isolated-host` launches `claude --bare`. A native-plugin test
loads the selected package root explicitly with `--plugin-dir`; it does not use
or modify the maintainer's installed-plugin state. Bare mode requires an
explicit Anthropic API key or supported third-party-provider credentials and
does not use OAuth or the keychain. Use a separate operating-system account or
VM for an ordinary OAuth and Desktop installation test.

Host-state isolation covers CLI configuration and plugin discovery. It is not a
GUI sandbox. Before a public release, use a separate macOS account or a restored
VM snapshot to smoke-test Codex Desktop, the Plugins Directory, browser launch,
project-server approval, and application restart behavior.

## Agent-guided onboarding scenario

The pre-install scenario starts with an empty consumer project and an isolated
Codex home. It copies only `docs/agent-guide.md` into the project—none of Nodal's
skills or contributor instructions—then asks the unconfigured agent to follow
the guide and install exactly one local release-candidate distribution:

```bash
scripts/integration/clean_test.sh \
  --package-source source-checkout \
  --host codex \
  --isolated-host \
  --scenario agent-guided-onboarding \
  --prepare-only
```

Authenticate the printed isolated Codex home, then run the printed
`--launch-prepared ... --non-interactive` command. The scenario confirms that:

- the agent explains Nodal and selects only the Codex native plugin;
- the isolated home contains the `nodal` marketplace and enabled plugin;
- no project-local skills, `.nodal.local.json`, or `.mcp.json` are written;
- the transcript establishes the new-task boundary and hands off to
  `$setup-nodal`; and
- no credentials are requested.

This test uses the local checkout so it can evaluate uncommitted release work
without network access. Before publishing, separately paste the public README
prompt into a clean Desktop account or VM to confirm that the public GitHub
guide is reachable and the Git marketplace installation succeeds.

## Browser-install lifecycle scenario

The tracked release scenario exercises the setup messaging that distinguishes a
missing binding from one that was just configured but is not live yet:

```bash
scripts/integration/clean_test.sh \
  --package-source codex-plugin \
  --host codex \
  --isolated-host \
  --scenario browser-install-lifecycle \
  --prepare-only
```

After authenticating the printed isolated Codex home, run the printed
`--launch-prepared ... --non-interactive` command. Non-interactive host output is
streamed to the terminal and preserved as `<host>-transcript.log` in the room.
The scenario asserts both state and user-facing concepts:

- `.nodal.local.json` records automated `chrome-devtools` intent;
- `.mcp.json` contains the project binding;
- the browser is described as optional, visible, and dedicated, with credentials
  remaining with the user;
- the binding is reported as configured and the next action is a session restart
  plus one-time project-server approval; and
- the lifecycle receipt states that installation was not offered again.

The agent invokes setup twice in one session so the second pass sees a configured
but not-yet-live binding. A separate macOS-user or VM smoke test remains the
release check for the next-session live-binding and Desktop approval experience.

## Private operator inputs

Simulated-customer briefs and connection settings remain ignored and local:

```bash
scripts/integration/clean_test.sh \
  --package-source claude-plugin \
  --host claude \
  --brief ./responses.md \
  --operator-settings ./.claude/settings.local.json \
  --mcp-config /path/to/operator.mcp.json
```

The brief is copied with owner-only permissions into the temporary room, outside
the test project. The tracked harness contains no MCP server names, credentials,
customer responses, browser profiles, or host-specific permission grants.

`--non-interactive` uses each host's normal automated mode. The additional
`--unsafe-bypass` switch is deliberately explicit and is accepted only with
`--non-interactive`; use it solely inside a real container or VM boundary. A
temporary directory by itself is not a security sandbox.

A private `clean-test.sh` or `clean-test.local.sh` may remain as a short wrapper
that supplies these local arguments. Both names are ignored.

## Quick simulated analyst loop

Use the current worktree directly, without publishing or refreshing an installed
plugin and without running the release matrix:

```bash
scripts/integration/clean_test.sh --package-source source-checkout --host claude --brief ./responses.md
```

The same path supports `--host codex`, `--prepare-only`, `--non-interactive`, and
`--resume ROOM`. The familiar `--auto` selects root `responses.md` (or legacy
`RESPONSES.md`); `--auto=/path/to/brief.md` supplies a specific brief. A positional
room path is accepted for old wrappers but must be absent or empty under an OS
temporary directory. Otherwise a unique room is created. No caller directory is
deleted. `--auto` selects simulation, not permission bypass.

Keep the ignored root wrapper small:

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/scripts/integration/clean_test.sh" "$@"
```

The copied brief stays outside both projects with owner-only permissions. Source
copies exclude `/specs/`, private response/context briefs, notebooks, raw run
evidence, plaintext answer keys and local operator configuration even when a
file was accidentally tracked. They preserve the canonical specification in
`skills/context-interview/references/SPEC.md`, hidden package files and encrypted
answer keys. A brief explicitly supplied with `--brief` is
also excluded regardless of its filename. Source copying reflects uncommitted
code changes; it never reads local planning specs as package inputs.

Both starting project and generated context destination receive
`.sim-analyst.json`, containing `responses` and `log` pointers plus launch mode
and optional run ID/state path. The initial prompt names the marker explicitly.
Only the responder subagent may read the brief; this separation is an interview
protocol, not an OS sandbox between agents. The helper never reads the brief.

`scripts/simulated_analyst.py record|pending` maintains a private transcript and
shared state. `CONFIDENT` replies progress the interview but leave artifacts
draft with no approval fields. `NOT_CONFIDENT`, malformed replies or missing
responder capability require a real human. Interactive mode asks; non-interactive
mode records the question and pauses with **exit code 3**, preserving the room.
Use `pending --marker PROJECT/.sim-analyst.json` to inspect unresolved questions.
Record the human reply with `record --source human --reviewer NAME` using the
same question ID, then resume. A second simulated guess cannot resolve it.

Resume discovers simulation from the existing marker even without another
`--brief` argument. It retains question history and the exact copied brief,
refuses to silently substitute a different brief, and works if the first pending
question occurred before scaffolding. Use a new room for a different brief.

Post-run assertions require actual draft metric/seed output and a logged exchange.
They reject confirmed objects without matching explicit real-human receipts.
Only a real-human approval permits `simulated_analyst.py attest-human` after the
reviewed artifact has been authored; it changes no definitions or status. It is
an operator attestation, not proof of identity or external execution. The helper's
`check` command detects stale receipts after edits. Dashboard, notebook and
warehouse checks remain actual executions; unavailable capabilities are skipped,
not simulated as passes. Draft evals use `--status draft` and are labeled as such.

Every actual simulation launch writes owner-only `simulation-summary.json` in
the room, including pauses before scaffolding. It records the generated context
path, draft metric/method paths, transcript, pending human questions, open
decisions and verification follow-ups. Inspect `context_created` and
`context_valid` separately from `execution_verification`: draft validation cannot
establish a warehouse, dashboard or notebook match. The console prints the summary
and log paths. Preparation alone starts no interview and creates no run summary.
Static notebook imports can participate in this quick loop; unavailable execution
does not prevent draft capture, and simulated answers never confirm a method.

Offline preparation, marker handoff, early-pause resume, pending-question behavior,
draft validation and destination preservation run in the direct test suite. A
short live acceptance test is available only when a maintainer selects it:

```bash
.venv/bin/python tests/test_simulation.py --live claude
# Or: --live codex
```

It uses a fictional brief, normal host safeguards and customer-owned host
authentication, preserves its room, and requires draft metric/method/seed output.
It performs no warehouse/dashboard/notebook acceptance. No live agent is started
by the default test command. A paused or failed live run is not a passing release
check; inspect its pending questions/transcript before continuing.

For a noninteractive Claude run that needs explicit script grants, first use
`tests/test_simulation.py --live claude --prepare-only`. Prepare an ignored
operator settings file for that printed room, then launch it with the tracked
harness's `--launch-prepared ROOM --non-interactive --operator-settings FILE`.
The launch prompt supplies absolute scaffold/helper/validation paths from the
selected package so grants can match the actual files rather than discovery
symlinks. The harness does not generate permissions or weaken host safeguards.
Inspect the resulting method drafts as well as the harness's metric/seed checks.

## Assertions and resume testing

After the host exits successfully, the harness checks the generated repo for:

- `SPEC.md`, schemas, context-local scripts, CI, and the eval harness;
- real hidden files including `.gitignore`, `.gitkeep`, and `.claude` content;
- executable extraction scripts;
- a working eval-harness import and `compile_skill.py` entry point; and
- root ACF validation when validation dependencies are installed.

To test resume behavior, retain the work-directory path printed by the first
run, stop the interview with draft work present, and run:

```bash
scripts/integration/clean_test.sh --resume /tmp/nodal-clean-test-EXAMPLE
```

The harness validates the existing context repo before launch and adds a unique
resume marker. Post-run checks fail if the skill replaced the repository instead
of resuming it. Package source and host are read from the room marker, so the
second run exercises the same distribution channel.

The assertions can also be run directly:

```bash
python3 scripts/integration/assert_context_repo.py /path/to/analytics-context
```
