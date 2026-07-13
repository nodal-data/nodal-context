"""Load eval seeds (`*.seed.yaml`, the shape in schemas/evalseed.schema.json) from a
directory tree.

Factored out of the acf adapter so the runner's `--seeds` flag can attach ground truth
to a context source that carries none — per INTERFACE.md, non-ACF adapters (ktx/dbt/raw)
produce an NCR with no seeds, so the harness needs an external seed source to grade.
"""
from pathlib import Path

from .ncr import Seed


def load_seeds(root):
    import yaml
    root = Path(root)
    seeds = []
    for f in sorted(root.rglob("*.seed.yaml")):
        try:
            doc = yaml.safe_load(f.read_text()) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(doc, dict) or not doc.get("question"):
            continue
        seeds.append(Seed(
            question=doc.get("question", ""),
            domain=doc.get("domain", ""),
            intent=doc.get("intent", ""),
            expected=doc.get("expected", {}) or {},
            provenance=doc.get("provenance", ""),
            status=doc.get("status", ""),
            path=str(f.relative_to(root)) if f.is_relative_to(root) else str(f),
        ))
    return seeds
