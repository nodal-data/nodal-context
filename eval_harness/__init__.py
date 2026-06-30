"""OSS one-shot eval-delta runner for Analytics Context Format (and other adapters).

Measures whether governed context makes an analytics agent more accurate: each eval
seed is answered context-off vs context-on, the query shape is graded against the seed's
`expected`, and a delta report is emitted. Free/local/single-domain by design — the
trustworthy hosted baseline, continuous re-eval, and drift detection are the paid
Nodal offering (see eval-harness/INTERFACE.md).
"""
__all__ = ["run", "ncr", "grader", "report", "client", "adapters"]
