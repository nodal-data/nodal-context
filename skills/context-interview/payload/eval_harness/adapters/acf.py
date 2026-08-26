"""ACF adapter: an Analytics Context Format repo (or example dir) -> NCR.

Seeds come from evals/seeds/*.seed.yaml (each carries its own `domain`). The context-on
payload per domain is assembled from exactly the material the `data-question` skill tells
an agent to read: company terminology/overview, the domain's reference.md (routing
IF/DO-NOT + caveats), metrics.yaml, and entity files. Missing pieces are simply skipped —
the example repos don't all carry metrics/entities.
"""
from pathlib import Path

from ..ncr import NCR
from ..seeds import load_seeds


def _read(p: Path) -> str:
    try:
        return p.read_text().strip()
    except OSError:
        return ""


def _company_text(root: Path) -> str:
    parts = [_read(p) for p in sorted((root / "company").glob("*.md"))]
    body = "\n\n".join(p for p in parts if p)
    return f"# Company context\n{body}" if body else ""


def _global_entities_text(root: Path) -> str:
    parts = [_read(p) for p in sorted((root / "entities").glob("*.yaml"))]
    body = "\n\n".join(p for p in parts if p)
    return f"# Shared entities\n{body}" if body else ""


def _domain_dirs(root: Path, only):
    base = root / "domains"
    if not base.is_dir():
        return []
    dirs = [d for d in sorted(base.iterdir()) if d.is_dir() and not d.name.startswith("_")]
    if only:
        want = set(only)
        dirs = [d for d in dirs if d.name in want]
    return dirs


def build_ncr(root, domains=None) -> NCR:
    root = Path(root)
    company = _company_text(root)
    shared_entities = _global_entities_text(root)

    context_by_domain = {}
    for d in _domain_dirs(root, domains):
        name = d.name
        blocks = [
            company,
            f"# Domain: {name}\n{_read(d / 'domain.yaml')}",
            _read(d / "reference.md"),
            (lambda t: f"# Metrics\n{t}" if t else "")(_read(d / "metrics.yaml")),
            (lambda t: f"# Domain entities\n{t}" if t else "")(_read(d / "entities.yaml")),
            shared_entities,
        ]
        context_by_domain[name] = "\n\n".join(b for b in blocks if b).strip()

    return NCR(seeds=load_seeds(root), context_by_domain=context_by_domain)
