"""ktx adapter: a Kaelio ktx project -> NCR.

Reads the two directories a ktx project keeps under git (docs.kaelio.com/ktx):

  semantic-layer/<connection-id>/*.yaml   semantic sources: name, table|sql, grain,
                                          columns, measures, segments, joins,
                                          descriptions keyed {user, dbt, ai}
  wiki/**/*.md                            policies/caveats with YAML frontmatter
                                          (summary, tags, sl_refs)

Domain mapping: one domain per connection directory (yaml files sitting directly under
semantic-layer/ fall into a "semantic-layer" domain). Wiki pages are shared context
appended to every domain — they hold cross-source policy by design.

ktx carries approved definitions but no question-level ground truth, so the NCR has no
seeds — attach them with the runner's `--seeds` flag (see INTERFACE.md).
"""
from pathlib import Path

from ..ncr import NCR


def _desc(d) -> str:
    """ktx descriptions are either a plain string or a map keyed by author; a human-
    confirmed description outranks a dbt-inherited one outranks an AI draft."""
    if isinstance(d, dict):
        return next((d[k].strip() for k in ("user", "dbt", "ai") if d.get(k)), "")
    return (d or "").strip() if isinstance(d, str) else ""


def _source_text(doc: dict) -> str:
    name = doc.get("name", "")
    rel = doc.get("table") or (f"sql: {doc['sql']}" if doc.get("sql") else "")
    grain = doc.get("grain")
    grain = ", ".join(grain) if isinstance(grain, list) else (grain or "")
    lines = [f"## Source: {name}" + (f"  ({rel})" if rel else "")]
    if grain:
        lines.append(f"Grain: {grain}")
    if _desc(doc.get("descriptions")):
        lines.append(_desc(doc.get("descriptions")))

    cols = [c for c in doc.get("columns") or [] if isinstance(c, dict) and c.get("name")]
    if cols:
        lines.append("Columns:")
        for c in cols:
            d = _desc(c.get("descriptions"))
            typ = f" ({c['type']})" if c.get("type") else ""
            lines.append(f"  - {c['name']}{typ}" + (f": {d}" if d else ""))

    for key, title, render in (
        ("measures", "Measures (approved)", lambda m: (
            f"  - {m.get('name')} = {m.get('expr')}"
            + (f"  [filter: {m['filter']}]" if m.get("filter") else "")
            + (f" — {m['description'].strip()}" if m.get("description") else ""))),
        ("segments", "Segments", lambda s: (
            f"  - {s.get('name')}: {s.get('expr')}"
            + (f" — {s['description'].strip()}" if s.get("description") else ""))),
        ("joins", "Joins", lambda j: (
            f"  - -> {j.get('to')} ON {j.get('on')}"
            + (f" ({j['relationship']})" if j.get("relationship") else ""))),
    ):
        items = [i for i in doc.get(key) or [] if isinstance(i, dict)]
        if items:
            lines.append(f"{title}:")
            lines += [render(i) for i in items]
    return "\n".join(lines)


def _wiki_text(root: Path) -> str:
    import yaml
    parts = []
    for f in sorted((root / "wiki").rglob("*.md")):
        try:
            body = f.read_text().strip()
        except OSError:
            continue
        header = f"### wiki/{f.relative_to(root / 'wiki')}"
        # Frontmatter: keep summary/tags (they carry the business vocabulary), drop the rest.
        if body.startswith("---"):
            end = body.find("\n---", 3)
            if end != -1:
                try:
                    fm = yaml.safe_load(body[3:end]) or {}
                except yaml.YAMLError:
                    fm = {}
                body = body[end + 4:].strip()
                if fm.get("summary"):
                    header += f"\n{fm['summary']}"
                if fm.get("tags"):
                    header += f"\nTags: {', '.join(str(t) for t in fm['tags'])}"
        if body:
            parts.append(f"{header}\n{body}")
    return "\n\n".join(parts)


def build_ncr(root, domains=None) -> NCR:
    import yaml
    root = Path(root)
    wiki = _wiki_text(root)

    sources_by_domain = {}
    for f in sorted((root / "semantic-layer").rglob("*.yaml")):
        try:
            doc = yaml.safe_load(f.read_text()) or {}
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(doc, dict) or not doc.get("name"):
            continue
        parent = f.parent
        domain = parent.name if parent != root / "semantic-layer" else "semantic-layer"
        sources_by_domain.setdefault(domain, []).append(_source_text(doc))

    context_by_domain = {}
    for domain, blocks in sorted(sources_by_domain.items()):
        if domains and domain not in domains:
            continue
        head = f"# ktx semantic layer — connection: {domain}"
        wiki_block = f"# Wiki (policies & caveats)\n{wiki}" if wiki else ""
        context_by_domain[domain] = "\n\n".join(
            b for b in [head] + blocks + [wiki_block] if b)

    return NCR(seeds=[], context_by_domain=context_by_domain)
