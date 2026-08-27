# Website content draft

> **Temporary migration file.** This preserves product, deployment, and
> commercial material that was previously carried by the repository README.
> Move the relevant sections into nodaldata.io or docs.nodaldata.io, then remove
> this file once the published pages have durable homes.

## Suggested destination map

| Content | Suggested destination |
|---|---|
| The three-stage product story | Product overview / homepage |
| Why interview-built | Methodology page |
| Sharing context through MCP | Hosted context product page |
| dbt synchronization and learning loop | Enterprise product page |
| Free and paid capability boundary | Pricing or open-source page |
| Compiled Claude skill snapshot | Documentation / deployment guide |

## Product overview: build, share, and keep context correct

Pointing an AI agent at a warehouse and letting it write SQL feels like
self-service analytics until the answers are confidently wrong. The fix is not
only a better model. It is context: what business terms mean, which table is
canonical, which filters are standard, and where the landmines are.

Nodal is three things, in the order teams adopt them:

1. **Build it — the context format and interview skills.**
   Free and open source under Apache-2.0. Nodal builds context with an analyst,
   one domain at a time, and writes it to a Git repository the team reviews by
   pull request. Use the complete multi-stage interview or a roughly 30-minute
   test drive that confirms five high-leverage answers and leaves the rest as
   explicit drafts. Take it, fork it, and own the output.

2. **Share it — the hosted MCP endpoint.**
   Connect analytics context—and optionally dbt lineage—to an MCP endpoint the
   whole team can use. Merge a pull request and every consumer sees the current
   definitions without redistributing files. Nodal's admin experience can also
   let non-technical users propose context changes as pull requests for the data
   team to review. Self-hosting a read-only server over the raw files remains
   free; the hosted service adds authentication, usage logging, and the managed
   editing flow. Private-cloud and VPC deployments are available.

3. **Keep it correct — the learning loop.**
   The enterprise layer adds observability into the questions people ask,
   coverage evaluation for questions with thin context, regression tests as
   definitions change, scheduled dashboard re-verification, and dbt-repository
   synchronization. Upstream changes re-draft affected definitions for an
   analyst to confirm. The open seed format and one-shot local runner remain
   free.

## Methodology: why interview-built, not auto-built

The obvious approach is to ingest a warehouse, dbt project, BI layer, and query
history and automatically generate a context layer. Nodal deliberately does not
treat that output as truth.

Anthropic's data team reported that automatically generated metric definitions
“encoded the very ambiguities we were trying to eliminate” and were net-negative
on evaluations compared with a smaller human-curated layer. Giving the agent
grep access to thousands of prior queries moved accuracy by less than one point:
the information was present, but it did not resolve the question to the right
entity. See [Anthropic's self-service analytics case study](https://claude.com/blog/how-anthropic-enables-self-service-data-analytics-with-claude).
Other published examples include work from
[Meta](https://medium.com/@AnalyticsAtMeta/inside-metas-home-grown-ai-analytics-agent-4ea6779acfb3)
and [Ramp](https://engineering.ramp.com/post/meet-ramp-research).

The practical conclusion is to let the model draft documentation while a human
owns the definition. Nodal extracts schema, dbt, documentation, dashboards, and
query history as evidence to correct—not as an authority to trust silently.

Dashboard verification follows the same rule. Reading a value and its filters
from a dashboard the analyst has blessed is ground-truth harvesting, not
automatic definition extraction. The analyst still decides what the metric
means and confirms every captured example.

Every confirmed disambiguation—“active client means X, not Y”—becomes both a
context entry and a labeled evaluation seed. Building context also creates the
ground truth needed to measure it.

## Two interview depths

The roughly 30-minute test drive covers one domain with five questions: the
grain of the canonical table, one ambiguous entity, the top metrics, the
standard hygiene filter, and one silent failure. It verifies selected answers
against the warehouse and leaves unasked material as `status: draft`.

The output remains human-owned, includes eval seeds, and is depth-stamped so a
quick start never masquerades as complete coverage. The full interview uses the
same governed flow without the five-question budget. Its evaluation punch list
shows which domains deserve deeper work.

Teams that already have context in ACF, Kaelio KTX, dbt docs, Markdown, or an
agent data skill can evaluate it as-is. The test drive is a low-cost way to mint
the labeled seeds required to measure whether that existing context helps.

## Sharing context across a team

A context repository is readable Markdown and YAML. A single analyst can point
their own agent at a local checkout for free. Team-wide use needs a delivery
layer so every agent gets the same reviewed definitions.

A hosted MCP endpoint retrieves the relevant definitions and canonical query
guidance for each question. An optional second connector can expose dbt or
warehouse lineage so the agent can inspect how a metric is computed, not only
what it means.

Three deployment paths:

- **Launch on Nodal.** Subscribe, connect a read-only GitHub token, and share the
  endpoint. Nodal serves the context repository, not the customer's database.
- **Self-host.** Build a small read-only MCP server over the raw context files.
  The format remains open and portable.
- **Deploy in the customer's cloud or VPC.** Use this path for data-residency or
  infrastructure-control requirements.

The managed product provides authentication, usage logging, and a workflow where
non-technical users can propose edits through pull requests. Those services are
conveniences for team-scale distribution, not a lock on the context files.

## Claude Desktop and uploaded-skill deployment

Teams that prefer an uploaded skill snapshot can compile a context repository:

```bash
python3 scripts/compile_skill.py path/to/analytics-context --zip
```

The result is a `<company>-data-analyst` skill containing `SKILL.md` and its
references. An administrator can upload it to Claude Desktop or Claude.ai. The
artifact is stamped with its source repository commit and should be regenerated
after every merge. It is a deployable cache, not a second source of truth. The
evaluation harness can grade the compiled skill with the same domain names and
seeds as the source repository.

## Keeping context synchronized with dbt

Context becomes stale when an upstream dbt model changes: columns are renamed,
metrics are redefined, tables disappear, or join behavior changes. Stale context
is dangerous because agents trust it.

The open-source context repository includes a drift-detection contract. A dbt
repository can publish its credential-free `manifest.json` and notify the
context repository when relevant models change. The context workflow then flags
affected domains for human reconfirmation. Sources that cannot be checked fail
loudly rather than silently passing.

The managed learning loop extends that contract. Connect the dbt repository and
upstream changes re-draft affected context definitions, route them to the
analyst, and retain human confirmation as the authority. Managed synchronization
uses the same lineage pointers as the open format and is available in Nodal's
enterprise deployment.

Technical setup for the repository-dispatch workflow remains in
[`template/dbt-repo/README.md`](../template/dbt-repo/README.md).

## Free and paid capability boundary

| Capability | Where | Cost |
|---|---|---|
| Analytics Context Format and schemas | `SPEC.md`, `schemas/` | Free, Apache-2.0 |
| Context interview, including the test drive | Agent skills | Free |
| Eval-seed harvesting | Context interview | Free |
| One-shot context-on/context-off evaluation | Local harness | Free |
| Analytics planning and result verification | Agent skills | Free |
| Dashboard verification in the user's browser | Agent skill | Free |
| Compiled skill snapshot for Claude Desktop | Local script | Free |
| Self-hosted use over raw context files | Customer infrastructure | Free |
| Team-shared governed MCP endpoint | Nodal hosted | Paid, self-serve |
| Authentication, usage logging, and non-technical editing through PRs | Nodal hosted | Paid, self-serve |
| dbt synchronization and analyst reconfirmation | Nodal managed | Paid, enterprise |
| Observability, coverage evaluation, regression testing, drift detection, and scheduled dashboard verification | Nodal managed | Paid, enterprise |

The hosted MCP endpoint is the self-serve entry point: connect the context
repository and share governed definitions without connecting Nodal to the
warehouse. The continuous learning loop and managed dbt synchronization are the
enterprise path. For deployment requirements or a demo, contact
[info@nodaldata.io](mailto:info@nodaldata.io).
