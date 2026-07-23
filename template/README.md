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

### The MCP user may need extra grants for query-history mining (Snowflake, Redshift)

Interview Stage 0 can mine your warehouse query history into draft context
(`scripts/query_history_extract.py`). On Snowflake, the full 365-day history
lives in `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`, which an ordinary read-only
user cannot see by default. Grant the MCP user access with the least-privilege
built-in database role (run as `ACCOUNTADMIN`):

```sql
USE ROLE ACCOUNTADMIN;

CREATE ROLE IF NOT EXISTS QUERY_HISTORY_READER;

-- ACCOUNT_USAGE views (QUERY_HISTORY among them) via the built-in governance role
GRANT DATABASE ROLE SNOWFLAKE.GOVERNANCE_VIEWER TO ROLE QUERY_HISTORY_READER;

GRANT USAGE ON WAREHOUSE <WAREHOUSE> TO ROLE QUERY_HISTORY_READER;

GRANT ROLE QUERY_HISTORY_READER TO USER <USER>;
```

`<USER>` is the user your warehouse MCP server connects as; `<WAREHOUSE>` is the
warehouse it runs queries on. Without this grant, mining still works via the
7-day `INFORMATION_SCHEMA` fallback — the interview will tell you it's working
from a one-week, privilege-limited sample.

On Redshift, history lives in `SYS_QUERY_HISTORY`, where a regular user sees
only their **own** queries — dashboards and teammates are invisible. Grant the
MCP user visibility of everyone's query *metadata* (never table data) with one
line, run as a superuser:

```sql
ALTER USER <USER> SYSLOG ACCESS UNRESTRICTED;
```

Without it, mining still runs but only over the MCP user's own queries — the
interview will tell you the sample was privilege-limited.

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
  skill** — it resumes from `context.config.yaml` rather than starting over. For
  picking the work up on another machine or handing it to a teammate, see
  "Continuing this repo" in [`AUTHORING.md`](./AUTHORING.md).
- Review every change **by PR**. The bundled `.github/workflows/` validate the YAML,
  flag unconfirmed `status: draft` entries, run the on/off eval delta, and detect
  drift when an upstream model changes.
- **Keep it in sync with dbt automatically (optional, Nodal).** Connect your dbt repo
  and upstream changes — renamed columns, redefined metrics — propagate into the
  affected definitions as drafts for your analyst to confirm, so the context tracks the
  warehouse without anyone remembering to re-run the interview. The `context-drift`
  workflow above flags the same drift on PR for free; the managed loop closes it. See
  [docs.nodaldata.io](https://docs.nodaldata.io/enterprise/overview).

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
the enterprise learning loop (observability, coverage evaluations, regression tests,
dbt-sync).
