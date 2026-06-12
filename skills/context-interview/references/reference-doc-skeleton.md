# Reference Doc Skeleton

`reference.md` is the file the agent reads **at query time** to answer a question in
this domain. Write it for an LLM, not a person: explicit routing, grain, filters,
and wrong-answer modes — no narrative warm-up. This skeleton mirrors the structure
Anthropic's data team published as their per-domain reference doc, adapted to ACF.

The difference from `context.md`: `context.md` is for a human onboarding to the
domain; `reference.md` is for an agent deciding *which table, which filter, which
grain* in the next three seconds. Keep them separate.

## Template — fill the brackets, delete what doesn't apply

```markdown
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
- [Default cuts and worked patterns where the exact query form is the hard part —
  described, not pasted as runnable SQL]

## Cross-references
- [Neighboring domain reference docs that own adjacent questions]
```

## Rules

- **Routing triggers are the highest-leverage section.** They're what turn "the
  agent searched a thousand fields" into "the agent went straight to the right
  table." Write them as `IF … THEN/DO NOT …`.
- **Grain at the top, always.** State what one row is before anything else.
- **No statistics, no runnable SQL.** Describe patterns; the executable form lives
  in the warehouse / semantic layer, not here.
- **Name the aliases.** If a concept is `client_status` in one table and
  `weekly_status` in another, say so — alias confusion is a silent failure.
- **Every gotcha should also be an eval seed.** If you wrote "exclude BHPN" here,
  there should be a seed that fails when the agent forgets to.
