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
