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

## Source routing

Read only the source types present for the current question.

### ACF

1. `company/terminology.md`
2. the selected `domains/<domain>/reference.md` for routing and `IF … DO NOT …`
3. `domains/<domain>/metrics.yaml`, including `expression.measure`, every
   `mandatory_filters` entry, parameters, caveats, grain, and allowed dimensions
4. `entities/*.yaml`, then domain-specific `entities.yaml`
5. matching confirmed seeds and their local verified-query sidecars when present

Confirmed human-authored claims are `confirmed`. Draft claims remain evidence but
cannot silently become the selected definition.

### KTX

Read the relevant `semantic-layer/<connection>/*.yaml` source and only the linked
or clearly relevant `wiki/**/*.md` pages. Human/user descriptions outrank dbt-
inherited descriptions; AI-authored drafts are `inferred` until confirmed. Preserve
measure expressions, segments, grain, joins, and connection identity.

### dbt

Prefer `target/manifest.json`; fall back to `models/**/*.yml`. Use model and column
descriptions, semantic models, metrics, tests that establish grain, relationships,
accepted values, and lineage. A dbt artifact proves technical structure; it proves
business meaning only when the description is explicit.

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
