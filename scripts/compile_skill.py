#!/usr/bin/env python3
"""Compile an ACF context repo into an agent data-analysis skill.

Produces the artifact skill-based consumers expect (Claude desktop / claude.ai,
including org-provisioned skills): a `<company>-data-analyst/` folder with
SKILL.md + references/*.md, optionally packaged as a zip. The output is a
STAMPED SNAPSHOT of the repo — a build artifact, not a second source of truth:
regenerate after every merge (or wire that into CI). The eval harness's `skill`
adapter reads the output back with the same domain names as the ACF source, so a
compiled skill is measurable with the same seeds as the repo it came from.

Mapping (the inverse of eval_harness/adapters/skill.py):
  SKILL.md               <- frontmatter + snapshot stamp + how-to-answer rules
                            + company/overview.md + company/terminology.md
                            + knowledge-base navigation table
  references/entities.md <- entities/*.yaml (cross-domain; the skill adapter
                            shares this file across every domain)
  references/<domain>.md <- domain.yaml header + reference.md (draft patterns filtered)
                            + expanded metrics + methods + entities + context.md

Deliberately NOT compiled: evals/ (ground truth, not context), org-structure.md and
repo-operational files. Items with effective `status: draft` are EXCLUDED by default
— a human owns every definition — pass
--include-drafts to keep them, clearly marked.

Usage:
  python3 scripts/compile_skill.py <context-repo> [--out DIR] [--name NAME]
                                   [--zip] [--include-drafts]

Default output: <context-repo>/dist/<company>-data-analyst/ (dist/ is gitignored
in scaffolded repos). Needs: pip install pyyaml
"""
import argparse
import datetime
import re
import subprocess
import sys
import zipfile
from pathlib import Path

CONTAINER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONTAINER / "payload" if (CONTAINER / "payload/acf_runtime").is_dir() else CONTAINER))
from acf_runtime import load_context
from acf_runtime.markdown import render_reference


def _read(p: Path) -> str:
    try:
        return p.read_text().strip()
    except OSError:
        return ""


def _load_yaml(p: Path):
    import yaml
    try:
        doc = yaml.safe_load(p.read_text())
    except (OSError, yaml.YAMLError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _git_stamp(repo: Path) -> str:
    """`<repo-name>@<sha>` (+dirty) — or `<repo-name> (unversioned)` outside git."""
    try:
        sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                               capture_output=True, text=True, check=True).stdout.strip()
        return f"{repo.name}@{sha}" + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return f"{repo.name} (unversioned)"


def _company_name(repo: Path, override: str | None) -> str:
    """From --name, else the first `# ` heading of company/overview.md (minus a
    trailing '— Overview' style suffix), else the repo directory name."""
    if override:
        return override
    for line in _read(repo / "company" / "overview.md").splitlines():
        if line.startswith("# "):
            return re.sub(r"\s*[—–-]+\s*overview\s*$", "", line[2:].strip(),
                          flags=re.IGNORECASE) or "Analytics context"
    return "Analytics context"


def _slug(name: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")


def _body_sans_title(text: str) -> str:
    """Drop a leading `# ` title line — the skill supplies its own headings."""
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def _draft(item: dict) -> bool:
    return str(item.get("status", "confirmed")).strip().lower() == "draft"


def _render_entity(e: dict, drafts: bool) -> str:
    lines = [f"### {e.get('name', '(unnamed)')}" + ("   _(draft — unconfirmed)_" if drafts and _draft(e) else "")]
    if e.get("description"):
        lines.append(str(e["description"]).strip())
    if e.get("important"):
        lines.append(f"**Disambiguation:** {str(e['important']).strip()}")
    mappings = e.get("mappings") or {}
    if isinstance(mappings, dict) and mappings:
        lines.append("Value mappings:")
        lines += [f"- `{k}` → {v}" for k, v in mappings.items()]
    if e.get("analytical_notes"):
        lines.append(f"Notes: {str(e['analytical_notes']).strip()}")
    return "\n".join(lines)


def _render_metric(m: dict, drafts: bool) -> str:
    import yaml
    lines = [f"### {m.get('name', '(unnamed)')}" + ("   _(draft — unconfirmed)_" if drafts and _draft(m) else "")]
    if m.get("definition"):
        lines.append(f"**Definition:** {str(m['definition']).strip()}")
    if m.get("grain"):
        lines.append(f"**Grain:** {str(m['grain']).strip()}")
    params = [p for p in m.get("parameters") or [] if isinstance(p, dict) and p.get("name")]
    if params:
        lines.append("Parameters the question must specify:")
        lines += [f"- `{p['name']}`" + (f" — {p['note']}" if p.get("note") else "") for p in params]
    for key, title in (("caveats", "Caveats"), ("common_filters", "Common filters")):
        vals = [v for v in m.get(key) or [] if v]
        if vals:
            lines.append(f"{title}:")
            lines += [f"- {v}" for v in vals]
    structured = {k: m[k] for k in ("aliases", "alias_notes", "family", "expression",
                  "expression_blocked_by", "deterministic_form", "allowed_dimensions",
                  "lineage", "open_decisions") if k in m}
    if structured:
        lines.append("```yaml\n" + yaml.safe_dump(structured, sort_keys=False).rstrip() + "\n```")
    return "\n".join(lines)


def _render_items(items: list, render, include_drafts: bool):
    """-> (markdown, n_excluded_drafts). Confirmed first, drafts kept only on request."""
    kept, excluded = [], 0
    for it in items:
        if not isinstance(it, dict):
            continue
        if _draft(it) and not include_drafts:
            excluded += 1
            continue
        kept.append(render(it, include_drafts))
    return "\n\n".join(kept), excluded


HOW_TO_ANSWER = """\
## How to answer with this skill

1. Check **Terminology** (below) for what the company's terms mean.
2. Identify the domain and open its file from **Knowledge base navigation** —
   it routes the query (canonical table, grain, routing triggers).
3. Honor every `IF … DO NOT …` routing trigger and caveat you find. When a
   "Common query patterns" block matches the question, start your SQL from its
   form (fill the `<placeholders>`; keep its filters and grain handling).
4. Before computing a metric, honor its listed parameters and caveats; resolve
   ambiguous terms via `references/entities.md`.
5. Issue **read-only** SQL only (SELECT — never DDL/DML) via the warehouse
   connection.
6. If this context is silent on something the answer depends on, **say so** — do
   not invent a definition. State any caveat the answer relies on."""


def _compile_skill(repo: Path, out_dir: Path, name: str | None, include_drafts: bool):
    """-> (skill_dir, stats dict). Writes the skill folder under out_dir."""
    import yaml
    registry = load_context(repo, branch_test=True if include_drafts else None)
    if registry.errors:
        raise SystemExit("compile_skill: invalid ACF 0.3 context:\n" + "\n".join(map(str, registry.errors)))
    if registry.governance["mode"] == "governed" and (not registry.governance["approved"] or registry.governance.get("freshness_state") == "unavailable"):
        raise SystemExit("compile_skill: governed export requires approved revision and live freshness evidence")
    from acf_runtime.governance import eligible_domains, blocked_prose_domains
    allowed_domains = eligible_domains(registry) if registry.governance["mode"] == "governed" else set(registry.domains)
    hidden_prose = blocked_prose_domains(registry) if registry.governance["mode"] == "governed" else set()
    company = _company_name(repo, name)
    slug = f"{_slug(company)}-data-analyst"
    skill_dir = out_dir / slug
    refs_dir = skill_dir / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)
    import json
    (skill_dir / "governance.json").write_text(json.dumps(registry.governance, indent=2) + "\n")
    stats = {"domains": [], "drafts_excluded": 0, "slug": slug}

    # references/entities.md — cross-domain entities (shared by the skill adapter)
    ent_blocks = []
    for node in registry.nodes.values():
        if node.kind != "entity" or node.domain:
            continue
        items = [{**node.data, "status": node.effective_status}]
        md, skipped = _render_items(items, _render_entity, include_drafts)
        stats["drafts_excluded"] += skipped
        if md:
            ent_blocks.append(md)
    if ent_blocks:
        (refs_dir / "entities.md").write_text(
            "# Entity definitions (cross-domain)\n\nAlways resolve ambiguous terms "
            "here before querying.\n\n" + "\n\n".join(ent_blocks) + "\n")

    # references/<domain>.md — one file per confirmed domain
    nav_rows = []
    for d in sorted((repo / "domains").iterdir()) if (repo / "domains").is_dir() else []:
        if not d.is_dir() or d.name.startswith(("_", ".")):
            continue
        if d.name not in allowed_domains:
            stats["drafts_excluded"] += 1
            continue
        dom = {**registry.domains[d.name], "status": registry.nodes["domain:" + d.name].effective_status}
        if _draft(dom) and not include_drafts:
            stats["drafts_excluded"] += 1
            continue
        parts = [f"# {dom.get('name', d.name)}"]
        head = []
        if dom.get("summary"):
            head.append(f"**Covers:** {str(dom['summary']).strip()}")
        tables = dom.get("tables") or {}
        if isinstance(tables, dict) and tables.get("canonical"):
            head.append(f"**Canonical table:** `{tables['canonical']}`")
        if dom.get("grain"):
            head.append(f"**Grain:** {str(dom['grain']).strip()}")
        if head:
            parts.append("\n".join(head))
        if d.name not in hidden_prose and (ref := _read(d / "reference.md")):
            ref, skipped = render_reference(ref,
                {n.id.rsplit("#", 1)[1]: n.effective_status for n in registry.nodes.values()
                 if n.kind == "pattern" and n.domain == d.name}, include_drafts=include_drafts)
            if not include_drafts:
                stats["drafts_excluded"] += skipped
            if ref.strip():
                parts.append(_body_sans_title(ref) or ref)
        metrics_md, skipped = _render_items(
            [{**n.data, "status": n.effective_status} for n in registry.metrics if n.domain == d.name],
            _render_metric, include_drafts)
        stats["drafts_excluded"] += skipped
        if metrics_md:
            parts.append("## Metrics\n\n" + metrics_md)
        dom_ent_md, skipped = _render_items(
            [{**n.data, "status": n.effective_status} for n in registry.nodes.values()
             if n.kind == "entity" and n.domain == d.name], _render_entity, include_drafts)
        stats["drafts_excluded"] += skipped
        if dom_ent_md:
            parts.append("## Domain entities\n\n" + dom_ent_md)
        for method in registry.methods:
            if method.domain != d.name:
                continue
            if method.effective_status != "confirmed" and not include_drafts:
                stats["drafts_excluded"] += 1
                continue
            data = {**method.data, "status": method.effective_status}
            parts.append("## Method: " + data["name"] +
                         (" _(draft — unconfirmed)_" if method.effective_status != "confirmed" else "") +
                         "\n\n```yaml\n" + yaml.safe_dump(data, sort_keys=False) + "```\n\n" + method.body)
        if d.name not in hidden_prose and (reasoning := _read(d / "context.md")):
            parts.append("## Reasoning context for new slices and methods\n\n" + reasoning)
        if d.name not in hidden_prose and (issues := _read(d / "known-issues.md")):
            parts.append("## Known issues\n\n" + (_body_sans_title(issues) or issues))
        (refs_dir / f"{d.name}.md").write_text("\n\n".join(parts) + "\n")
        stats["domains"].append(d.name)
        nav_rows.append(f"| {d.name} | `references/{d.name}.md` | "
                        f"{str(dom.get('summary', '')).strip()} |")

    if not stats["domains"]:
        raise SystemExit(f"compile_skill: no confirmed domains found under {repo}/domains/ "
                         "— is this an ACF context repo? (drafts are excluded unless "
                         "--include-drafts)")
    if ent_blocks:
        nav_rows.append("| entities | `references/entities.md` | cross-domain entity "
                        "definitions and disambiguations |")

    # SKILL.md
    from acf_runtime.governance import revision, digest, context_files
    source_revision = revision(repo) or "sha256:" + digest(context_files(repo))
    drafts_note = (f"\n> {stats['drafts_excluded']} draft (unconfirmed) definition(s) "
                   "were excluded — confirm them in the repo and recompile."
                   if stats["drafts_excluded"] and not include_drafts else "")
    description = (f"{company} data analysis skill, compiled from the team's governed "
                   "analytics context (ACF). Use when answering "
                   f"{company} data, analytics, or warehouse questions — terminology, "
                   "entity definitions, metric calculations, caveats, and query "
                   f"patterns for: {', '.join(stats['domains'])}.")
    skill_md = f"""---
name: {slug}
description: "{description}"
---

# {company} Data Analysis

> **Compiled snapshot — not the source of truth.** Generated from
> `{source_revision}` by `scripts/compile_skill.py`
> ([nodal-context](https://github.com/nodal-data/nodal-context)). The live,
> reviewed context is the ACF repo (and its MCP endpoint, if served).
> Approval provenance is in `governance.json`. This export is an offline snapshot; recheck the live authority before governed use. Branch-test exports are proposed context only.
> Regenerate this skill after every merge; do not edit it by hand.{drafts_note}

{HOW_TO_ANSWER}

## Company overview

{_body_sans_title(_read(repo / "company" / "overview.md")) or "_Not captured._"}

## Terminology

{_body_sans_title(_read(repo / "company" / "terminology.md")) or "_Not captured._"}

## Knowledge base navigation

| Domain | Reference file | Use for |
|---|---|---|
{chr(10).join(nav_rows)}
"""
    (skill_dir / "SKILL.md").write_text(skill_md)
    import hashlib
    proof = {**registry.governance, "format": "acf-export/1", "export_name": company, "export_files": {p.relative_to(skill_dir).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in skill_dir.rglob("*") if p.is_file() and p.name != "governance.json"}}
    (skill_dir / "governance.json").write_text(json.dumps(proof, indent=2) + "\n")
    return skill_dir, stats


def compile_skill(repo: Path, out_dir: Path, name: str | None, include_drafts: bool):
    """Publish a fresh owned build; refuse to delete user-added or edited files."""
    import hashlib
    import json
    import os
    import tempfile
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".acf-build-", dir=out_dir) as work:
        staged, stats = _compile_skill(Path(repo), Path(work), name, include_drafts)
        destination = out_dir / staged.name
        previous = Path(work) / "previous"
        if destination.exists():
            proof_path = destination / "governance.json"
            if destination.is_symlink() or not proof_path.is_file() or proof_path.is_symlink():
                raise ValueError("existing export is not an owned ACF build")
            proof = json.loads(proof_path.read_text())
            files = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in destination.rglob("*") if p.is_file() and p != proof_path}
            if (proof.get("format") != "acf-export/1" or files != proof.get("export_files") or
                    any(p.is_symlink() for p in destination.rglob("*"))):
                raise ValueError("existing export contains user changes; preserve it or use a new output directory")
            os.replace(destination, previous)
        try:
            os.replace(staged, destination)
        except Exception:
            if previous.exists():
                os.replace(previous, destination)
            raise
        return destination, stats


def verify_export(repo, exported, name=None):
    """Recompile from a live-approved source revision; copied proofs aren't trust."""
    import hashlib
    import json
    import os
    import tempfile
    if os.environ.get("ACF_BRANCH_TEST") == "1":
        raise ValueError("export approval cannot be verified in branch-test mode")
    exported = Path(exported)
    proof = json.loads((exported / "governance.json").read_text())
    if proof.get("format") != "acf-export/1" or proof.get("mode") != "governed" or not proof.get("approved"):
        raise ValueError("export is not an approved revision snapshot")
    with tempfile.TemporaryDirectory(prefix="acf-export-check-") as directory:
        rebuilt, _ = compile_skill(Path(repo), Path(directory), name if name is not None else proof.get("export_name"), False)
        live = json.loads((rebuilt / "governance.json").read_text())
        for key in ("revision", "content_digest", "approval", "export_files"):
            if proof.get(key) != live.get(key):
                raise ValueError("export differs from the approved source revision")
        actual = {p.relative_to(exported).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in exported.rglob("*") if p.is_file() and p.name != "governance.json"}
        if actual != live["export_files"] or any(p.is_symlink() for p in exported.rglob("*")):
            raise ValueError("export content changed")
    return live


def package_zip(skill_dir: Path) -> Path:
    """Zip with the `<slug>/...` arcname layout skill consumers (and the harness's
    skill adapter) expect."""
    zpath = skill_dir.parent / f"{skill_dir.name}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(skill_dir.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(skill_dir.parent))
    return zpath


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo", help="path to the ACF context repo to compile")
    ap.add_argument("--out", help="output directory (default: <repo>/dist)")
    ap.add_argument("--name", help="company name override (default: from "
                    "company/overview.md's title)")
    ap.add_argument("--zip", action="store_true", dest="zip_", help="also package "
                    "the skill as <name>.zip next to the folder")
    ap.add_argument("--include-drafts", action="store_true",
                    help="keep status:draft items, marked '(draft — unconfirmed)' "
                    "(default: excluded — a human owns every definition)")
    ap.add_argument("--verify-export", type=Path, help="recheck an export against this live-approved source checkout")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    if not (repo / "domains").is_dir():
        raise SystemExit(f"compile_skill: {repo} has no domains/ directory — point me "
                         "at an ACF context repo (see SPEC.md).")
    if args.verify_export:
        verify_export(repo, args.verify_export, args.name)
        print("compile_skill: export matches live-approved source revision")
        return 0
    out_dir = Path(args.out).resolve() if args.out else repo / "dist"
    skill_dir, stats = compile_skill(repo, out_dir, args.name, args.include_drafts)

    print(f"compile_skill: wrote {skill_dir}")
    print(f"  domains: {', '.join(stats['domains'])}")
    if stats["drafts_excluded"] and not args.include_drafts:
        print(f"  drafts excluded: {stats['drafts_excluded']} (use --include-drafts to keep)")
    if args.zip_:
        print(f"  packaged: {package_zip(skill_dir)}")
    print("  measure it: python -m eval_harness.run --adapter skill "
          f"--root {skill_dir} --seeds {repo / 'evals' / 'seeds'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
