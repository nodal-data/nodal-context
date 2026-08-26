# Nodal Context Contributor Guide

This repository is the installable Nodal Analytics package and the canonical
source for Analytics Context Format (ACF), its three skills, generated context
repositories, and the evaluation harness. `FINDINGS.md` is ignored local scratch;
do not edit or include it in package work.

## Product invariants

- Interview, do not silently extract: a human owns every confirmed definition.
- Keep qualitative business logic in context; statistics stay in the warehouse.
- Every confirmed disambiguation emits an eval seed.
- The eval harness remains format-agnostic; ACF is one supported adapter.
- Warehouse and browser actions are read-only. Nodal never handles credentials.
- `.nodal.local.json` is local, versioned configuration. Only `setup-nodal` writes
  it, and it stores classifications rather than errors or secrets.

## Canonical and generated files

Root ACF files are canonical: `SPEC.md`, `schemas/`, `template/`, `.ci/`, the
three customer workflows, `scripts/`, and `eval_harness/`. The payload under
`skills/context-interview/` is a generated distribution mirror described by
`scripts/scaffold_manifest.py`; it is not another manually maintained source.

After editing a canonical artifact, run:

```bash
python3 scripts/sync_skill_payload.py --write
python3 scripts/sync_skill_payload.py --check
```

Never hand-edit generated payload files. The checker compares SHA-256 content and
executable modes while preserving actual dot paths. Upgrade scaffolds must
preserve `.ci/lineage-baseline.json` and authored
context.

An ACF field or path change must reconcile all affected canonical surfaces:
`SPEC.md`, `schemas/`, `template/`, the worked example, and
`skills/context-interview/` instructions.

## Skills and packaging

- Skills live only under `skills/`; `.claude/skills/*` are in-repo discovery
  symlinks. Do not create duplicate `.agents/skills` links.
- `.claude-plugin/` and `.codex-plugin/` describe the same root `skills/` tree.
- The plugin must not bundle an MCP server. Optional browser configuration lives
  in `setup-nodal/assets/` and is merged only with consent.
- Native plugin and skills.sh installation are alternatives on one host; docs
  must warn that installing both creates duplicate skill discovery.
- ACF `0.x` and plugin semver are independent; every published package change
  bumps plugin semver.

## Validation

Run the direct test runner, not `pytest tests/` (these executable tests are not
pytest-discovered):

```bash
python3 scripts/run_tests.py
python3 scripts/lint_skills.py
python3 .ci/validate.py
python3 scripts/sync_skill_payload.py --check
claude plugin validate . --strict
```

Also validate `.codex-plugin/plugin.json` and the repo marketplace with the
repository checks. Do not mark a packaging migration complete until repository
and isolated installed-skill scaffold smoke tests pass.

Commit, push, publish, and global agent configuration changes happen only when
the user explicitly requests them.
