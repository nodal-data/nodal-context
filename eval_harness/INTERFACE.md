# Eval Harness Interface

The seam between the free context layer and Nodal. This file
defines a **contract**, not an implementation. The open-source side defines the
inputs and the delta report shape; the trustworthy "perfect" baseline, continuous
re-evaluation, drift detection, and observability are the commercial
implementation (Nodal).

The harness is **format-agnostic by design.** It does not require ACF. It reads
whatever context you have, normalizes it, and measures the same way. This keeps the
measurement — not the context format — as the thing that matters.

## Inputs (any one or more)

All five adapters are implemented in `adapters/` (`--adapter acf|ktx|dbt|raw|skill`).

| Adapter | Reads | Notes |
|---|---|---|
| `acf` | this repo's ACF (`SPEC.md`) | richest: carries seeds + lineage + status |
| `ktx` | Kaelio `semantic-layer/<connection>/*.yaml` + `wiki/**/*.md` | bring an existing ktx project; one domain per connection |
| `dbt` | `manifest.json` (or bare `models/**/*.yml` docs) | model/column docs, unique-test grain evidence, semantic models + metrics (manifest v12); one domain per top-level `models/` folder |
| `raw` | a directory of markdown | last resort; one domain per subdirectory |
| `skill` | an agent data-analysis skill (`SKILL.md` + `references/**/*.md`), folder or packaged `.zip`/`.skill` | e.g. the output of Anthropic's `data-context-extractor`; one domain per reference file, `SKILL.md` + entities/metrics references shared across domains |

Each adapter maps its source into the **Normalized Context Representation (NCR)** —
a single intermediate the rest of the harness operates on. That's why the format
isn't the moat: every format collapses to NCR, and the delta is computed on NCR. We
are constantly looking to increase our adapters, like Cortex, Genie, Hex, Looker, Atlan, etc. 

### Normalized Context Representation (NCR)

```yaml
entities:    [ {name, meaning, disambiguation, aliases, lineage?} ]
metrics:     [ {name, definition, grain, params, caveats, lineage?} ]
routing:     [ {trigger, table, do_not} ]          # from reference.md IF/DO-NOT
seeds:       [ {question, intent, ir?, expected, provenance, status} ]   # ACF only; others: empty
```

Non-ACF inputs produce an NCR with **no seeds** — which is the point: without the
interview you have context but no ground truth. The runner's `--seeds <dir>` flag
attaches an external directory of `*.seed.yaml` files (the shape in
`schemas/evalseed.schema.json`; each seed's `domain` must name one of the adapter's
context domains) so any adapter can be graded. (This is a concrete reason the
interview is worth running even if you already have a ktx or dbt context — it's what
mints the seeds.)

## The three measurements

Given an NCR and a seed set, run the target agent over the seeds three ways:

1. **context-off** — agent answers with raw warehouse access only.
2. **context-on** — agent answers with the NCR injected (as MCP resources / skill).
3. **perfect** — the confirmed seed answer (human-anchored ground truth).

Grade by `expected.kind`:
- `semantic_entity` → did it resolve to the right governed entity?
- `sql_shape` → does the query satisfy `must_include` / `must_exclude`?
- `value_at_snapshot` → does the number match at the pinned date?

## Modes: how context reaches the subject

The *subject* — the thing that turns a seed question into an answer — is pluggable;
seeds, grading, and the report are mode-independent.

- **`inject` (implemented, the default):** one API call per condition; context-on
  pastes the NCR context text into the prompt, context-off omits it. No MCP, no
  warehouse. This isolates **context quality**: the payload is a fixed string, so the
  delta has no retrieval variance. Blind spot: an agent failing to *find* good context
  in production is invisible here.
- **`mcp` (planned):** run each seed through a headless agent session under **named
  MCP configurations** (e.g. `off` = warehouse only, `on` = warehouse + context MCP,
  plus arbitrary combinations), measuring **context + retrieval + tool use** — the
  production state. Because the agent executes against a live warehouse, this mode
  also unlocks grading `value_at_snapshot` seeds, which `inject` must skip.

## The delta report (the aha)

```
Domain: session-financials   (seeds: 34 confirmed, 0 draft excluded)

  context-off   → 41%   ███████░░░░░░░░░░
  context-on    → 88%   ████████████████░   (+47 pts)
  perfect       → 100%

  Still wrong with context on (the punch-list):
    • "GMV by payer"        forgot blank-payer caveat        [sql_shape]
    • "active providers"    used dim_provider, not CPC level [routing]
    • "Cigna collection"    aggregated across TX/FL          [sql_shape]
```

Two numbers, both meaningful: **on-vs-off** proves the context is worth maintaining;
**on-vs-perfect** is the punch-list that drives the next interview round — and the
reason to keep a subscription, because that list regenerates every time a model
changes.

## Free vs paid boundary

- **Free / OSS:** the adapters, the NCR spec, the grading definitions, and a
  one-shot local runner that produces the delta report above for a single domain.
  Enough to see the aha once. In practice today this runner is the interview's
  **Stage 5 live verification** (`skills/context-interview/references/live-verification.md`):
  it answers off vs on against the live warehouse in-session and has the analyst
  confirm the truth against a dashboard — which is also how it mints the
  `dashboard`-provenance seeds the NCR otherwise lacks (a non-ACF context has
  context but no seeds; the interview supplies them).
- **Paid / Nodal:** the trustworthy hosted "perfect" baseline (managed ground
  truth + blessed-dashboard ingestion), continuous re-evaluation on every PR,
  drift detection wired to `context.config.yaml`, correction harvesting back into
  seeds, and the accuracy time-series / observability that catches silent
  regressions. In short: keeping the delta green as the warehouse changes daily.

## Versioning & stability

This contract is **v0 and pre-1.0 unstable**: the NCR shape, the seed format, and the
delta-report shape may change between minor releases without a deprecation cycle. The
version is stamped in code as `NCR_VERSION` (`eval_harness/ncr.py`); seed files are the
shape validated by `schemas/evalseed.schema.json`.

Version history: **v1** — `Seed` gains an optional `ir` field (the structured
question decomposition, `schemas/ir.schema.json`: metric, dimensions, filters,
grain, time_window). Additive: absent for non-ACF sources and pre-v1 seeds;
grading is unchanged (still keyed on `expected.kind`). When the contract reaches 1.0, NCR
and seed changes will be versioned and backward-compatible within a major version. If
you build a third-party adapter or tooling against the NCR today, pin the repo revision
you built against.

## Why a human-anchored "perfect" is non-negotiable

A delta is only as trustworthy as its ground truth. Auto-generated "expected"
answers encode the same ambiguities the agent has, so the delta would measure
nothing. That's why `status: draft` seeds are excluded from `perfect`, and why the
paid product's core value is *managing trustworthy ground truth*, not generating
more of it.
