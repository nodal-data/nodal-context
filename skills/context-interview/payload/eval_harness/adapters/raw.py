"""Raw adapter: a directory of markdown -> NCR. Last resort; no structure assumed.

Domain mapping: each top-level subdirectory containing *.md files is a domain; *.md files
at the root are shared context prepended to every domain. A flat directory (markdown only
at the root) becomes a single domain named after the directory itself.

Raw markdown carries no ground truth, so the NCR has no seeds — attach them with the
runner's `--seeds` flag (see INTERFACE.md).
"""
from pathlib import Path

from ..ncr import NCR


def _read(p: Path) -> str:
    try:
        return p.read_text().strip()
    except OSError:
        return ""


def _dir_text(d: Path) -> str:
    parts = []
    for f in sorted(d.rglob("*.md")):
        body = _read(f)
        if body:
            parts.append(f"# {f.relative_to(d)}\n{body}")
    return "\n\n".join(parts)


def build_ncr(root, domains=None) -> NCR:
    root = Path(root)
    shared = "\n\n".join(b for b in (_read(f) for f in sorted(root.glob("*.md"))) if b)

    context_by_domain = {}
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name.startswith((".", "_")):
            continue
        if domains and d.name not in domains:
            continue
        body = _dir_text(d)
        if body:
            context_by_domain[d.name] = "\n\n".join(b for b in (shared, body) if b)

    # Flat layout: no markdown-bearing subdirectories -> one domain, the dir's own name.
    if not context_by_domain and shared and (not domains or root.name in domains):
        context_by_domain[root.name] = shared

    return NCR(seeds=[], context_by_domain=context_by_domain)
