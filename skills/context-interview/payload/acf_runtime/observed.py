"""Local observed-demand input and bounded variant retention."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from .registry import text_key
from .verified import contained
from eval_harness.execution import strict_json


def read_queue(root, schemas, registry=None):
    path = contained(root, "evals/observed/queue.jsonl", "evals/observed")
    if not path.exists():
        return None
    if not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError("observed queue escapes context root")
    rows, seen = [], set()
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = strict_json(line)
        except ValueError as exc:
            raise ValueError(f"{path}:{number}: invalid JSON: {exc}") from exc
        errors = schemas.errors("observed", row)
        if errors:
            raise ValueError(f"{path}:{number}: {errors[0].message}")
        if row["id"] in seen:
            raise ValueError(f"{path}:{number}: duplicate observation ID")
        if registry is not None:
            if row.get("domain") and row["domain"] not in registry.domains:
                raise ValueError(f"{path}:{number}: unknown observation domain")
            known = {name for n in registry.seeds for name in (
                n.id, n.path, Path(n.path).name, Path(n.path).name.removesuffix(".seed.yaml"))}
            if any(ref not in known for ref in row.get("nearest_seeds", [])):
                raise ValueError(f"{path}:{number}: unknown nearest seed reference")
        seen.add(row["id"])
        rows.append(row)
    return rows


def pending_first(rows):
    """Stable priority: ambiguous, then frequency, then oldest, then ID."""
    return sorted((r for r in rows or [] if r["status"] == "pending"), key=lambda r: (
        r.get("relation") != "ambiguous", -r["count"],
        datetime.fromisoformat(r["asked_at"].replace("Z", "+00:00")), r["id"]))


def distance(a, b):
    """Levenshtein distance, linear storage. Used only for retention, not matching."""
    if len(a) > len(b):
        a, b = b, a
    previous = list(range(len(a) + 1))
    for row, cb in enumerate(b, 1):
        current = [row]
        for col, ca in enumerate(a, 1):
            current.append(min(current[-1] + 1, previous[col] + 1, previous[col - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def retain_variant(seed, variant, maximum=20, threshold=0.1):
    """Pure reviewed insertion. Return updated seed, disposition, overflow entries."""
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
        raise ValueError("variant maximum must be a positive integer")
    if not 0 <= threshold <= 1:
        raise ValueError("near-duplicate threshold must be between zero and one")
    key = text_key(variant["text"])
    updated = deepcopy(seed)
    existing = [seed["question"], *(v["text"] for v in seed.get("variants", []))]
    for text in existing:
        other = text_key(text)
        if key == other or distance(key, other) / max(len(key), len(other), 1) < threshold:
            return updated, "duplicate_dropped", [deepcopy(variant)]
    variants = updated.setdefault("variants", [])
    overflow = []
    if len(variants) >= maximum:
        def stamp(item):
            return datetime.fromisoformat(item[1]["observed_at"].replace("Z", "+00:00")), item[0]
        while len(variants) >= maximum:
            index, _ = min(enumerate(variants), key=stamp)
            overflow.append(variants.pop(index))
    variants.append(deepcopy(variant))
    return updated, "replaced_oldest" if overflow else "appended", overflow
