# Context Sources

Use sources through a common evidence contract. The format is not the authority;
the provenance of the particular claim is.

## Evidence record

For each claim that changes the plan, retain:

- `claim`: the definition, routing rule, join, filter, or caveat;
- `source`: stable local path or MCP binding plus document identifier;
- `kind`: ACF, KTX, dbt, documentation, agent skill, warehouse metadata,
  query history, or dashboard;
- `authority`: confirmed, governed, documented, behavioral, or inferred;
- `owner` and `updated_at`: only when the source supplies them;
- `conflicts`: other credible readings and their evidence;
- `used`: whether this claim affected the approved plan.

Do not paste large source bodies into the plan. Cite the smallest useful location
and paraphrase the claim.

## Tool discovery

Identify the capability needed to close the next evidence gap. When the host
supports deferred discovery, return a compact shortlist of names and one-line
summaries using narrow capability/provider matching. Select a tool, then inspect
its full advertised contract, argument schema, prerequisites and authorization
boundaries before calling it. Broaden or page discovery only when needed; never
dump the full catalog or silently drop candidates from an oversized shortlist.

On hosts exposing `ALL_TOOLS`, select names and short summaries first, then look
up the selected entry by exact name. Name/description metadata alone may not
include the argument schema: use the host's supported schema loader or an already
supplied schema. Do not invent arguments or require a host-specific discovery API.
Do not reprint contracts already supplied. This reduces discovery output, not
necessarily the schemas that the host has injected into its initial context.

## Source routing

Read only the source types present for the current question.

### ACF

ACF 0.3 uses `domains/<domain>/metrics/<name>.yaml` and optional `_shared.yaml`;
the old wrapper, LookML metric artifacts and 0.2 repositories require migration.
Read the normalized registry when available, so shared filters/parameters and
transitive references agree across consumers. Otherwise expand the declared
references explicitly and report any unavailable validation/matching capability.

Always read structured metrics and `entities/*.yaml`, then domain entities.
Honor measure, grouped mandatory filters, entity-group filters, parameters, grain,
allowed dimensions, ratio policy and caveats. Methods live at `methods/<slug>.md`:
read declarations, decision rationales, procedure, output and checks. Cross-domain
references bring the relevant definitions with them.

Use the relation-based prose ladder: equivalent metric → domain `reference.md`;
new slice/decomposition or method → also `context.md` and relevant method bodies;
unresolved/ambiguous → also company overview/terminology before escalation. Do
not use a draft pattern as governed query guidance.

Governed use requires live authority evidence of protected human-reviewed merge
at the exact source revision, current freshness checks, and ready dependencies.
Authored status or a branch name is not proof. Missing/expired evidence blocks use. A family or alias collision requires user selection, not a guessed
default. Use seed IDs/IR metadata for structural matching only. Keep expected
answers, seed variants and verified SQL out of answer generation; they belong to
separate verification. Ciphertext availability is not a successful regression.

### KTX

Read the relevant `semantic-layer/<connection>/*.yaml` source and only the linked
or clearly relevant `wiki/**/*.md` pages. Human/user descriptions outrank dbt-
inherited descriptions; AI-authored drafts are `inferred` until confirmed. Preserve
measure expressions, segments, grain, joins, and connection identity.

### dbt

Start from model identifiers or relations in metric lineage. Fetch a known unique
model directly; do not require a project index scan first. If the target is unknown,
use bounded model search or compact index summaries to identify candidates. Resolve
same-name models by project/package and relation identity rather than silently
choosing one. Summaries route discovery; fetch complete evidence before relying on
constraints. A project-wide request may legitimately use a project overview.

Prefer `target/manifest.json` when available locally; parse and select relevant
model nodes and associated test nodes rather than printing the whole artifact.
Fall back to the relevant entries in `models/**/*.yml`. Preserve model and column
descriptions, semantic models/metrics, tests, constraints, relationship targets,
accepted values, source locations and direct dependency identifiers. Read the
selected model's full SQL, distinguishing raw from compiled SQL when supplied.
Missing compiled SQL remains explicit; never substitute invented compilation.

For MCP sources, inspect the advertised capabilities and prefer scoped model
lookup, search and retrieval when available. No particular endpoint name or server
version is required. Otherwise use directory listings and targeted SQL/schema
file reads. Never assume a proposed endpoint or an unsupported column projection
exists. Column selection must retain model-level and cross-column constraints,
relevant tests and relationship targets. Retain tests whose applicability is
uncertain and mark that uncertainty; do not remove them to meet a token budget.
Carry material model-level and cross-column constraints into the plan's evidence
and applicable checks, including constraints already supplied before retrieval.
Retain all columns referenced by a supplied cross-column test. Do not silently
omit the constraint or make it optional because a projection selected fewer
columns. If a test definition has not been retrieved, name the needed evidence;
never invent a concrete predicate, exclusion, or uniqueness requirement.
A dbt data test is evidence to assess, not automatically a new business row filter;
distinguish the test definition from evidence that the test actually passed.

Follow dependencies only to resolve named gaps, such as an upstream account
exclusion or a customer join's cardinality. Multiple metrics may need multiple
models. For a new-customer metric linked to `fct_orders`, retrieve its evidence
and necessary dependencies, not unrelated subscription or marketing model bodies.
Use warehouse metadata to check the actual relation/columns; metadata does not
prove data-level uniqueness, business authority or live governance approval.

### Legacy tools and incomplete responses

Honor a documented initialization prerequisite when it is the only usable route.
Prefer an independent narrow capability when its contract supports the task.
An older connector may require an overview before search or a whole-file read of
shared YAML. Record the unavoidable broad retrieval and avoid repeating it.
Do not pretend the prerequisite has been removed or install a different server.

When an authorized runtime supports structured result selection, retain the full
response there and emit relevant sections with provenance, warnings, errors and
completeness indicators. Use known response structure, not arbitrary text
truncation. If reliable selection is unavailable, accept the broad response;
preserving required evidence takes precedence over reducing tokens.

Retain source/model identity, revision or digest when supplied, requested scope,
returned sections, and omitted/unavailable evidence. Do not invent missing metadata.
Complete required continuations before claiming completeness. A partial index or
failed search does not prove an asset is absent. A summary is not full model
evidence, and complete retrieval is not governance readiness. If a revision changes
mid-pagination, restart the affected retrieval or report a blocker; do not combine
incompatible snapshots. If required sections cannot be recovered, state the gap.

A dbt artifact proves technical structure; it supports business meaning only when
the description is explicit. Technical corroboration does not grant human approval.

### Markdown and agent skills

Search within the configured directory for terms from the question. Read the
entrypoint plus only linked/relevant references. Treat unsupported prose as
`documented`, not confirmed ground truth, unless it names its governing owner and
approval state.

### Documentation MCPs

Use only a connector already loaded and authorized. Search narrowly by domain,
metric, entity, and known aliases; then read the smallest relevant documents.
Record binding, document identifier, title, owner, and last-updated time when the
tool exposes them. Never modify documentation from this skill. An unavailable or
denied connector is an evidence gap, not a reason to request credentials.

### Warehouse and behavioral evidence

Use metadata to validate that named tables, columns, joins, and grains exist. Use
bounded query history or dashboard SQL only to identify recurring institutional
patterns. Recurrence shows behavior, not correctness. Never copy raw history into
the plan or treat popularity as confirmation.

## Authority and conflict policy

Default recommendation order:

1. confirmed human-owned ACF claim;
2. governed human-authored semantic definition;
3. explicit version-controlled dbt/LookML-style definition;
4. owned business documentation;
5. behavioral evidence from dashboards or recurring queries;
6. warehouse/schema inference.

This order selects a recommendation, not an automatic winner. Stop for user choice
when two credible sources define a load-bearing term differently, a lower-ranked
source is newer and explicitly supersedes the higher one, or ownership is unclear.
Record the rejected reading in the eval-seed candidate.
