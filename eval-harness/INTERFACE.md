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

| Adapter | Reads | Notes |
|---|---|---|
| `acf` | this repo's ACF (`SPEC.md`) | richest: carries seeds + lineage + status |
| `ktx` | Kaelio `semantic-layer/*.yaml` + `wiki/*.md` | bring an existing ktx project |
| `dbt` | `manifest.json` + `schema.yml` docs | docs/descriptions as context |
| `raw` | a directory of markdown | last resort; no structure assumed |

Each adapter maps its source into the **Normalized Context Representation (NCR)** —
a single intermediate the rest of the harness operates on. That's why the format
isn't the moat: every format collapses to NCR, and the delta is computed on NCR. We
are constantly looking to increase our adapters, like Cortex, Genie, Hex, Looker, Atlan, etc. 

### Normalized Context Representation (NCR)

```yaml
entities:    [ {name, meaning, disambiguation, aliases, lineage?} ]
metrics:     [ {name, definition, grain, params, caveats, lineage?} ]
routing:     [ {trigger, table, do_not} ]          # from reference.md IF/DO-NOT
seeds:       [ {question, intent, expected, provenance, status} ]   # ACF only; others: empty
```

Non-ACF inputs produce an NCR with **no seeds** — which is the point: without the
interview you have context but no ground truth, so the harness can still measure
on/off but needs a seed source for on-vs-perfect. (This is a concrete reason the
interview is worth running even if you already have a ktx or dbt context.)

## The three measurements

Given an NCR and a seed set, run the target agent over the seeds three ways:

1. **context-off** — agent answers with raw warehouse access only.
2. **context-on** — agent answers with the NCR injected (as MCP resources / skill).
3. **perfect** — the confirmed seed answer (human-anchored ground truth).

Grade by `expected.kind`:
- `semantic_entity` → did it resolve to the right governed entity?
- `sql_shape` → does the query satisfy `must_include` / `must_exclude`?
- `value_at_snapshot` → does the number match at the pinned date?

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

## Why a human-anchored "perfect" is non-negotiable

A delta is only as trustworthy as its ground truth. Auto-generated "expected"
answers encode the same ambiguities the agent has, so the delta would measure
nothing. That's why `status: draft` seeds are excluded from `perfect`, and why the
paid product's core value is *managing trustworthy ground truth*, not generating
more of it.
