---
name: setup-nodal
description: Configure Nodal's project-local warehouse, context sources, and optional browser bindings. Use only when the user explicitly asks to set up, configure, reconnect, or diagnose Nodal. Do not invoke for ordinary interviews or analytics questions.
disable-model-invocation: true
---

# Setup Nodal

Create or repair project-local Nodal configuration without storing credentials.
This is the only Nodal skill allowed to write `.nodal.local.json` or merge a
browser binding into `.mcp.json`.

When explicitly invoked only to change browser verification, preserve every
valid warehouse and context-source field unchanged, run only the browser,
confirmation, and write portions of this procedure, and re-probe only the browser.

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
5. Resolve browser intent without turning general setup into a browser-install
   prompt:
   - Read `browser.mode` from a valid existing configuration. Missing `mode` is
     backward-compatible: infer `automated` when `binding` is set and
     `ask_when_needed` otherwise.
   - Respect `mode: manual` before live discovery. Do not use an otherwise
     available browser for Nodal or ask again unless the user explicitly asks to
     change browser verification.
   - Discover browser tools already loaded. A suitable live binding means
     `mode: automated`; record its binding.
   - If no binding is live, check only whether the bundled binding is already
     present in the project `.mcp.json` by running the helper's sanitized
     `mcp-status` command. Never display or record the MCP configuration body. If
     it reports `configured`, say that a session restart and one-time project
     server approval are still required. Do not offer to install it again.
   - During general setup, when the user has not named a dashboard or asked for
     automated dashboard verification, use `mode: ask_when_needed` and do not
     interrupt setup with a browser offer.
   - When a dashboard is named or automation is explicitly requested and no
     binding is configured, explain before asking: *"Nodal can optionally open a
     visible, dedicated Chrome profile to read one named dashboard, capture its
     values and active filters, and compare them with warehouse answers. You
     sign in yourself; Nodal never requests or handles credentials. This is not
     needed to build context or answer warehouse questions."* Offer automated
     or manual verification. A manual choice writes `mode: manual` with a null
     binding so it is not asked again. For automated verification, offer the
     bundled `assets/chrome-devtools.mcp.json`, explain that Chrome DevTools MCP
     is a local browser bridge rather than the Chrome developer panel, and merge
     it only after explicit consent. Write `mode: automated` and
     `binding: chrome-devtools`, then clearly request the required session
     restart.
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
   python3 <resolved-setup-skill-directory>/scripts/nodal_config.py mcp-status --project-root <project-root> --binding chrome-devtools
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

`browser.mode` is `ask_when_needed`, `manual`, or `automated`. New configurations
always write it. Version-1 configurations without `mode` remain valid and infer
the intent from `binding`. `automated` requires a non-null binding; the other
modes require a null binding. The mode records the user's durable preference,
not whether a tool happens to be live in the current session.
