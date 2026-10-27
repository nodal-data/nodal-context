"""Method readiness checks. Prose interpretation never becomes a blocking guess."""
import re
import ast

from .expressions import filter_fields
from .registry import signature


def executable_code(body):
    if re.search(r"^\s*(?:`{3,}|~{3,})\s*(?:sql|python|py)\b", body, re.M | re.I):
        return True
    if re.search(r"^\s*(?:SELECT|WITH|INSERT INTO|UPDATE|DELETE FROM|CREATE TABLE|DROP TABLE)\s+", body, re.M):
        return True
    # Code cannot evade the contract by using tildes or leaving the fence untyped.
    for match in re.finditer(r"^\s*(`{3,}|~{3,})([^\n]*)\n(.*?)^\s*\1\s*$", body, re.M | re.S):
        language, code = match.group(2).strip().lower(), match.group(3)
        if language in {"sql", "python", "py"}:
            return True
        if re.search(r"\b(?:SELECT\b.*?\bFROM|INSERT\s+INTO|DELETE\s+FROM)\b", code, re.I | re.S):
            return True
        try:
            parsed = ast.parse(code)
        except (SyntaxError, ValueError):
            continue
        if any(isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Import, ast.ImportFrom,
                              ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.For,
                              ast.While, ast.With, ast.Call)) for n in ast.walk(parsed)):
            return True
    return False


def inherited_filter_sources(registry, target):
    """Keep constraints on arithmetic components separate, including their owner.

    This is traversal of reviewed expressions, not flattening unlike branch
    populations into a single predicate or interpreting deterministic-form prose.
    """
    pending, seen, sources = [target], set(), []
    while pending:
        node = pending.pop()
        if node.id in seen:
            continue
        seen.add(node.id)
        expression = node.data.get("expression")
        if not expression:
            continue
        sources.append((node, expression.get("mandatory_filters", [])))
        pending.extend(registry.nodes[key] for key in sorted(node.dependencies)
                       if key in registry.nodes and registry.nodes[key].kind == "metric")
    return sources


def check_method(registry, node):
    data = node.data
    targets = []
    for ref in data["metrics"]:
        target = registry.dependency(node, ref)
        if target:
            targets.append(target)
            if not target.defined:
                registry.readiness(node, "method.undefined_metric", "metrics",
                                   "method metric needs an expression or deterministic form", target.id)
    if not targets:
        registry.readiness(node, "method.empty", "metrics", "method needs at least one resolved metric")
    composed_ids = {target.id for target in targets}
    params = data["parameters"]
    names = [p["name"] for p in params]
    if len(names) != len(set(names)):
        registry.error("parameter.duplicate", node.path, "parameters", "duplicate parameter names")
    constants = data.get("constants", [])
    constant_names = [c["name"] for c in constants]
    if len(constant_names) != len(set(constant_names)) or set(names) & set(constant_names):
        registry.error("constant.duplicate", node.path, "constants", "constants and parameters need unique names")
    decisions = data["decisions"]
    ids = [d["id"] for d in decisions]
    if len(ids) != len(set(ids)):
        registry.error("decision.duplicate", node.path, "decisions", "duplicate decision IDs")
    text = node.body + "\n" + "\n".join(d["rule"] for d in decisions)
    # Parameter declarations themselves do not establish actual use.
    text += "\n" + "\n".join(data["checks"] + data["output"]["must_state"])
    for placeholder in re.findall(r"<([A-Za-z_][A-Za-z0-9_-]*)>", text):
        if placeholder not in names and placeholder not in constant_names:
            registry.readiness(node, "parameter.undeclared", "parameters", "undeclared placeholder", placeholder)
    for name in names:
        if not re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text):
            registry.readiness(node, "parameter.unused", "parameters", "declared parameter is unused", name)
    for title in ("When to use", "Procedure"):
        if not re.search(r"^## " + title + r"\s*$", node.body, re.M):
            registry.readiness(node, "method.section", "body", f"missing ## {title}")
    if executable_code(text):
        registry.error("method.code", node.path, "body", "method carries decisions and prose, not runnable SQL/Python")
    procedure = re.split(r"^## Procedure\s*$", node.body, flags=re.M)[-1]
    procedure = re.split(r"^## ", procedure, maxsplit=1, flags=re.M)[0]
    steps = re.findall(r"^\d+\.\s+(.*(?:\n(?!\d+\.|## ).+)*)", procedure, re.M)
    if not steps:
        registry.readiness(node, "method.procedure", "body", "Procedure needs numbered steps citing decision IDs")
    for step in steps:
        if not any(re.search(r"(?<!\w)" + re.escape(key) + r"(?!\w)", step) for key in ids):
            registry.readiness(node, "decision.uncited", "body/Procedure", "each procedure step must cite a decision ID")
    dimension_set = set(data["output"].get("dimensions", []))
    for target in targets:
        registry.check_dimensions(node, dimension_set, target, "dimensions.method",
                                  "output/dimensions", "fixed dimensions must be allowed by every metric")
    if not set(data["output"].get("optional_columns", [])).issubset(data["output"]["columns"]):
        registry.error("output.optional", node.path, "output/optional_columns", "optional columns must belong to output.columns")
    for column in data["output"].get("optional_columns", []):
        if not any(re.search(r"(?<!\w)" + re.escape(column) + r"(?!\w)", d["rule"]) for d in decisions):
            registry.readiness(node, "output.optional_decision", "output/optional_columns",
                               "a decision must explain when the optional column is present", column)
    allowed_numbers = {str(c["value"]) for c in constants}
    aligned = set()
    for decision in decisions:
        field = f"decisions/{decision['id']}"
        if not decision["without_this"].strip():
            registry.readiness(node, "decision.rationale", field + "/without_this", "decision needs a named failure mode")
        for ref in decision.get("references", []):
            resolved = registry.target_file(node, ref)
            if resolved:
                path, anchor, _ = resolved
                # A reference to a governed entity is an actual semantic
                # dependency, not just a valid hyperlink. An unanchored entity
                # file conservatively depends on every definition in that file.
                for referenced in registry.nodes.values():
                    if referenced.path != path:
                        continue
                    if referenced.kind == "entity":
                        if not anchor or anchor == referenced.data["name"]:
                            node.dependencies.add(referenced.id)
                    elif referenced.kind in ("metric", "method"):
                        node.dependencies.add(referenced.id)
                        if referenced.kind == "metric" and referenced.id not in composed_ids:
                            registry.readiness(node, "method.metric_reference", field + "/references",
                                               "referenced metrics must be declared in metrics", referenced.id)
        for ref in decision.get("alignment", []):
            target = registry.resolve(ref, node.domain)
            if not target or target.id not in composed_ids:
                registry.readiness(node, "alignment.target", field, "alignment must reference a composed metric", ref)
            else:
                aligned.add(target.id)
        override = decision.get("overrides")
        if override:
            target = registry.resolve(override["metric"], node.domain)
            if not target or target.id not in composed_ids:
                registry.readiness(node, "override.target", field, "override must reference a composed metric")
            elif not any(override["filter_field"] in set(filter_fields(filters))
                         for _, filters in inherited_filter_sources(registry, target)):
                registry.readiness(node, "override.field", field, "override field is not mandatorily filtered by its metric")
        for constraint in decision.get("constraints", []):
            target = registry.resolve(constraint["metric"], node.domain)
            if not target or target.id not in composed_ids:
                registry.readiness(node, "constraint.target", field, "constraint must reference a composed metric")
                continue
            proposed = constraint["filter"]
            for owner, filters in inherited_filter_sources(registry, target):
                if signature(proposed) in {signature(f) for f in filters}:
                    continue
                fields = set(filter_fields([proposed])) & set(filter_fields(filters))
                covered = (override and registry.resolve(override["metric"], node.domain) == target
                           and fields == {override["filter_field"]})
                if fields and not covered:
                    registry.readiness(node, "constraint.override_required", field,
                                       "changed mandatory-filter constraint requires an explicit override", owner.id)
    # Procedural rules are subject to the same literal contract as decisions.
    # Metadata and the illustrative Worked parameterization section are excluded.
    for field, clause in [(f"decisions/{d['id']}/rule", d["rule"]) for d in decisions] + [("body/Procedure", procedure)]:
        clause = re.sub(r"\[[^\]]*\]\([^)]*\)", "", clause)  # citation URLs are not runtime literals
        clause = re.sub(r"^\s*\d+\.\s+", "", clause, flags=re.M)
        for identifier in ids:
            clause = re.sub(r"(?<![\w-])" + re.escape(identifier) + r"(?![\w-])", "decision_ref", clause)
        for number in re.findall(r"(?:[<>=*/+\-]\s*)(-?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?)\b", clause):
            if number not in allowed_numbers:
                registry.readiness(node, "constant.undeclared", field,
                                   f"computational literal {number} must be a parameter or declared constant")
        if re.search(r"\b\d{4}-\d{2}-\d{2}\b", clause):
            registry.readiness(node, "parameter.literal_date", field, "runtime dates belong in parameters")
        elif re.search(r"\b\d+\b", clause):
            registry.warn("method.literal_review", node.path, field, "review prose literals against declared constants/defaults")
    temporal = {t.data.get("temporal_kind") for t in targets}
    if {"stock", "flow"}.issubset(temporal):
        required = {t.id for t in targets if t.data.get("temporal_kind") in ("stock", "flow")}
        if not required.issubset(aligned):
            registry.readiness(node, "method.alignment", "decisions", "stock/flow composition requires an explicit alignment decision")
    if None in temporal:
        registry.warn("method.temporal_unknown", node.path, "metrics", "temporal_kind unknown; review stock/flow alignment")
    for adjacent in data.get("not_this", []):
        target = registry.resolve(adjacent["target"], node.domain)
        if not target:
            registry.readiness(node, "method.not_this", "not_this", "adjacent target does not exist", adjacent["target"])
