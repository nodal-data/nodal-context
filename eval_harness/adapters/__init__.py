"""Adapter registry: source format -> NCR builder.

ACF is the first adapter; the contract (eval-harness/INTERFACE.md) names more
(`raw`, `dbt`, `ktx`, …). They're future drop-ins on the same NCR — the runner,
grader, and reporter never touch a source format directly.
"""
from . import acf

_BUILDERS = {
    "acf": acf.build_ncr,
}
_PLANNED = ["raw", "dbt", "ktx"]   # named in INTERFACE.md, not yet built


def get_builder(name):
    if name in _BUILDERS:
        return _BUILDERS[name]
    if name in _PLANNED:
        raise NotImplementedError(
            f"adapter '{name}' is defined in the contract but not yet implemented; "
            f"available now: {', '.join(sorted(_BUILDERS))}")
    raise ValueError(f"unknown adapter '{name}'; available: {', '.join(sorted(_BUILDERS))}")
