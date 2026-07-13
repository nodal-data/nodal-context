# eval_harness

The OSS one-shot **eval-delta runner**: it measures whether your analytics context
actually makes an agent more accurate. For each eval seed it answers the question
**context-off** vs **context-on**, grades the generated SQL's shape against the seed's
`expected`, and prints an on/off/perfect delta report.

```bash
# ACF context repo (seeds come with it):
python -m eval_harness.run --adapter acf --domains "<domain>" --report pr-comment

# Any other context source (ktx / dbt / raw / skill) + your own seeds:
python -m eval_harness.run --adapter dbt --root path/to/dbt_project --seeds path/to/seeds
python -m eval_harness.run --adapter ktx --root path/to/ktx_project --seeds path/to/seeds
python -m eval_harness.run --adapter raw --root path/to/markdown_dir --seeds path/to/seeds

# Already built a data skill with Claude (e.g. data-context-extractor)? Measure it —
# folder or the packaged zip both work:
python -m eval_harness.run --adapter skill --root path/to/acme-data-analyst.zip --seeds path/to/seeds
```

Only ACF carries ground truth; the other adapters produce context-only NCRs, so point
`--seeds` at a directory of `*.seed.yaml` files (shape: `schemas/evalseed.schema.json`,
with `domain` naming one of the adapter's context domains — run once without a key to
see the domains it found).

The runner's `--mode` is `inject` (context pasted into a single-call prompt — measures
context quality in isolation); an `mcp` mode measuring context + retrieval through an
agent with named MCP configurations is planned — see INTERFACE.md "Modes". Context-on
calls cache the injected context block, so seeds after the first in a domain read the
prompt cache instead of re-paying for the context.

Bring-your-own key (`ANTHROPIC_API_KEY`); with no key it skips gracefully so CI stays
green. This is the **free/local** runner — the trustworthy hosted "perfect" baseline,
continuous re-evaluation, drift detection, and observability are the commercial product.

## Files

- **[`INTERFACE.md`](./INTERFACE.md)** — the format-agnostic **contract** this package
  implements (adapters → Normalized Context Representation → on/off/perfect delta).
  Read it first; it's the source of truth, not this README.
- `run.py` — CLI entry / orchestration.
- `adapters/` — source format → NCR (all five contract adapters: `acf`, `ktx`, `dbt`, `raw`, `skill`).
- `client.py` — Anthropic generate (answer) + judge (grade).
- `grader.py` — grade by `expected.kind`; `report.py` — the delta report; `ncr.py` — the
  Normalized Context Representation (versioned: `NCR_VERSION`, pre-1.0 — see
  INTERFACE.md "Versioning & stability"); `seeds.py` — the shared `*.seed.yaml` loader
  behind `--seeds`.
