---
name: setup-nodal
description: Configure Nodal's project-local warehouse, context sources, and optional browser bindings. Use only when the user explicitly asks to set up, configure, reconnect, or diagnose Nodal. Do not invoke for ordinary interviews or analytics questions.
disable-model-invocation: true
---

# Setup Nodal

Create or repair project-local Nodal configuration without storing credentials.
This is the only Nodal skill allowed to write `.nodal.local.json` or merge a
browser binding into `.mcp.json`.

## Procedure

1. Establish the user's project root from the current repository or the path they
   name. Never write into this installed skill directory.
2. Discover local context candidates with bounded searches only:
   - ACF: identify `context.config.yaml`.
   - KTX: identify `semantic-layer/` plus `wiki/`.
   - dbt: identify `dbt_project.yml` or `target/manifest.json`.
   - Markdown or agent skills: identify only directories the user names or that
     are already inside the bounded project search.
   Search the project root, its children to depth 3, and sibling directories to
   depth 3. Do not crawl the home directory.
   - git remotes: inspect only candidates already found.
   Present at most five most-recent candidates and ask which ones to use.
3. Discover documentation and semantic-layer tools that are already loaded and
   user-authorized. Classify each chosen source by kind, access (`local` or `mcp`),
   authority, and availability. For MCP sources, record only the binding name —
   never connector configuration, document contents, account identifiers, or
   credentials. Probe with a bounded search/read that retrieves no sensitive
   document body when the tool supports metadata-only discovery.
4. Discover available warehouse tools and run non-mutating probes:
   - read query: `SELECT 1` (or the platform's equivalent);
   - metadata: list one catalog/schema without fetching table contents;
   - query history: a bounded metadata query using the platform recipe from the
     context-interview skill when available.
   Record only classifications (`ok`, `unavailable`, `denied`, `full`, `limited`,
   or `unsupported`) and a UTC verification timestamp. Never record raw errors,
   authentication responses, query text, tokens, account names, or credentials.
5. Discover a browser binding from the tools already loaded. If none exists,
   offer the bundled `assets/chrome-devtools.mcp.json`. Explain that it launches
   a visible local browser with a dedicated profile and requires a session
   restart. Merge it only after explicit consent.
6. Show the complete destination and sanitized configuration for confirmation.
   The normal fresh context destination is `../analytics-context`, resolved from
   the user's project root. Always confirm before writing.
7. Resolve the helper from the directory containing this actually loaded
   `SKILL.md`; do not assume a checkout path or environment variable. Write
   through that deterministic helper (it validates and uses atomic replace):

   ```bash
   python3 <resolved-setup-skill-directory>/scripts/nodal_config.py write --project-root <project-root> --input <sanitized-json>
   ```

   For an approved default browser binding:

   ```bash
   python3 <resolved-setup-skill-directory>/scripts/nodal_config.py merge-mcp --project-root <project-root> --binding chrome-devtools --consent
   ```

8. Re-run the live probes and report the sanitized warehouse and context-source
   capability tables. A
   failed optional probe degrades normally; it does not invalidate the config.

## Configuration contract

The helper accepts version 1 only. `context_sources` is an array whose entries
carry a unique name, kind (`acf`, `ktx`, `dbt`, `markdown`, `agent-skill`, or
`documentation`), access (`local` or `mcp`), authority (`confirmed`, `governed`,
`documented`, `behavioral`, or `inferred`), sanitized availability, verification
timestamp, and enabled flag. Local sources require `location`; MCP sources require
`binding`. Local paths may be relative to the project root. Repository identities
are durable host paths such as `github.com/acme/acme-dbt`. The file is local and
gitignored.

Never work around helper refusal. Malformed JSON, secret-like fields, an invalid
status, or an existing browser binding require the user to repair or choose a
different binding explicitly; this skill does not overwrite them.
