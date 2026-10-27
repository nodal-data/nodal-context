"""Dependency-aware impact for authored paths and upstream lineage changes.

Git snapshots contain only context data. Never import or execute code from a
base/PR revision. Invalid/unavailable graphs conservatively select all domains.
"""
from collections import deque
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile

from .loader import load_context, read_yaml


def all_domains(root):
    return sorted(p.name for p in (Path(root) / "domains").glob("*")
                  if p.is_dir() and not p.name.startswith("_"))


def context_path(path):
    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts or "\\" in path:
        return False
    return (path == "context.config.yaml" or
            (len(p.parts) == 3 and p.parts[0] == "domains" and
             (p.suffix in (".yaml", ".md") or p.name == "metrics.yml" or p.name.casefold() == "metrics.lookml")) or
            (len(p.parts) == 4 and p.parts[0] == "domains" and p.parts[2] == "metrics" and p.suffix == ".yaml") or
            (len(p.parts) == 2 and p.parts[0] in ("entities", "methods", "company") and p.suffix in (".yaml", ".md")) or
            (len(p.parts) == 3 and p.parts[:2] == ("evals", "seeds") and path.endswith(".seed.yaml")))


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    if result.returncode:
        raise ValueError("Git revision data is unavailable; fetch the required history")
    return result.stdout


def commit(root, reference):
    value = git(root, "rev-parse", "--verify", "--end-of-options", reference + "^{commit}").decode().strip()
    if not re.fullmatch(r"[a-f0-9]{40,64}", value):
        raise ValueError("invalid Git commit ID")
    return value


def revisions(root, base, head="HEAD"):
    base_id, head_id = commit(root, base), commit(root, head)
    ancestor = git(root, "merge-base", base_id, head_id).decode().strip()
    paths = [p.decode() for p in git(root, "diff", "--name-only", "--no-renames", "-z",
                                     ancestor, head_id, "--").split(b"\0") if p]
    return ancestor, head_id, paths


@contextmanager
def snapshot(root, revision):
    """Materialize contract documents from object IDs; no tar extraction or hooks."""
    revision = commit(root, revision)
    entries = git(root, "ls-tree", "-r", "-z", revision).split(b"\0")
    with tempfile.TemporaryDirectory(prefix="nodal-context-snapshot-") as directory:
        destination = Path(directory)
        total = 0
        for entry in entries:
            if not entry:
                continue
            header, raw_path = entry.split(b"\t", 1)
            path = raw_path.decode()
            if not context_path(path):
                continue
            mode, kind, oid = header.decode().split()
            if mode not in ("100644", "100755") or kind != "blob":
                raise ValueError("context snapshot contains a symlink or non-file contract artifact")
            raw = git(root, "cat-file", "blob", oid)
            total += len(raw)
            if total > 32 * 1024 * 1024:
                raise ValueError("context snapshot exceeds the 32 MiB data limit")
            output = destination / path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(raw)
        yield destination


def graph(registries):
    nodes, dependencies = {}, {}
    for registry in registries:
        for key, node in registry.nodes.items():
            nodes[key] = node
            dependencies.setdefault(key, set()).update(node.dependencies)
            # Blocker edges affect eligibility/impact, never lineage inheritance.
            dependencies[key].update(reason.removeprefix("open_decision:").rsplit("#", 1)[0]
                                     for reason in node.local_blockers if reason.startswith("open_decision:"))
            # Untargeted questions may become answerable after definition changes.
            if node.kind == "evalseed" and not node.dependencies:
                dependencies[key].update(n.id for n in registry.nodes.values()
                                         if n.domain == node.domain and n.kind != "evalseed")
    return nodes, dependencies


def cascade(registries, roots):
    nodes, dependencies = graph(registries)
    reverse = {}
    for key, parents in dependencies.items():
        for parent in parents:
            reverse.setdefault(parent, set()).add(key)
    paths = {key: [key] for key in sorted(roots) if key in nodes}
    pending = deque(paths)
    while pending:
        key = pending.popleft()
        for dependent in sorted(reverse.get(key, [])):
            if dependent not in paths:
                paths[dependent] = [*paths[key], dependent]
                pending.append(dependent)
    objects = [{"id": key, "kind": nodes[key].kind, "domain": nodes[key].domain,
                "path": nodes[key].path, "dependency_path": paths[key],
                "authored_status": nodes[key].data.get("status", "draft"),
                "effective_status": nodes[key].effective_status}
               for key in sorted(paths)]
    return {"objects": objects, "domains": sorted({n.domain for r in registries for n in r.nodes.values()
                                                   if n.id in paths and n.domain}),
            "roots": sorted(roots), "fallback": False, "reasons": []}


def _shared(value):
    if isinstance(value, dict):
        return "shared" in value or bool(value.get("include_filters")) or any(_shared(v) for v in value.values())
    return isinstance(value, list) and any(_shared(v) for v in value)


def affected_paths(paths, registries):
    roots, domains, reasons = set(), set(), []
    for name in paths:
        parts = PurePosixPath(name).parts
        if parts and any(part.startswith("_domain-template") for part in parts):
            continue
        if name == "context.config.yaml" or (parts and parts[0] in (
                "company", "schemas", "acf_runtime", "eval_harness", ".ci")):
            roots.update(n.id for r in registries for n in r.nodes.values())
            reasons.append("cross-cutting context/runtime change: " + name)
            continue
        for registry in registries:
            selected = {n.id for n in registry.nodes.values() if n.path == name}
            if parts and parts[0] == "entities":
                selected.update(registry.nodes)
                reasons.append("shared entity scope is conservative: " + name)
            elif len(parts) > 2 and parts[0] == "domains":
                domains.add(parts[1])
                if parts[-1] == "_shared.yaml":
                    selected.update(n.id for n in registry.metrics if n.domain == parts[1]
                                    and _shared(read_yaml(registry.root / n.path)))
                elif len(parts) == 3:
                    selected.update(n.id for n in registry.nodes.values() if n.domain == parts[1])
            elif parts[:2] == ("evals", "verified"):
                plain = name.removesuffix(".age").removesuffix(".sops")
                selected.update(n.id for n in registry.seeds if n.data.get("verified_query_file") == plain)
            roots.update(selected)
    result = cascade(registries, roots)
    result["domains"] = sorted(set(result["domains"]) | domains)
    result["reasons"] = sorted(set(reasons))
    return result


def conservative(registries, roots, reason):
    result = cascade(registries, {n.id for r in registries for n in r.nodes.values()})
    result.update(fallback=True, reasons=[reason], domains=sorted(set(result["domains"]) |
                  {d for root in roots for d in all_domains(root)}))
    return result


def path_impact(root, paths, *, base_root=None, require_base=True, schemas=None):
    root = Path(root).resolve()
    schema = schemas or (root / "schemas" if (root / "schemas").is_dir() else Path(__file__).resolve().parents[1] / "schemas")
    roots = [Path(base_root).resolve(), root] if base_root is not None else [root]
    registries = []
    try:
        registries = [load_context(path, schemas=schema) for path in roots]
    except Exception:
        # Unsupported/broken schema registries cannot justify a narrow selection.
        return conservative(registries, roots, "base/head graph could not be loaded; evaluating all domains")
    if require_base and base_root is None:
        return conservative(registries, roots, "base graph unavailable; evaluating all domains")
    if any(registry.errors for registry in registries):
        return conservative(registries, roots, "base/head graph cannot be resolved; evaluating all domains")
    return affected_paths(paths, registries)


def lineage_impact(registry, changed_models):
    """Trace each affected object from an upstream model and its direct owner."""
    changed_models = set(changed_models)
    roots, reasons, model_roots = set(), [], {}
    for node in registry.nodes.values():
        own = registry._lineage(node.data.get("lineage"))
        if node.kind == "pattern":
            own = node.lineage
        if node.kind == "entity" and not own:
            own = registry._lineage(registry.domains.get(node.domain, {}).get("lineage"))
            if not node.domain and changed_models:
                roots.update(registry.nodes)
                reasons.append("shared entity has no lineage; all context requires review: " + node.id)
        # The config convenience map also owns lineage for the entire domain.
        configured = registry.config.get("domains", {}).get(node.domain, {}) or {}
        own |= registry._lineage(configured.get("lineage"))
        matched = own & changed_models
        if matched:
            roots.add(node.id)
            model_roots[node.id] = sorted([list(pair) for pair in matched])
    result = cascade([registry], roots)
    result["reasons"] = reasons
    for item in result["objects"]:
        item["changed_models"] = model_roots.get(item["dependency_path"][0], [])
    result["snapshot_batch"] = sorted(n.id for n in registry.seeds if n.id in {
        item["id"] for item in result["objects"]} and n.data["expected"]["kind"] == "value_at_snapshot")
    return result
