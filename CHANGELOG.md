# Changelog

## 1.0.0 — Unreleased

- Package `context-interview`, `dashboard-verify`, and explicit-only
  `setup-nodal` for Claude, Codex, and skills.sh installation.
- Add the manifest-driven, hash-checked context scaffold distribution mirror.
- Add guarded project-local configuration and consent-based browser binding setup.
- Preserve clone-and-run development and generated-repository workflows.
- Add a tracked, non-destructive clean-room integration harness while keeping
  operator briefs, connection configuration, and permissions local.

## Release checklist

- [ ] Run `python3 scripts/sync_skill_payload.py --check` and all tool CI locally.
- [ ] Install from a temporary checkout with Claude; confirm all three namespaced
      skills and bundled hidden files/scripts are present.
- [ ] Install from a temporary checkout with Codex; list the available plugin and
      confirm all three skills load.
- [ ] Install into a temporary project with `npx skills@latest add`; confirm
      scripts, executable modes, `.claude`, `.gitignore`, and `.gitkeep` survive.
- [ ] Invoke setup in each native host, confirm `.nodal.local.json`, and consent to
      a test `.mcp.json` merge without overwriting an existing binding.
- [ ] With authenticated read-only connections, run all three capability probes.
- [ ] Complete a `context-interview` test drive against a temporary context repo.
- [ ] Run the tracked clean-room harness against the source checkout, installed
      Claude and Codex plugins, and a temporary skills.sh installation; complete
      its resume check and generated-repository assertions.
- [ ] Invoke `dashboard-verify` against an authenticated dashboard and reconcile
      at least one value and filter window.
- [ ] Confirm repository and isolated installed-skill scaffold smoke tests pass.
- [ ] Bump plugin semver for every published package change and add release notes.
