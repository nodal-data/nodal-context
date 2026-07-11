# AUTHORING.md

Rules for agents **editing** this repo (adding or correcting context). For rules on
**answering data questions** from this repo, see `CLAUDE.md`. This repo contains only
Markdown and YAML.

## Do Not
- **No statistics in context.** Qualitative business logic only. Not "~37% of
  sessions" — that belongs in the warehouse.
- **No schema duplication.** Column types live in dbt/Snowflake.
- **No invented definitions.** Leave `_To be confirmed by [owner]._` and
  `status: draft` rather than guessing. Wrong context is worse than missing context.
- **No executable SQL.** Describe patterns in `reference.md`; don't paste runnable
  queries.

## Conventions
- YAML entities/metrics carry `status: draft|confirmed` and a `lineage:` pointer.
- `reference.md` is written for retrieval by an agent (routing triggers, grain,
  gotchas), not as narrative — narrative goes in `context.md`.
- Add `# REVIEW: [question]` where domain-owner verification is needed.

## Continuing this repo (resume or teammate handoff)

Context is built one domain at a time; picking it back up is the normal case.

- **Same machine, later.** Re-run the `context-interview` skill from your clone of
  the tool repo ([github.com/nodal-data/nodal-context](https://github.com/nodal-data/nodal-context)).
  It searches nearby directories for this repo and asks before touching anything;
  if it doesn't find it, give it the path (or this repo's GitHub URL). It reads
  `context.config.yaml`, sees what's already captured, and resumes from the open
  `status: draft` items — it never starts over.
- **A teammate picking it up.** Clone the tool repo, run the `context-interview`
  skill from that clone, and answer "continuing" with this repo's GitHub URL — the
  skill clones it and resumes. (A nearby existing clone works too; the skill finds
  those itself.) Everything needed to continue is committed here.
- **Do I need the dbt repo locally?** Not to answer questions, validate, or run
  evals — CI uses the git URL recorded in `context.config.yaml`. Clone it locally
  (and run `dbt parse`) only when drafting a **new** domain, so the interview can
  seed real drafts from your models; the skill will tell you the exact clone URL.
- **Running the regression evals locally.** No warehouse needed:

  ```bash
  pip install anthropic pyyaml
  export ANTHROPIC_API_KEY=...
  python -m eval_harness.run --adapter acf --domains "<domain>"
  ```

  `value_at_snapshot` seeds are skipped locally — they're verified against the
  live warehouse, and their blessed SQL lives in gitignored `evals/verified/`
  (it does not travel with a clone; re-run the interview's live-verification pass
  to mint new ones). CI runs the same eval delta on every PR once the
  `ANTHROPIC_API_KEY` repo secret is set.
