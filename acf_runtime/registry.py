"""Canonical definitions, dependency graph, lineage and deterministic checks."""
from dataclasses import dataclass, field
from datetime import date
import json
from pathlib import PurePosixPath
import re
import unicodedata

from .expressions import MeasureParser, filter_fields
from .status import resolve_status
from .markdown import pattern_span, pattern_status


def text_key(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def canonical(value):
    """Typed structural identity; reasons do not alter a constraint."""
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in sorted(value.items()) if k != "reason"}
    if isinstance(value, list):
        return [canonical(v) for v in value]
    return value


def signature(value):
    return json.dumps(canonical(value), sort_keys=True, ensure_ascii=False)


@dataclass
class Diagnostic:
    code: str
    severity: str
    path: str
    field: str
    message: str
    target: str = ""
    related: list = field(default_factory=list)

    def __str__(self):
        references = "".join(f"; related {item['path']}:{item['field']}" for item in self.related)
        return f"{self.path}:{self.field or '(root)'} [{self.code}] {self.message}{references}"


@dataclass
class Node:
    id: str
    kind: str
    domain: str
    path: str
    data: dict
    body: str = ""
    dependencies: set = field(default_factory=set)
    lineage: set = field(default_factory=set)
    local_blockers: set = field(default_factory=set)
    blocking_reasons: set = field(default_factory=set)
    effective_status: str = "draft"
    approval_state: str = "unavailable"

    @property
    def dimensions(self):
        return set(self.data.get("expression", {}).get("allowed_dimensions",
                       self.data.get("allowed_dimensions", [])))

    @property
    def defined(self):
        return self.kind == "method" or bool(self.data.get("expression") or self.data.get("deterministic_form"))


class Registry:
    def __init__(self, root, manifests=None):
        self.root, self.manifests = root, manifests or {}
        self.config, self.nodes, self.domains, self.aliases = {}, {}, {}, {}
        self.diagnostics = []
        self.governance = {}
        self.dimension_checks = []
        self.fragment_origins = {}

    @property
    def errors(self):
        return [d for d in self.diagnostics if d.severity == "error"]

    @property
    def metrics(self):
        return [n for n in self.nodes.values() if n.kind == "metric"]

    @property
    def methods(self):
        return [n for n in self.nodes.values() if n.kind == "method"]

    @property
    def seeds(self):
        return [n for n in self.nodes.values() if n.kind == "evalseed"]

    def error(self, code, path, field, message, target=""):
        self.diagnostics.append(self._diagnostic(code, "error", path, field, message, target))

    def warn(self, code, path, field, message, target=""):
        diagnostic = self._diagnostic(code, "warning", path, field, message, target)
        if diagnostic not in self.diagnostics:
            self.diagnostics.append(diagnostic)

    def _diagnostic(self, code, severity, path, field, message, target):
        related = []
        for origin in self.fragment_origins.get(path, []):
            scopes = (origin["expanded_field"], origin["reference_field"])
            if not field or any(field == scope or field.startswith(scope + "/")
                                or scope.startswith(field + "/") for scope in scopes):
                for reference in ({"path": path, "field": origin["reference_field"]},
                                  {"path": origin["path"], "field": origin["field"]}):
                    if reference not in related:
                        related.append(reference)
        return Diagnostic(code, severity, path, field, message, target, related)

    def readiness(self, node, code, field, message, target=""):
        emit = self.error if node.data.get("status") == "confirmed" else self.warn
        emit(code, node.path, field, message, target)
        node.local_blockers.add(f"{code}:{target or field}")

    def check_dimensions(self, node, dimensions, target, code, field, message, *, structural=False):
        # Resolve after the complete dependency lineage is available. Inherited
        # models can prove equivalence between bare and qualified dimensions.
        self.dimension_checks.append((node, set(dimensions), target, code, field, message, structural))

    def _dimensions(self):
        from .columns import column_evidence
        for node, dimensions, target, code, field, message, structural in self.dimension_checks:
            aliases, _ = column_evidence(self.manifests, target.lineage)
            requested = {aliases.get(d, d) for d in dimensions}
            allowed = {aliases.get(d, d) for d in target.dimensions}
            if not requested.issubset(allowed):
                if structural:
                    self.error(code, node.path, field, message, target.id)
                else:
                    self.readiness(node, code, field, message, target.id)

    def add(self, kind, path, data, body=""):
        parts = PurePosixPath(path).parts
        domain = parts[1] if parts[0] == "domains" else data.get("domain", "")
        if kind == "domain":
            self.domains[domain] = data
            key = f"domain:{domain}"
            if data["name"] != domain:
                self.error("name.domain", path, "name", "domain name must equal directory name")
        elif kind == "metric":
            key = f"metric:{domain}.{data['name']}"
        elif kind == "method":
            key = f"method:{data['name']}"
        elif kind == "evalseed":
            key = f"seed:{path.removeprefix('evals/seeds/')}"
        elif kind == "entity":
            for entity in data["entities"]:
                entity_key = f"entity:{path}#{entity['name']}"
                if entity_key in self.nodes:
                    self.error("name.duplicate", path, "entities/name", "duplicate entity name", entity_key)
                self.nodes[entity_key] = Node(entity_key, kind, domain, path, entity)
            return
        else:
            return
        if kind in ("metric", "method") and PurePosixPath(path).stem != data["name"]:
            self.error("name.filename", path, "name", "name must equal file stem", key)
        if key in self.nodes:
            self.error("name.duplicate", path, "name", "duplicate canonical ID", key)
            return
        self.nodes[key] = Node(key, kind, domain, path, data, body)

    def resolve(self, reference, domain, kind="metric"):
        if not isinstance(reference, str):
            return None
        if reference.startswith(("metric:", "method:", "entity:", "seed:")):
            return self.nodes.get(reference)
        if kind == "method" or reference.startswith("methods/"):
            key = "method:" + reference.removeprefix("methods/").removesuffix(".md")
        else:
            key = "metric:" + (reference if "." in reference else f"{domain}.{reference}")
        return self.nodes.get(key)

    def lookup(self, reference, domain, kind="metric"):
        """Question-only lookup, including ambiguous aliases. No fuzzy match."""
        node = self.resolve(reference, domain, kind)
        candidates = set(self.aliases.get((domain, text_key(reference)), set()))
        if node:
            candidates.add(node.id)
        return sorted(candidates)

    def dependency(self, node, reference, kind="metric", field="metrics"):
        target = self.resolve(reference, node.domain, kind)
        if target is None or target.kind != kind:
            self.readiness(node, "reference.missing", field,
                           f"unresolved {kind} reference {reference!r}", str(reference))
            return None
        else:
            node.dependencies.add(target.id)
        return target

    def target_file(self, node, reference):
        """Resolve an authored file/anchor, respecting root and owning domain."""
        path, _, anchor = reference.partition("#")
        if path.startswith("methods/") and not path.endswith(".md"):
            path += ".md"
        if not path:
            path = node.path
        elif not path.startswith(("domains/", "entities/", "methods/", "company/")):
            path = f"domains/{node.domain}/{path}"
        full = (self.root / path).resolve()
        if not full.is_relative_to(self.root):
            self.error("path.escape", node.path, "references", "reference escapes context root", reference)
            return None
        if not full.is_file():
            self.readiness(node, "reference.missing", "references", "target file does not exist", reference)
            return None
        path = full.relative_to(self.root).as_posix()
        content = full.read_text()
        if anchor:
            headings = {re.sub(r"[^\w -]", "", h.strip().lower()).replace(" ", "-")
                        for h in re.findall(r"^#+\s+(.+)$", content, re.M)}
            named_entities = {n.data["name"] for n in self.nodes.values()
                              if n.kind == "entity" and n.path == path}
            if not (re.search(r'\bid=["\']' + re.escape(anchor) + r'["\']', content)
                    or anchor in headings or anchor in named_entities):
                self.readiness(node, "reference.anchor", "references", "target anchor does not exist", reference)
                return None
        return path, anchor, content

    def _metric(self, node):
        data, expr = node.data, node.data.get("expression")
        if expr:
            try:
                measure = MeasureParser(expr["measure"]).parse()
                refs, columns = set(measure.references), set(measure.columns)
                for group in expr.get("entity_filters", []):
                    columns.add(group["entity"])
                    for condition in group["having"]:
                        having = MeasureParser(condition["measure"]).parse()
                        refs.update(having.references)
                        columns.update(having.columns)
                if any(v == "/" for _, v in measure.tokens) and "ratio" not in expr:
                    self.error("ratio.required", node.path, "expression/ratio", "division requires zero_denominator and reason")
                if (measure.has_aggregate or not measure.references) and not node.lineage:
                    self.error("lineage.required", node.path, "lineage", "column/row measures require own lineage models")
                if not measure.has_aggregate and measure.references and "lineage" not in data:
                    self.error("lineage.explicit", node.path, "lineage", "reference-only measure must declare lineage: inherit")
                if data.get("lineage") == "inherit" and measure.has_aggregate:
                    self.error("lineage.invalid_inherit", node.path, "lineage", "row/column aggregates cannot use inherit")
                for ref in sorted(refs):
                    target = self.dependency(node, ref, field="expression/measure")
                    if target and not target.defined:
                        self.readiness(node, "reference.undefined", "expression/measure", "referenced metric has no expression or deterministic form", target.id)
                    if target:
                        self.check_dimensions(node, node.dimensions, target, "dimensions.reference",
                            "expression/allowed_dimensions", "dimensions must be a subset of every referenced metric", structural=True)
                node._columns = columns
            except (ValueError, RecursionError) as exc:
                self.error("expression.invalid", node.path, "expression/measure", str(exc))
            self._constraints(node, expr.get("mandatory_filters", []))
        if data.get("deterministic_form"):
            ref = data["deterministic_form"]
            if ref.startswith("methods/"):
                self.dependency(node, ref, "method", "deterministic_form")
            else:
                target = self.target_file(node, ref)
                if target:
                    path, anchor, content = target
                    if not anchor.startswith("pattern-") or not path.endswith("/reference.md"):
                        self.error("pattern.target", node.path, "deterministic_form", "expected reference.md#pattern-<slug>")
                    try:
                        start, end = pattern_span(content, anchor)
                        section = content[start:end]
                    except ValueError:
                        self.readiness(node, "pattern.section", "deterministic_form", "pattern section could not be resolved")
                        return
                    if "Without this:" not in section:
                        self.readiness(node, "pattern.rationale", "deterministic_form", "pattern requires Without this:")
                    pattern_id = f"pattern:{path}#{anchor}"
                    if pattern_id not in self.nodes:
                        p = Node(pattern_id, "pattern", node.domain, path,
                                 {"status": pattern_status(section)}, section)
                        p.lineage = self._lineage(self.domains.get(node.domain, {}).get("lineage"))
                        self.nodes[pattern_id] = p
                    node.dependencies.add(pattern_id)

    @staticmethod
    def _lineage(value):
        if not isinstance(value, list):
            return set()
        return {(p["source"], m) for p in value for m in p.get("models", [])}

    def _constraints(self, node, filters):
        # Only prove direct conjunctive equality contradictions. OR stays intact.
        equalities = {}
        def walk(items):
            for item in items:
                if "all_of" in item:
                    yield from walk(item["all_of"])
                elif "field" in item:
                    yield item
        for item in walk(filters):
            if item["op"] in ("=", "=="):
                value = signature(item.get("value"))
                if item["field"] in equalities and equalities[item["field"]] != value:
                    self.error("filter.contradiction", node.path, "expression/mandatory_filters",
                               f"conflicting equality constraints on {item['field']}")
                equalities[item["field"]] = value

    def _family(self, node):
        family = node.data.get("family")
        if not family:
            return
        members = {node.id}
        for ref in family["siblings"]:
            target = self.resolve(ref, node.domain)
            if not target or target.id == node.id:
                self.error("family.target", node.path, "family/siblings", "missing or self sibling", ref)
                continue
            members.add(target.id)
        values = set()
        base = None
        for key in sorted(members):
            target = self.nodes[key]
            f = target.data.get("family", {})
            their_members = {target.id}
            their_members.update(n.id for r in f.get("siblings", [])
                                 if (n := self.resolve(r, target.domain)))
            if f.get("name") != family["name"] or f.get("discriminator") != family["discriminator"] or their_members != members:
                self.error("family.mutual", node.path, "family", "siblings must declare the same mutual family", key)
            expr = target.data.get("expression", {})
            filters = expr.get("mandatory_filters", [])
            discriminators = [x for x in filters if x.get("field") == family["discriminator"]]
            if len(discriminators) != 1:
                self.error("family.discriminator", target.path, "expression/mandatory_filters", "exactly one mandatory discriminator constraint is required")
            else:
                val = signature(discriminators[0])
                if val in values:
                    self.error("family.distinct", node.path, "family", "sibling discriminator constraints must differ", key)
                values.add(val)
            measure = re.sub(r"\s+", "", expr.get("measure", ""))
            rest = sorted(signature(x) for x in filters if x not in discriminators)
            current = (measure, rest, signature(expr.get("entity_filters", [])))
            if base is not None and base != current:
                self.error("family.measure", node.path, "family", "family members must share measure and nondiscriminator filters", key)
            base = current

    def _seed(self, node):
        data, ir = node.data, node.data.get("ir", {})
        if data["expected"].get("kind") == "semantic_entity":
            reference = data["expected"]["entity"]
            candidates = [n for n in self.nodes.values() if n.kind == "entity" and
                (reference in (n.id, n.id.removeprefix("entity:")) or
                 (n.domain in ("", node.domain) and text_key(reference) in
                  {text_key(v) for v in [n.data["name"], *n.data.get("aliases", [])]}))]
            if len(candidates) == 1:
                node.dependencies.add(candidates[0].id)
            else:
                self.readiness(node, "entity.unresolved", "expected/entity",
                               "entity expectation requires a unique governed entity reference", reference)
        if ir:
            kind = "method" if "method" in ir else "metric"
            target = self.dependency(node, ir[kind], kind, f"ir/{kind}")
            if target:
                if kind == "metric":
                    self.check_dimensions(node, ir.get("dimensions", []), target, "dimensions.seed",
                                          "ir/dimensions", "seed uses a dimension no longer allowed")
                if kind == "method":
                    declared = {p["name"]: p for p in target.data["parameters"]}
                    for p in ir.get("parameters", {}):
                        if p not in declared:
                            self.error("parameter.unknown", node.path, f"ir/parameters/{p}", "unknown method parameter")
                    composed = set()
                    for ref in ir["metrics"]:
                        metric = self.dependency(node, ref, field="ir/metrics")
                        if metric:
                            composed.add(metric.id)
                            if metric.id not in target.dependencies:
                                self.error("method.composition", node.path, "ir/metrics", "metric is not composed by the method", metric.id)
                    dims = set(ir.get("dimensions", []))
                    for key, value in ir["parameters"].items():
                        if declared.get(key, {}).get("dimension"):
                            if not isinstance(value, str):
                                self.error("parameter.dimension", node.path, f"ir/parameters/{key}", "dimension parameter must be a string")
                            elif not value.startswith("<"):
                                dims.add(value)
                    for metric_id in composed:
                        self.check_dimensions(node, dims, self.nodes[metric_id], "dimensions.seed",
                                              "ir/dimensions", "method dimensions must be allowed by each resolved metric")
        window = ir.get("time_window")
        tokens = self.config.get("time_tokens", {})
        if isinstance(window, str) and window not in tokens.get("calendar", []) + tokens.get("fiscal", []):
            self.error("time.undeclared", node.path, "ir/time_window", "time token is not declared in context.config.yaml", window)
        if isinstance(window, dict):
            if data["expected"]["kind"] != "value_at_snapshot":
                self.error("time.snapshot", node.path, "ir/time_window", "absolute windows require a snapshot seed")
            try:
                if date.fromisoformat(window["start"]) >= date.fromisoformat(window["end"]):
                    raise ValueError("window start must precede end")
            except ValueError as exc:
                self.error("time.bounds", node.path, "ir/time_window", str(exc))
        variants = data.get("variants", [])
        if len(variants) > self.config.get("variants", {}).get("max_per_seed", 20):
            self.error("variant.cap", node.path, "variants", "variants exceed configured maximum")
        seen = {text_key(data["question"])}
        for i, variant in enumerate(variants):
            key = text_key(variant["text"])
            if key in seen:
                self.error("variant.duplicate", node.path, f"variants/{i}/text", "duplicate normalized question/variant text")
            seen.add(key)
        value = data["expected"].get("value")
        if isinstance(value, list) and len(value) > 1 and not data["expected"].get("key_columns"):
            self.error("snapshot.keys", node.path, "expected/key_columns", "multiple snapshot rows require unique comparison keys")
        query = data.get("verified_query_file")
        if query:
            from .verified import contained, VerificationError
            try:
                for suffix in ("", ".age", ".sops"):
                    contained(self.root, query + suffix, "evals/verified")
            except VerificationError:
                self.error("path.escape", node.path, "verified_query_file", "query artifacts must remain in the ignored verification area without symlinks")

    def _cycles(self):
        done, active = set(), []
        def visit(key):
            if key in active:
                cycle = active[active.index(key):] + [key]
                node = self.nodes[key]
                self.error("graph.cycle", node.path, "dependencies", "cyclic references: " + " -> ".join(cycle))
                for member in cycle:
                    self.nodes[member].local_blockers.add("graph.cycle")
                return
            if key in done:
                return
            active.append(key)
            for dep in sorted(self.nodes[key].dependencies):
                if dep in self.nodes:
                    visit(dep)
            active.pop()
            done.add(key)
        try:
            for key in sorted(self.nodes):
                visit(key)
        except RecursionError:
            self.error("graph.depth", "context.config.yaml", "", "dependency graph exceeds supported nesting depth")

    def affected(self, targets):
        affected = set(targets)
        changed = True
        while changed:
            before = len(affected)
            affected.update(n.id for n in self.nodes.values() if n.dependencies & affected)
            changed = before != len(affected)
        return affected

    def definitions(self):
        """Format-neutral records; the harness never imports ACF node classes."""
        from .columns import column_evidence
        out = {}
        for node in self.metrics + self.methods:
            column_aliases, ambiguous_columns = column_evidence(self.manifests, node.lineage)
            out[node.id] = {
                "kind": node.kind, "domain": node.domain, "name": node.data["name"],
                "aliases": node.data.get("aliases", []), "alias_notes": node.data.get("alias_notes", []),
                "grain": node.data.get("grain", node.data.get("output", {}).get("grain", "")),
                "dimensions": sorted(node.dimensions), "parameters": node.data.get("parameters", []),
                "metrics": sorted(d for d in node.dependencies if d.startswith("metric:")),
                "defined": node.defined, "expressible": bool(node.data.get("expression")),
                "effective_status": node.effective_status, "approval_state": node.approval_state, "blockers": sorted(node.blocking_reasons),
                "lineage": sorted(node.lineage), "family": node.data.get("family"),
                "output": node.data.get("output", {}), "checks": node.data.get("checks", []),
                "decisions": node.data.get("decisions", []), "path": node.path,
                "time_tokens": sorted(token for group in self.config.get("time_tokens", {}).values()
                                      for token in group),
                "column_aliases": column_aliases, "ambiguous_columns": ambiguous_columns,
            }
        return out

    def seed_records(self):
        return [{**node.data, "status": node.effective_status, "id": node.id, "path": node.path,
                 "effective_status": node.effective_status, "approval_state": node.approval_state,
                 "blockers": sorted(node.blocking_reasons), "governance": self.governance} for node in self.seeds]

    def build(self):
        from .methods import check_method
        from .verified import contained, VerificationError
        try:
            contained(self.root, self.config.get("verified_sql", {}).get("decrypt_to", "evals/verified"), "evals/verified")
        except VerificationError:
            self.error("config.decrypt_path", "context.config.yaml", "verified_sql/decrypt_to", "decryption must stay under evals/verified without traversal or symlinks")
        tokens = self.config.get("time_tokens", {})
        all_tokens = tokens.get("calendar", []) + tokens.get("fiscal", [])
        if len(all_tokens) != len(set(all_tokens)):
            self.error("time.duplicate", "context.config.yaml", "time_tokens", "tokens must be unique across calendars")
        sources = self.config.get("lineage_sources", [])
        source_ids = [s["id"] for s in sources]
        if len(source_ids) != len(set(source_ids)):
            self.error("lineage.duplicate_source", "context.config.yaml", "lineage_sources", "source IDs must be unique")
        for node in list(self.nodes.values()):
            node.lineage = self._lineage(node.data.get("lineage"))
            if node.domain and node.kind != "domain" and node.domain not in self.domains:
                self.readiness(node, "domain.missing", "domain", "owning domain does not exist", node.domain)
            for source, model in node.lineage:
                if source not in source_ids:
                    self.error("lineage.source", node.path, "lineage", "unknown lineage source", source)
            if node.kind in ("metric", "method"):
                for alias in [node.data["name"], *node.data.get("aliases", [])]:
                    self.aliases.setdefault((node.domain, text_key(alias)), set()).add(node.id)
        for node in self.metrics:
            self._metric(node)
        for node in self.methods:
            check_method(self, node)
        for node in self.metrics:
            self._family(node)
            for decision in node.data.get("open_decisions", []):
                for ref in decision["blocks"]:
                    target = self.resolve(ref, node.domain)
                    if target:
                        target.local_blockers.add(f"open_decision:{node.id}#{decision['id']}")
                    else:
                        self.readiness(node, "decision.target", "open_decisions/blocks", "blocking target does not exist", ref)
        for node in self.seeds:
            self._seed(node)
        for (domain, alias), ids in sorted(self.aliases.items()):
            if len(ids) > 1:
                for key in sorted(ids):
                    if not self.nodes[key].data.get("alias_notes"):
                        self.error("alias.ambiguous", self.nodes[key].path, "alias_notes", f"alias {alias!r} collides within {domain}; every owner needs alias_notes")
        self._cycles()
        changed = True
        while changed:
            changed = False
            for node in self.nodes.values():
                old = set(node.lineage)
                for dep in node.dependencies:
                    if dep in self.nodes:
                        node.lineage |= self.nodes[dep].lineage
                changed |= node.lineage != old
        for node in self.methods:
            union = set().union(*(self.nodes[d].lineage for d in node.dependencies)) if node.dependencies else set()
            own = self._lineage(node.data.get("lineage"))
            if not own.issubset(union):
                self.error("lineage.method_subset", node.path, "lineage", "explicit method lineage must be a subset of composed lineage")
            node.lineage = union
        self._columns()
        self._dimensions()
        resolve_status(self.nodes)
        self._prose_warnings()

    def _columns(self):
        from .columns import column_evidence
        catalog = {}
        for source, manifest in self.manifests.items():
            for record in list(manifest.get("nodes", {}).values()) + list(manifest.get("sources", {}).values()):
                if record.get("resource_type") in ("model", "seed", "snapshot", "source"):
                    for name in {record.get("name"), record.get("unique_id")} - {None}:
                        catalog.setdefault((source, name), []).append(set(record.get("columns", {})))
        def check(node, fields, pointers):
            complete = all(source in self.manifests for source, _ in pointers)
            if not complete:
                self.warn("lineage.unchecked", node.path, "lineage", "column membership unchecked: source manifest unavailable")
                return
            known = {}
            for pointer in pointers:
                records = catalog.get(pointer, [])
                if len(records) != 1:
                    self.error("lineage.model", node.path, "lineage", "lineage model missing or ambiguous in manifest", "/".join(pointer))
                else:
                    known[pointer] = {c.lower() for c in records[0]}
            aliases, _ = column_evidence(self.manifests, pointers)
            for field in fields:
                normalized_field = aliases.get(field, field)
                qualifier, dot, column = normalized_field.rpartition(".")
                candidates = [cols for (_, model), cols in known.items()
                              if not dot or model == qualifier or model.split(".")[-1] == qualifier]
                if known and not any((column if dot else normalized_field).lower() in cols for cols in candidates):
                    self.error("lineage.column", node.path, "expression", f"column {field!r} absent from lineage models")
        for node in self.metrics:
            expr = node.data.get("expression", {})
            own = self._lineage(node.data.get("lineage"))
            check(node, getattr(node, "_columns", set()), own or node.lineage)
            fields = set(filter_fields(expr.get("mandatory_filters", [])))
            check(node, fields | node.dimensions, node.lineage)
            pending, seen = list(node.dependencies), set()
            while pending:
                dep = pending.pop()
                if dep in seen or dep not in self.nodes:
                    continue
                seen.add(dep)
                target = self.nodes[dep]
                check(node, fields, target.lineage)
                pending.extend(target.dependencies)

    def _prose_warnings(self):
        for domain in self.domains:
            ref = self.root / "domains" / domain / "reference.md"
            content = ref.read_text() if ref.is_file() else ""
            for node in self.metrics:
                if node.domain == domain and node.data.get("expression") and node.data["name"] not in content:
                    self.warn("prose.metric_missing", str(ref.relative_to(self.root)), "", f"reference.md does not name {node.data['name']}")
            reasons = []
            def collect(value):
                if isinstance(value, dict):
                    for key, child in value.items():
                        if key in ("reason", "without_this") and isinstance(child, str):
                            reasons.append(text_key(child))
                        collect(child)
                elif isinstance(value, list):
                    for child in value:
                        collect(child)
            for node in self.metrics + self.methods:
                if node.domain == domain:
                    collect(node.data)
            for line in content.splitlines():
                if "Without this:" in line and text_key(line.split("Without this:", 1)[1]) not in reasons:
                    self.warn("prose.rationale_unmapped", str(ref.relative_to(self.root)), "", "Without this rationale has no exact structured match; semantic agreement needs review")
        glossary = self.root / "company/terminology.md"
        if glossary.is_file():
            aliases = {key for _, key in self.aliases}
            aliases.update(text_key(a) for n in self.nodes.values() if n.kind == "entity"
                           for a in [n.data["name"], *n.data.get("aliases", [])])
            for heading in re.findall(r"^#{2,6}\s+(.+)$", glossary.read_text(), re.M):
                if text_key(heading) not in aliases:
                    self.warn("prose.glossary_alias", "company/terminology.md", "", f"heading {heading!r} has no matching alias")
