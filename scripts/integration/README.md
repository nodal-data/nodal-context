# Clean-room integration testing

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
  --marketplace-ref v1.5.0 \
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
