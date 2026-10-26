# Reference Doc Skeleton

`reference.md` is the file the agent reads **at query time** to answer a question in
this domain. Write it for an LLM, not a person: explicit routing, grain, filters,
and wrong-answer modes — no narrative warm-up. This skeleton mirrors the structure
Anthropic's data team published as their per-domain reference doc, adapted to ACF.

`reference.md` supplies routing, grain and filters for equivalent questions.
`context.md` explains the business reasoning to both humans and agents handling
new slices, decompositions and methods. Structured definitions are always loaded;
the prose ladder adds these documents according to the question's relation.

## Template — fill the brackets, delete what doesn't apply

````markdown
# [Domain] Reference

## Quick Reference
- **Business context** — [what this domain means in one plain sentence]
- **Entity grain** — [what one row represents; the #1 wrong-answer mode if wrong]
- **Standard hygiene filter** — [the WHERE clause every correct query here applies]
- **Canonical table** — [the single source-of-truth table for this domain]

## Routing triggers
- IF the question is about [X] → use `[table]`, grain `[…]`
- IF the question is about [Y] → DO NOT use `[table]`; use `[other_table]` because […]
- IF [ambiguous term] appears → clarify [which entity] before querying
- IF [timing-sensitive metric] → apply [age cutoff] unless told otherwise

## Dimensions
- [How the key dimensions are encoded, and where the SAME concept is named
  differently across tables — list the aliases]

## Key tables
### [table_name]   ← canonical
- **Grain**: [...]  ·  **Scope / exclusions**: [...]
- **Use for**: [...]  ·  **Do NOT use for**: [...]
- **Required filters**: [...]  ·  **Join keys**: [...]
[... one short block per governed table ...]

## Gotchas
- [The plausible-but-wrong modes a senior analyst would warn about — each a
  one-liner the agent can scan]

## Common query patterns
- [Default cuts described as prose one-liners]

<a id="pattern-[slug]"></a>
### [pattern name]   <!-- a fenced sql block ONLY where the exact form is the hard part -->
Without this: [the plausible-but-wrong result the obvious query produces]
```sql
-- pattern, not paste: real model/column names, <placeholders> for parameter
-- values — never a complete runnable report
SELECT ...
```

## Cross-references
- [Neighboring domain reference docs that own adjacent questions]
````

## Rules

- **Routing triggers are the highest-leverage section.** They're what turn "the
  agent searched a thousand fields" into "the agent went straight to the right
  table." Write them as `IF … THEN/DO NOT …`.
- **Grain at the top, always.** State what one row is before anything else.
- **No statistics; SQL only as patterns.** Numbers go stale. A fenced `sql` block
  is allowed ONLY under "Common query patterns", and only where the exact query
  form is the hard-won knowledge — pattern, not paste: real model/column names,
  `<placeholders>` for parameter values, each led by a `Without this:` line naming
  the failure it prevents, a handful per domain, analyst-confirmed (drafts marked
  a working-branch review note), and **never mined from query logs** — a pattern comes
  from the interview or a Stage-5 verified match. Full rule: `SPEC.md` "Query
  patterns". Runnable approved SQL stays in ignored plaintext sidecars; configured
  ciphertext travels separately as an answer key. Neither is answering context.
  When a measure fits the expression grammar, record it in
  `metrics/<name>.yaml`. Otherwise name the unsupported construct in
  `expression_blocked_by` and link `deterministic_form` to the confirmed
  `reference.md#pattern-<slug>` anchor or root `methods/<slug>`. Never invent an
  expression for window functions or other unsupported constructs.
- **Keep rationales aligned.** Name expression metrics in reference routing.
  Map each `Without this:` to a filter/ratio reason or method decision. Only use
  models in domain lineage; draft patterns must be marked before their content
  and must not be compiled as confirmed guidance. Semantic lint warnings require
  review; no warning is not proof of agreement.
- **Name the aliases.** If a concept is `client_status` in one table and
  `weekly_status` in another, say so — alias confusion is a silent failure.
- **Every gotcha should also be an eval seed.** If you wrote "exclude BHPN" here,
  there should be a seed that fails when the agent forgets to.
