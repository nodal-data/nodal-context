# eval_harness

The OSS one-shot **eval-delta runner**: it measures whether your analytics context
actually makes an agent more accurate. For each eval seed it answers the question
**context-off** vs **context-on**, grades the generated SQL's shape against the seed's
`expected`, and prints an on/off/perfect delta report.

```bash
python -m eval_harness.run --adapter acf --domains "<domain>" --report pr-comment
```

Bring-your-own key (`ANTHROPIC_API_KEY`); with no key it skips gracefully so CI stays
green. This is the **free/local** runner — the trustworthy hosted "perfect" baseline,
continuous re-evaluation, drift detection, and observability are the commercial product.

## Files

- **[`INTERFACE.md`](./INTERFACE.md)** — the format-agnostic **contract** this package
  implements (adapters → Normalized Context Representation → on/off/perfect delta).
  Read it first; it's the source of truth, not this README.
- `run.py` — CLI entry / orchestration.
- `adapters/` — source format → NCR (`acf` built; `raw`/`dbt`/`ktx` planned).
- `client.py` — Anthropic generate (answer) + judge (grade).
- `grader.py` — grade by `expected.kind`; `report.py` — the delta report; `ncr.py` — the
  Normalized Context Representation.
