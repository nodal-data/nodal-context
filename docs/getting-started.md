# Getting started with Nodal Analytics

This guide covers the durable technical setup for the Nodal Analytics skills.
It is deliberately more detailed than the root README so prerequisites,
permissions, and degraded modes remain explicit without burying installation.

## What setup can and cannot do

Nodal uses agent-provided tools to inspect approved sources. It does not bundle a
warehouse MCP server, handle credentials, or grant itself access.

- Warehouse actions are read-only: `SELECT` and non-mutating metadata probes.
- A human owns every confirmed definition.
- Existing schema, dbt, documentation, dashboard, and query-log evidence is
  draft material until the analyst confirms it.
- Only `setup-nodal` writes `.nodal.local.json`.
- `.nodal.local.json` stores paths and sanitized capability classifications, not
  secrets or raw connection errors.

## Prerequisites

### Required

1. **A supported agent host.** Use Claude Code, Codex, or another host that can
   install Agent Skills.
2. **A domain expert.** The context interview requires an analyst or other owner
   who can confirm business definitions and failure cases.
3. **An approved read-only warehouse connection.** Configure an MCP server for
   the warehouse in the host. The connected identity must be able to run
   `SELECT` and inspect the relevant metadata.

### Strongly recommended for the initial build

1. **Historical query access.** Full Stage 0 discovery mines recurring query
   shapes, BI traffic, and conflicting metric definitions. Access should cover
   relevant users and service accounts—not only the MCP identity's own queries.
2. **A local dbt checkout.** If the company uses dbt, clone it next to the
   project where you will run the interview.
3. **BI service-account names.** Knowing which users, roles, warehouses, or
   labels belong to dashboards helps distinguish institutionalized logic from
   ETL and ad hoc exploration.

The interview does not block when query history is unavailable. It records one
of `mined`, `deferred: auth`, `deferred: privileges`, or `unsupported`, then
continues with the evidence it can access. This makes reduced coverage visible
rather than silently treating a thin sample as complete.

## Install exactly one distribution

Installing a native plugin and skills.sh on the same host creates duplicate
skill discovery. Pick one.

### Claude Code plugin

```bash
claude plugin marketplace add nodal-data/nodal-context
claude plugin install nodal-analytics@nodal
claude plugin list
```

Update an existing installation with:

```bash
claude plugin marketplace update nodal
claude plugin update --scope user nodal-analytics@nodal
```

Restart Claude Code after an update.

### Codex plugin

```bash
codex plugin marketplace add nodal-data/nodal-context
codex plugin add nodal-analytics@nodal
```

### Project-local skills

```bash
npx skills@latest add nodal-data/nodal-context
```

Select `setup-nodal` plus the workflows you want. Project-local copies are
editable and update independently from native plugins.

## Connect a warehouse through MCP

Nodal does not enable an MCP server during installation. Configure one that is
approved for your environment and authenticate it outside Nodal.

| Warehouse | Example MCP implementation |
|---|---|
| Snowflake | [Snowflake Labs MCP](https://github.com/Snowflake-Labs/mcp) |
| BigQuery | [MCP Toolbox for Databases](https://github.com/googleapis/genai-toolbox) |
| Redshift | [AWS Labs MCP servers](https://github.com/awslabs/mcp) |
| Databricks | [Databricks MCP](https://github.com/databricks/databricks-mcp) |
| Other | [Model Context Protocol servers](https://github.com/modelcontextprotocol/servers) |

Use a dedicated read-only role or identity. Nodal does not execute DDL, DML,
grants, stored procedures, or exports.

## Historical query access

Query-history mining is the highest-leverage optional input to the initial
interview. It reveals what dashboards and people repeatedly compute and, more
importantly, where multiple definitions compete for the same metric.

Query metadata can include full SQL text and literals embedded in it. Treat it
as sensitive operational metadata. Extraction artifacts are transient,
gitignored local files and should be discarded after Stage 0.

The grants below must be applied by the customer's warehouse administrator—not
by Nodal or the agent running the interview.

### Preflight visibility probes

Run the probe for the connected warehouse before the first interview. These
queries read query metadata only; they do not read application-table data.
Replace `<PROJECT>` and `<LOCATION>` with the BigQuery project and the dataset's
region (for example, `us` or `eu`).

<details>
<summary><strong>Snowflake</strong></summary>

```sql
SELECT
  CURRENT_USER() AS connected_user,
  CURRENT_ROLE() AS active_role,
  COUNT(*) AS visible_queries,
  COUNT(DISTINCT user_name) AS visible_users
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE start_time >= DATEADD(day, -1, CURRENT_TIMESTAMP());
```

</details>

<details>
<summary><strong>BigQuery</strong></summary>

```sql
SELECT
  SESSION_USER() AS connected_user,
  COUNT(*) AS visible_queries,
  COUNT(DISTINCT user_email) AS visible_users
FROM `<PROJECT>`.`region-<LOCATION>`.INFORMATION_SCHEMA.JOBS
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY);
```

</details>

<details>
<summary><strong>Redshift</strong></summary>

```sql
SELECT
  CURRENT_USER AS connected_user,
  COUNT(*) AS visible_queries,
  COUNT(DISTINCT user_id) AS visible_users
FROM SYS_QUERY_HISTORY
WHERE start_time >= DATEADD(day, -1, GETDATE());
```

</details>

If a query succeeds, the connected identity can read that history source. A
`visible_users` value greater than one shows cross-user visibility in the
one-day sample. A value of zero or one is not proof that access is restricted—
the warehouse may simply have little recent activity—but Nodal treats it as a
visibility warning rather than assuming the history is complete. A permission
error means the applicable administrator grant below is still needed.

### Snowflake

The preferred source is `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`, which provides
up to 365 days of history with normal Account Usage latency. The MCP identity
usually cannot see it without an explicit read-only role.

An `ACCOUNTADMIN` can create and assign a least-privilege role:

```sql
USE ROLE ACCOUNTADMIN;
CREATE ROLE IF NOT EXISTS QUERY_HISTORY_READER;
GRANT DATABASE ROLE SNOWFLAKE.GOVERNANCE_VIEWER TO ROLE QUERY_HISTORY_READER;
GRANT USAGE ON WAREHOUSE <WAREHOUSE> TO ROLE QUERY_HISTORY_READER;
GRANT ROLE QUERY_HISTORY_READER TO USER <USER>;
```

If the grant cannot be applied immediately, Nodal can use the
`INFORMATION_SCHEMA` fallback. That view covers only seven days and is limited
to queries visible to the current role, so the interview labels the sample as
privilege-limited.

### BigQuery

The preferred source is the project-level, region-qualified
`INFORMATION_SCHEMA.JOBS` view. It retains up to 180 days. Reading all project
jobs requires `bigquery.jobs.listAll`; running the extraction query also needs
job execution permission.

A project administrator can grant the standard read-only job-metadata roles:

```bash
gcloud projects add-iam-policy-binding <PROJECT> \
  --member="serviceAccount:<READER>" \
  --role="roles/bigquery.resourceViewer"

gcloud projects add-iam-policy-binding <PROJECT> \
  --member="serviceAccount:<READER>" \
  --role="roles/bigquery.jobUser"
```

Use `user:<email>` instead of `serviceAccount:<READER>` for a human identity.
`JOBS_BY_USER` is not equivalent coverage: when available, it shows only the
caller's jobs. Nodal treats an empty or unusually thin result as a visibility
warning rather than proof that the project has no useful history.

### Redshift

`SYS_QUERY_HISTORY` retains roughly seven days. Regular users can read the view
but normally see only their own rows, which can look like a successful yet
misleading extraction.

A superuser can grant visibility into other users' system-log rows:

```sql
ALTER USER <USER> SYSLOG ACCESS UNRESTRICTED;
```

This exposes query metadata, including query text and literals—not underlying
table data. The short retention window means low-frequency dashboard queries may
still be underrepresented.

### Other warehouses

Warehouse querying may still work through an approved MCP server even when the
query-history extractor does not support that platform. Nodal records history
mining as unsupported and continues with dbt, documentation, warehouse metadata,
the analyst interview, and optional dashboard verification.

## Run project setup

Start in the project where you plan to ask analytics questions or build context.
Invoke setup explicitly:

```text
# Claude Code
/nodal-analytics:setup-nodal

# Codex
$setup-nodal
```

Setup performs live capability probes, discovers nearby context and dbt sources,
and optionally offers to merge a local browser binding. It writes a gitignored
configuration like:

```json
{
  "version": 1,
  "warehouse": {
    "platform": "snowflake",
    "mcp_server": "snowflake",
    "capabilities": {
      "read_query": {"status": "ok", "verified_at": "2026-08-25T12:00:00Z"},
      "metadata": {"status": "ok", "verified_at": "2026-08-25T12:00:00Z"},
      "query_history": {"status": "full", "verified_at": "2026-08-25T12:00:00Z"}
    }
  },
  "dbt": {"local_path": "../acme-dbt", "repo": "github.com/acme/acme-dbt"},
  "context_repo": {"local_path": "../analytics-context", "repo": null},
  "browser": {"binding": "chrome-devtools"}
}
```

Other skills treat this configuration as a hint and re-probe live tools before
use. Missing, stale, or invalid configuration degrades to normal discovery.

## Build context

For a five-question, one-domain test drive, ask:

```text
Take Nodal for a test drive on one analytics domain.
```

The interview confirms the canonical grain, one ambiguous entity, the top
metrics, a standard hygiene filter, and a silent failure case. It verifies a few
answers against the live warehouse and leaves everything else as reviewable
drafts. Confirmed disambiguations become both context entries and eval seeds.

For the complete workflow, ask:

```text
Build my analytics context.
```

The proposed output is normally `../analytics-context`. The skill confirms the
resolved destination before writing. The generated repository contains its own
specification, schemas, scripts, CI, and evaluation harness, so work can continue
without a Nodal source checkout.

## Ask and verify an analytics question

Ask a normal business question, for example:

```text
How did activated customers change month over month this year?
```

`analytics-plan` discovers approved context across ACF, Kaelio KTX, dbt, local
documentation, approved documentation MCPs, and warehouse evidence. It presents
the interpretation, grain, filters, time semantics, query plan, and uncertainty
before execution.

After read-only SQL runs, `verify-result` checks plan fidelity and result
plausibility. Missing definitions, conflicting evidence, mandatory-filter
failures, or unsafe joins produce a clarification or expert-escalation
recommendation rather than a falsely confident answer.

If the returned answer still looks wrong—or you simply want another take—ask:

```text
Challenge this result with an independent second review.
```

`challenge-result` first distinguishes a specific concern from a general second
opinion. It reconstructs the intended analysis, tests plausible alternative
interpretations and failure modes, and audits both the reported number and the
user's expectation. It returns `UPHELD`, `INCONCLUSIVE`, or `REPLAN`. A replan
goes back through `analytics-plan` and requires fresh approval before any SQL is
executed.

## Optional dashboard verification

`dashboard-verify` uses a named dashboard in the user's local authenticated
browser. It captures visible values together with active filters and extraction
confidence. It does not handle credentials or use the browser for general
browsing.

## Maintainer testing

Repository validation commands and the release checklist live in
[`CHANGELOG.md`](../CHANGELOG.md). The opt-in clean-room workflow for source,
native-plugin, skills.sh, warehouse, dashboard, and resume checks is documented
in [`scripts/integration/README.md`](../scripts/integration/README.md).
