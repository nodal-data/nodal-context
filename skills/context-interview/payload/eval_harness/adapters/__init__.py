"""Adapter registry: source format -> NCR builder.

All five contract adapters (eval_harness/INTERFACE.md) are built. The runner, grader,
and reporter never touch a source format directly — only the NCR. Note the seed
asymmetry: only `acf` yields seeds; the others produce context-only NCRs and rely on
the runner's `--seeds` flag for ground truth.
"""
from . import acf, dbt, ktx, raw, skill

_BUILDERS = {
    "acf": acf.build_ncr,
    "dbt": dbt.build_ncr,
    "ktx": ktx.build_ncr,
    "raw": raw.build_ncr,
    "skill": skill.build_ncr,
}


def get_builder(name):
    if name in _BUILDERS:
        return _BUILDERS[name]
    raise ValueError(f"unknown adapter '{name}'; available: {', '.join(sorted(_BUILDERS))}")
