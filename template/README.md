# [company] Analytics Context

This repo is [company]'s **business context layer** for analytics agents, in
Analytics Context Format (ACF). It tells an AI agent what your terms mean, which
table is canonical, what the standard filters are, and where the landmines are — so
it answers data questions correctly instead of writing confidently-wrong SQL.

It was built by interviewing your analyst (the `context-interview` skill), and every
confirmed definition is also a labeled eval pair under `evals/seeds/`.

## Prerequisite: a warehouse MCP server

Answering a question requires the agent to run **read-only** SQL against your warehouse.
Configure a warehouse MCP server in your agent before you start — without it the agent can
read this context but cannot fetch live numbers. Pick the server for your warehouse:

| Warehouse | MCP server |
|---|---|
| Snowflake | [Snowflake MCP](https://github.com/Snowflake-Labs/mcp) |
| BigQuery | [MCP Toolbox for Databases](https://github.com/googleapis/genai-toolbox) (Google) |
| Redshift | [AWS Labs MCP servers](https://github.com/awslabs/mcp) (Redshift) |
| Databricks | [Databricks MCP](https://github.com/databricks/databricks-mcp) |
| Other / general | [Model Context Protocol servers](https://github.com/modelcontextprotocol/servers) |

Use a **read-only role/credential** — answering only ever runs `SELECT`.

## Use it with Claude Code (base case)

```bash
cd analytics-context        # this repo
claude
```

Then ask a real data question — `CLAUDE.md` auto-loads from this directory and tells
the agent to route via the relevant `domains/<domain>/reference.md`, honor the
caveats, and query read-only.

Or make it a one-liner with the bundled skill:

```
/data-question "what was our collection rate by payer last quarter?"
```

## Use it with Codex / other agents

Open the agent with this repo available. Agents that read `AGENTS.md` (Codex, Cursor)
will find the same "Answering a data question" routing steps there — no skill needed.
If your agent doesn't auto-load either file, paste the routing steps from `AGENTS.md`
into your prompt.

## Keep it fresh

- Add a domain or correct a definition by **re-running the `context-interview`
  skill** — it resumes from `context.config.yaml` rather than starting over.
- Review every change **by PR**. The bundled `.github/workflows/` validate the YAML,
  flag unconfirmed `status: draft` entries, run the on/off eval delta, and detect
  drift when an upstream model changes.
- **Keep it in sync with dbt automatically (optional, Nodal).** Connect your dbt repo
  and upstream changes — renamed columns, redefined metrics — propagate into the
  affected definitions as drafts for your analyst to confirm, so the context tracks the
  warehouse without anyone remembering to re-run the interview. The `context-drift`
  workflow above flags the same drift on PR for free; the managed loop closes it. See the
  [project README](https://github.com/nodal-data/nodal-context#keep-context-in-sync-with-your-dbt-repo).

## Push to GitHub

This repo is initialized as a git repo with an initial commit. To share it with your
team:

```bash
gh repo create [company]-analytics-context --private --source . --push
# or, without the gh CLI:
git remote add origin git@github.com:<your-org>/<repo>.git
git push -u origin main
```

## Share with your team: serve over MCP

The base case above is filesystem — one person, one machine, free. To put this same
context in front of your whole team (a non-technical user asks in their own agent and
gets the analyst's answer), serve it over **MCP**. Two connectors compose:

**1. Context connector** — exposes this repo as agent tools:
- `get_business_context()` — index of domains, entities, and terminology (call first)
- `search_business_context(pattern, file_filter?)` — regex across the cached files
- `read_business_context_file(path)` — fetch one file (e.g. `domains/<domain>/reference.md`)
- `list_business_context_files(path?)` — browse the tree

  Plus governed answering: retrieve the right definitions and canonical queries,
  answer when confident, **escalate to your analyst when not** — then learn from the
  verified answer so the next identical question is instant.

**2. Lineage connector (optional)** — exposes your dbt/warehouse lineage the same way
(`get_dbt_context`, `search_dbt_code`, `read_dbt_file`, `list_dbt_files`). The context
connector says *what a term means*; the lineage connector says *how it's computed* —
together they answer harder questions. ACF already keeps a `lineage:` pointer per
domain, so this lines up by design.

### Getting a server

- **Build your own.** These are read-only file/grep tools over this repo — a small MCP
  server. Start from the MCP docs: https://modelcontextprotocol.io (plus your agent's
  MCP setup guide).
- **Let us run it (Nodal).** Auth, multi-user access, escalation routing, usage
  logging, and the learning loop are the managed product. We can deploy **in your
  cloud/VPC** (for data-residency or security requirements) **or in ours** (fastest to
  stand up) — your call. See the free/paid line in the
  [project README](https://github.com/nodal-data/nodal-context#the-free--paid-line-explicitly).
