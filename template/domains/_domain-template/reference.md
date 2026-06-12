# [Domain] Reference

> Agent-facing retrieval doc. Routing, grain, filters, gotchas — no narrative.
> Skeleton: skills/context-interview/references/reference-doc-skeleton.md

## Quick Reference
- **Business context** — [one plain sentence]
- **Entity grain** — [what one row represents]
- **Standard hygiene filter** — [the WHERE clause every correct query applies]
- **Canonical table** — [source-of-truth table]

## Routing triggers
- IF [question about X] → use `[table]`, grain `[…]`
- IF [question about Y] → DO NOT use `[table]`; use `[other]` because […]
- IF [ambiguous term] → clarify [which entity] before querying

## Dimensions
- [key dimension encodings; same concept named differently across tables]

## Key tables
### [table_name]   ← canonical
- **Grain**: [...] · **Scope/exclusions**: [...]
- **Use for**: [...] · **Do NOT use for**: [...]
- **Required filters**: [...] · **Join keys**: [...]

## Gotchas
- [plausible-but-wrong modes a senior analyst would warn about]

## Common query patterns
- [default cuts; worked patterns described, not pasted as SQL]

## Cross-references
- [neighboring domain reference docs]
