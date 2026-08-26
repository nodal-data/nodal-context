"""skill adapter: an agent data-analysis skill -> NCR.

Reads the artifact produced by skill-based context extractors (e.g. Anthropic's
`data-context-extractor`): a skill folder — or the packaged `.zip` / `.skill` file —
laid out as

  SKILL.md            frontmatter (name, description) + the main context body:
                      dialect notes, entity disambiguation, terminology, standard
                      filters, key metrics, common query patterns
  references/**/*.md  per-domain reference files (orders.md, tables/customers.md, …)

Domain mapping: one domain per references markdown file (its stem). The SKILL.md
body is shared context prepended to every domain, and so are
`references/entities.md` / `references/metrics.md` — the skill template defines
those two as cross-domain (entity definitions and KPI formulas). A skill with no
per-domain reference files becomes a single domain named after the skill
(frontmatter `name`, else the folder name). Non-markdown reference assets
(e.g. dashboards.json) are ignored.

A skill carries no question-level ground truth, so the NCR has no seeds — attach
them with the runner's `--seeds` flag (see INTERFACE.md). That asymmetry is the
point: a generated skill is context without measurement; the interview mints the
seeds that grade it.
"""
import tempfile
import zipfile
from pathlib import Path

from ..ncr import NCR

# references/ stems the skill template defines as cross-domain, not domains.
_SHARED_REFERENCES = {"entities", "metrics"}


def _read(p: Path) -> str:
    try:
        return p.read_text().strip()
    except OSError:
        return ""


def _split_frontmatter(text: str):
    """-> (meta dict, body). Tolerates absent or unparseable frontmatter."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    import yaml
    try:
        meta = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        meta = {}
    return (meta if isinstance(meta, dict) else {}), text[end + 4:].strip()


def _skill_dir(root: Path) -> Path:
    """The directory holding SKILL.md: root itself, or one child deep (zip layout)."""
    if (root / "SKILL.md").is_file():
        return root
    nested = sorted(p.parent for p in root.glob("*/SKILL.md"))
    return nested[0] if nested else root


def _build_from_dir(skill_dir: Path, domains) -> NCR:
    meta, body = _split_frontmatter(_read(skill_dir / "SKILL.md"))
    name = str(meta.get("name") or skill_dir.name)
    shared = [f"# Skill: {name}\n{body}" if body else ""]

    per_domain = {}
    refs = skill_dir / "references"
    for f in sorted(refs.rglob("*.md")):
        text = _read(f)
        if not text:
            continue
        block = f"# references/{f.relative_to(refs)}\n{text}"
        if f.stem in _SHARED_REFERENCES:
            shared.append(block)
        else:
            per_domain.setdefault(f.stem, []).append(block)

    shared_text = "\n\n".join(b for b in shared if b)
    context_by_domain = {}
    for domain, blocks in sorted(per_domain.items()):
        if domains and domain not in domains:
            continue
        context_by_domain[domain] = "\n\n".join(b for b in [shared_text] + blocks if b)

    # No per-domain reference files -> the whole skill is one domain.
    if not per_domain and shared_text and (not domains or name in domains):
        context_by_domain[name] = shared_text

    return NCR(seeds=[], context_by_domain=context_by_domain)


def build_ncr(root, domains=None) -> NCR:
    root = Path(root)
    if root.is_file() and zipfile.is_zipfile(root):
        # The packaged deliverable (package script zips <skill-name>/...). Extract to a
        # temp dir; the NCR holds only strings, so the dir can be cleaned up on return.
        with tempfile.TemporaryDirectory() as td:
            with zipfile.ZipFile(root) as zf:
                zf.extractall(td)
            return _build_from_dir(_skill_dir(Path(td)), domains)
    return _build_from_dir(_skill_dir(root), domains)
