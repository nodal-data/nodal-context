---
name: setup-nodal
description: Configure Nodal's project-local warehouse, dbt, context-repo, and optional browser bindings. Use only when the user explicitly asks to set up, configure, reconnect, or diagnose Nodal. Do not invoke for ordinary interviews or dashboard checks.
disable-model-invocation: true
---

# Setup Nodal

Create or repair project-local Nodal configuration without storing credentials.
This is the only Nodal skill allowed to write `.nodal.local.json` or merge a
browser binding into `.mcp.json`.

## Procedure

1. Establish the user's project root from the current repository or the path they
   name. Never write into this installed skill directory.
2. Discover candidates with bounded searches only:
   - dbt: the project root, its children to depth 3, and sibling directories to
     depth 3; identify `dbt_project.yml`.
   - context repos: the same bounds; identify `context.config.yaml`.
   - git remotes: inspect only candidates already found.
   Present at most five most-recent candidates and ask which ones to use.
3. Discover available warehouse tools and run non-mutating probes:
   - read query: `SELECT 1` (or the platform's equivalent);
   - metadata: list one catalog/schema without fetching table contents;
   - query history: a bounded metadata query using the platform recipe from the
     context-interview skill when available.
   Record only classifications (`ok`, `unavailable`, `denied`, `full`, `limited`,
   or `unsupported`) and a UTC verification timestamp. Never record raw errors,
   authentication responses, query text, tokens, account names, or credentials.
4. Discover a browser binding from the tools already loaded. If none exists,
   offer the bundled `assets/chrome-devtools.mcp.json`. Explain that it launches
   a visible local browser with a dedicated profile and requires a session
   restart. Merge it only after explicit consent.
5. Show the complete destination and sanitized configuration for confirmation.
   The normal fresh context destination is `../analytics-context`, resolved from
   the user's project root. Always confirm before writing.
6. Resolve the helper from the directory containing this actually loaded
   `SKILL.md`; do not assume a checkout path or environment variable. Write
   through that deterministic helper (it validates and uses atomic replace):

   ```bash
   python3 <resolved-setup-skill-directory>/scripts/nodal_config.py write --project-root <project-root> --input <sanitized-json>
   ```

   For an approved default browser binding:

   ```bash
   python3 <resolved-setup-skill-directory>/scripts/nodal_config.py merge-mcp --project-root <project-root> --binding chrome-devtools --consent
   ```

7. Re-run the three live probes and report the sanitized capability table. A
   failed optional probe degrades normally; it does not invalidate the config.

## Configuration contract

The helper accepts version 1 only. Local paths may be relative to the project
root. Repository identities are durable host paths such as
`github.com/acme/acme-dbt`. The file is local and gitignored.

Never work around helper refusal. Malformed JSON, secret-like fields, an invalid
status, or an existing browser binding require the user to repair or choose a
different binding explicitly; this skill does not overwrite them.
