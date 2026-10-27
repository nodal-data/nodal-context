"""ACF 0.3 adapter: expanded, validated registry -> format-neutral NCR.

Ground truth is never included in context components. Dependency definitions and
prose travel across domain boundaries; generic harness code sees only plain data.
"""
from pathlib import Path
import yaml

from acf_runtime import load_context
from acf_runtime.markdown import render_reference
from ..ncr import NCR
from ..seeds import seed_from_record


def _read(path):
    return path.read_text().strip() if path.is_file() else ""


def build_ncr(root, domains=None, *, branch_test=None):
    root = Path(root).resolve()
    registry = load_context(root, branch_test=branch_test)
    if registry.errors:
        raise ValueError("invalid ACF context:\n" + "\n".join(map(str, registry.errors)))
    if registry.governance["mode"] == "governed" and (not registry.governance["approved"] or registry.governance.get("freshness_state") == "unavailable"):
        raise ValueError("governed context unavailable: approval, freshness or dependencies blocked")
    from acf_runtime.governance import blocked_prose_domains
    hidden_prose = blocked_prose_domains(registry) if registry.governance["mode"] == "governed" else set()
    components = {}
    wanted = set(domains) if domains else set(registry.domains)
    if registry.governance["mode"] == "governed":
        from acf_runtime.governance import eligible_domains
        wanted &= eligible_domains(registry)
        if not wanted:
            raise ValueError("governed context unavailable: selected domains are blocked")
    for domain in sorted(wanted & set(registry.domains)):
        node_ids = {n.id for n in registry.nodes.values() if n.domain == domain and n.kind in ("metric", "method", "entity", "domain")}
        node_ids.update(n.id for n in registry.nodes.values() if n.kind == "entity" and not n.domain)
        pending = list(node_ids)
        while pending:
            key = pending.pop()
            for dep in registry.nodes[key].dependencies - node_ids:
                node_ids.add(dep)
                pending.append(dep)
        relevant_domains = {domain} | {registry.nodes[k].domain for k in node_ids if registry.nodes[k].domain}
        definitions, method_bodies = [], []
        for key in sorted(node_ids):
            node = registry.nodes[key]
            if node.kind in ("evalseed", "pattern") or (registry.governance["mode"] == "governed" and node.blocking_reasons):
                continue
            # Definitions may be visible for disambiguation, but never silently approved.
            definitions.append(f"# {key} (approval: {node.approval_state}; effective status: {node.effective_status})\n" +
                               yaml.safe_dump(node.data, sort_keys=False))
            if node.blocking_reasons:
                definitions.append("Blocked: " + ", ".join(sorted(node.blocking_reasons)))
            if node.kind == "method":
                method_bodies.append(f"# {key} (approval: {node.approval_state}; effective status: {node.effective_status})\n" + node.body)
        components[domain] = {
            "definitions": "\n\n".join(definitions),
            "reference": "\n\n".join(render_reference(_read(root / "domains" / d / "reference.md"),
                {n.id.rsplit("#", 1)[1]: n.effective_status for n in registry.nodes.values()
                 if n.kind == "pattern" and n.domain == d})[0] for d in sorted(relevant_domains - hidden_prose)),
            "reasoning": "\n\n".join([*(_read(root / "domains" / d / "context.md") for d in sorted(relevant_domains - hidden_prose)), *method_bodies]),
            "orientation": "\n\n".join(_read(root / "company" / name) for name in ("overview.md", "terminology.md")),
        }
    ncr = NCR(seeds=[seed_from_record(record) for record in registry.seed_records()
                     if record["domain"] in wanted],
              definitions=registry.definitions(), context_components=components,
              capabilities={"matching", "methods", "coverage"},
              diagnostics=[vars(d) for d in registry.diagnostics])
    if registry.governance["mode"] == "branch-test":
        for component in components.values():
            component["orientation"] = "BRANCH TEST: proposed context; no approval or result verification claimed.\n" + component["orientation"]
    ncr.context_by_domain = {domain: ncr.context_for(domain) for domain in components}
    return ncr
