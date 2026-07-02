# nodal-context

## What this repo is
This is the **tool**, not a context layer. It's the open-source project that lets a
team build its analytics context **by interviewing the analyst** — instead of
inheriting stale context from Notion, Slack, or auto-generated dbt docs. It ships
three things: a context **format** (ACF, see `SPEC.md`), an **interview skill** that
fills it in (`skills/context-interview/`), and a format-agnostic **eval harness
contract** that measures whether the context made the agent more accurate
(`eval_harness/INTERFACE.md`). The thesis — interview-built beats auto-built — and
the free/paid line are argued in `README.md`; read it before changing the pitch.

## This is a test bed, optimized for iteration speed
Right now the only user is us, dogfooding. The point of this stage is **quick
internal testing of the skill against real data projects**, finding friction, and
fixing the format/skill before launch. Concretely:

- We run the skill from this cloned repo and have it write output to a **sibling**
  `analytics-context/` directory (the tool repo stays read-only — it is not a
  context repo and must not be authored into).
- Friction goes in `FINDINGS.md` (gitignored scratch), one line as it happens, then
  gets promoted to that file's punch-list once confirmed.
- We **will** migrate to a cleaner, easier-to-install distribution later ("Plan B
  self-containment" in `FINDINGS.md`). Do **not** do that migration yet — it's
  explicitly deferred until the format stabilizes from testing. Favor fast,
  reversible changes over polished packaging for now.

## Don't confuse the two CLAUDE.md files
- **This file** (`/CLAUDE.md`) = rules for an agent **building the tool**.
- **`template/CLAUDE.md`** = rules shipped *into* a generated context repo, for an
  agent **authoring context**. It is a product artifact. Edit it only as a
  deliberate change to what users receive — never treat it as guidance for working
  here.

`.claude/skills/context-interview` is a **symlink** to `skills/context-interview`
(single source of truth, made discoverable to Claude Code in-repo). It is not a
duplicate — edit `skills/context-interview/`.

## The load-bearing invariant: the format lives in five places, keep them in sync
A change to ACF is not one edit. When you change a field, kind, or directory rule,
update all of these together or you'll ship an inconsistent format:

1. `SPEC.md` — the prose definition of ACF (the standard).
2. `schemas/*.json` — the JSON Schemas CI validates YAML against.
3. `template/` — the empty scaffold the skill copies out; must match the schemas.
4. `examples/example-healthcare-company/` — the worked example; must still validate.
5. `skills/context-interview/` — `SKILL.md` + `references/` describe how to produce
   it; the directory contract and field lists are referenced there.

If you touch one, grep the others for the same field/path name and reconcile.

## Principles that are not up for casual change
These are the product's reason to exist; treat them as fixed unless the user is
deliberately revisiting the thesis:

- **Interview, not extraction. A human owns every definition.** The model drafts;
  the analyst confirms. Unconfirmed → `status: draft` (excluded from the eval
  "perfect" baseline). An interview that silently auto-extracts has failed even if
  the files look complete.
- **No statistics in context files.** Qualitative business logic only ("exclude
  BHPN — different reimbursement cycle"), never "~37% of sessions." Numbers go
  stale; logic doesn't.
- **Every confirmed disambiguation emits an eval seed** (`evals/seeds/*.yaml`).
  Building context and harvesting ground truth are the same act — don't drop the
  seed half.
- **The harness is format-agnostic on purpose.** ACF is *one* input, not a
  prerequisite. The measurement (the NCR + delta), not the format, is the moat.
  Don't add features that make ACF mandatory to measure.

## Working in this repo
- Skill behavior is prompt-engineering: changes land in `SKILL.md` and the staged
  `references/*.md` (loaded per interview stage, not all up front — preserve that).
- `.github/workflows/` (`validate-context`, `eval-delta`, `context-drift`) act on a
  *context* repo's contents; they're the CI contract we hand users, not CI for this
  tool. Keep them consistent with the schemas.
- After format changes, the cheap check is: does `examples/` still validate against
  `schemas/`, and does `template/` match? That's the regression test until there's
  a real one. The ACF schemas `$ref` each other (e.g. `lineage.schema.json`), so a
  validator must register every schema in `schemas/` by its `$id` before validating
  — otherwise refs are "Unresolvable" (a setup error, not a content failure). The
  in-repo CI script (`.ci/validate.py`, referenced by `validate-context.yml`) is not
  yet shipped; until it is, validate ad hoc with `referencing` + `jsonschema`:

  ```python
  import json, glob, yaml, jsonschema
  from referencing import Registry, Resource
  registry = Registry().with_resources(
      [(json.load(open(s))["$id"], Resource.from_contents(json.load(open(s))))
       for s in glob.glob("schemas/*.json")])
  # pair each doc with its schema: domain.yaml→domain, *.seed.yaml→evalseed, etc.
  jsonschema.Draft202012Validator(schema, registry=registry).validate(yaml.safe_load(open(doc)))
  ```

  Markdown-only changes (README/CLAUDE/AGENTS/AUTHORING, skills) can't break schema
  validation — but still confirm `template/` and `examples/` stay parallel.
- Commit/push only when asked. Remote: `github.com/nodal-data/nodal-context`.
