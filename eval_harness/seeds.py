"""Load eval seeds (`*.seed.yaml`, the shape in schemas/evalseed.schema.json) from a
directory tree.

Factored out of the acf adapter so the runner's `--seeds` flag can attach ground truth
to a context source that carries none — per INTERFACE.md, non-ACF adapters (ktx/dbt/raw)
produce an NCR with no seeds, so the harness needs an external seed source to grade.
"""
from pathlib import Path
from dataclasses import fields
from datetime import date, datetime

from .ncr import Seed


def seed_from_record(doc, path=""):
    keys = {f.name for f in fields(Seed)}
    values = {k: v for k, v in doc.items() if k in keys}
    values["path"] = path or doc.get("path", "")
    # Unattributed external seeds are proposed; only adapters supply eligibility.
    values.setdefault("status", doc.get("effective_status", "draft"))
    for required in ("question", "domain", "intent", "expected", "provenance"):
        if required not in values:
            raise ValueError(f"{path}: seed missing {required}")
    return Seed(**values)


def load_seeds(root):
    import yaml

    class SeedLoader(yaml.SafeLoader):
        """Reject ambiguous ground truth instead of accepting the last YAML value."""

        def construct_mapping(self, node, deep=False):
            self.flatten_mapping(node)
            seen = set()
            for key_node, _ in node.value:
                key = self.construct_object(key_node, deep=deep)
                if not isinstance(key, str):
                    raise ValueError(f"mapping keys must be strings (line {key_node.start_mark.line + 1})")
                if key in seen:
                    raise ValueError(f"duplicate mapping key (line {key_node.start_mark.line + 1})")
                seen.add(key)
            return super().construct_mapping(node, deep=deep)

    def portable(value):
        # YAML's implicit date objects must not break JSON matching or prompting.
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: portable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [portable(item) for item in value]
        return value

    root = Path(root)
    seeds = []
    base = root / "evals/seeds" if (root / "evals/seeds").is_dir() else root
    for f in sorted(base.glob("*.seed.yaml")):
        if f.name.startswith("_"):
            continue
        try:
            doc = portable(yaml.load(f.read_text(), Loader=SeedLoader)) or {}
        except ValueError as exc:
            raise ValueError(f"{f}: invalid seed YAML: {exc}") from exc
        except (yaml.YAMLError, RecursionError) as exc:
            # Parser exceptions can echo an entire line of private expected data.
            raise ValueError(f"{f}: invalid seed YAML ({type(exc).__name__})") from None
        if not isinstance(doc, dict) or not doc.get("question"):
            raise ValueError(f"{f}: seed must be an object with a question")
        seeds.append(seed_from_record(doc, str(f.relative_to(root))))
    return seeds
