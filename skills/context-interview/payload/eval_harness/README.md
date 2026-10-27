# eval_harness

The OSS one-shot **eval-delta runner**: it measures whether your analytics context
actually makes an agent more accurate. For each eval seed it answers the question
**context-off** vs **context-on**, grades shape, method and escalation obligations,
and prints a paired positive delta with separate negative accuracy and skipped
component counts. Numeric checks need actual execution evidence.

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
context quality in isolation). Explicit customer regression and interactive
dashboard/notebook verification are separate operations; see INTERFACE.md. Context-on
calls cache the injected context block, so seeds after the first in a domain read the
prompt cache instead of re-paying for the context.

Bring-your-own key (`ANTHROPIC_API_KEY`); with no key it skips gracefully so CI stays
green without computing a delta. One-shot customer regression is also local:

```bash
python3 scripts/regress.py --root <context-root> \
  --executor '["/absolute/customer-executor", "--read-only"]' \
  --identity <customer-managed-key-file>
```

It replays approved SQL with read-only customer execution and explicit snapshot
attestations. Missing keys/executors/history are skipped. Its stdout contains only
seed IDs/status/categories; private evidence stays ignored. It does not measure a
new AI answer or uplift. Hosted scheduling, history and observability remain
separate products.

## Files

- **[`INTERFACE.md`](./INTERFACE.md)** — the format-agnostic **contract** this package
  implements (adapters → normalized records → matching, grading and reporting).
  Read it first; it's the source of truth, not this README.
- `run.py` — CLI entry / orchestration.
- `adapters/` — source format → NCR (all five contract adapters: `acf`, `ktx`, `dbt`, `raw`, `skill`).
- `client.py` — Anthropic generate (answer) + judge (grade).
- `grader.py` — grade by `expected.kind`; `report.py` — the delta report; `ncr.py` — the
  Normalized Context Representation (versioned: `NCR_VERSION`, pre-1.0 — see
  INTERFACE.md "Versioning"); `seeds.py` — the shared `*.seed.yaml` loader
  behind `--seeds`.
- `execution.py`, `regression.py` — customer executor protocol and SQL preflight;
  ACF selection/decryption lives in `acf_runtime/regression.py`.
