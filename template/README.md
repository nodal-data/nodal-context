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
gets the analyst's answer), serve it over **MCP** — three ways: **build your own**
(self-host, free), **launch on Nodal** (hosted, low-cost, ~2 min, no database
connection), or **run it in your own cloud/VPC** (regulated/enterprise).

See **[`SHARING.md`](./SHARING.md)** for the tool surface, the 3-step hosted setup, and
the enterprise dbt-sync + observability options.
