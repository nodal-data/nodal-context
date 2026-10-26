"""Static notebook drafting. This module never executes or imports notebook code.

Only identifiers and qualitative templates enter the draft. Source snippets,
stored outputs, connection strings and runtime literals are not copied.
"""
import ast
from datetime import date
import hashlib
import re

import yaml

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SLUG = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
SENSITIVE = re.compile(r"password|secret|token|credential|api_key|connection|dsn", re.I)


def content_hash(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _identifier(value):
    return isinstance(value, str) and bool(IDENTIFIER.fullmatch(value)) and not SENSITIVE.search(value)


def _call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _call_name(node.value) + "." + node.attr
    return ""


def _sql_filter(node, exp):
    """Narrow, typed filter extraction; unsupported SQL is never an exact match."""
    if isinstance(node, exp.Paren):
        return _sql_filter(node.this, exp)
    for cls, key in ((exp.And, "all_of"), (exp.Or, "any_of")):
        if isinstance(node, cls):
            return {key: [_sql_filter(node.this, exp), _sql_filter(node.expression, exp)]}
    ops = {exp.EQ: "=", exp.NEQ: "!=", exp.GT: ">", exp.GTE: ">=", exp.LT: "<", exp.LTE: "<="}
    if type(node) not in ops or not isinstance(node.this, exp.Column):
        raise ValueError("unsupported filter")
    value = node.expression
    if isinstance(value, exp.Boolean):
        literal = value.this
    elif isinstance(value, exp.Literal):
        literal = value.this if value.is_string else (float(value.this) if "." in value.this else int(value.this))
    else:
        raise ValueError("nonliteral filter")
    return {"field": node.this.name, "op": ops[type(node)], "value": literal}


def _filter_identity(filters):
    import json
    def canonical(node):
        if "all_of" in node or "any_of" in node:
            key = "all_of" if "all_of" in node else "any_of"
            return (key, tuple(sorted(canonical(n) for n in node[key])))
        return (node.get("field"), node.get("op"), json.dumps(node.get("value"), sort_keys=True))
    def conjunction(node):
        if "all_of" in node:
            return [n for c in node["all_of"] for n in conjunction(c)]
        return [canonical(node)]
    return sorted(n for f in filters for n in conjunction(f))


def draft_notebook(path, *, name, domain, registry, source_path=None, repo=None, ref=None, dialect=None):
    """Return method/frontmatter, body and a local review report; no writes."""
    try:
        import nbformat
        import sqlglot
        from sqlglot import exp
    except ImportError as exc:
        raise ValueError("notebook import requires optional nbformat and sqlglot dependencies") from exc
    if not SLUG.fullmatch(name) or domain not in registry.domains:
        raise ValueError("choose a valid method slug and an existing domain")
    raw = path.read_bytes()
    book = nbformat.reads(raw.decode("utf-8"), as_version=4)
    decisions, params, columns, checks, proposed = [], {}, set(), [], set()
    report = {"source_hash": content_hash(raw), "cells": [], "metric_candidates": [], "review_items": []}

    def decision(rule, cell):
        key = f"cell_{cell}_{len(decisions) + 1}"
        decisions.append({"id": key, "rule": rule, "without_this": ""})

    def parameter(key, cell):
        if _identifier(key):
            params.setdefault(key, {"name": key, "note": f"Review the runtime binding identified in cell {cell}."})

    def sql(source, cell, classes):
        try:
            statements = sqlglot.parse(source, read=dialect)
        except (sqlglot.errors.SqlglotError, ValueError):
            report["review_items"].append({"cell": cell, "reason": "SQL could not be parsed; inspect source"})
            return
        for statement in statements:
            if not isinstance(statement, exp.Select):
                report["review_items"].append({"cell": cell, "reason": "non-SELECT SQL requires review; not executed"})
                continue
            classes.add("load")
            aggregates = list(statement.find_all(exp.AggFunc))
            if aggregates or statement.args.get("group") or statement.args.get("where"):
                classes.add("transform")
            for projection in statement.expressions:
                if _identifier(projection.alias_or_name):
                    columns.add(projection.alias_or_name)
            tables = {t.name for t in statement.find_all(exp.Table)}
            fields = sorted({c.name for c in statement.find_all(exp.Column) if _identifier(c.name)})
            for predicate in statement.find_all(exp.Predicate):
                column, literal = predicate.this, predicate.expression
                if isinstance(column, exp.Column) and isinstance(literal, exp.Literal):
                    if literal.is_string and re.fullmatch(r"\d{4}-\d{2}-\d{2}", literal.this):
                        parameter("date_" + column.name, cell)
                    elif not literal.is_string and literal.this not in ("0", "1"):
                        parameter("threshold_" + column.name, cell)
            if statement.args.get("where"):
                decision("Apply the reviewed eligibility constraints on " + (", ".join(fields) or "source rows") + ".", cell)
            if statement.args.get("group"):
                decision("Use the reviewed grouping grain before calculating the reported measures.", cell)
            if statement.args.get("joins"):
                decision("Review join cardinality and identity so a source subject contributes the intended number of times.", cell)
            filters, simple = [], not any(statement.find_all(exp.Subquery, exp.Join, exp.Window))
            # CTEs, HAVING and DISTINCT can change populations; never propose an exact match.
            simple = simple and not any(statement.args.get(k) for k in ("with_", "having", "distinct", "limit", "offset"))
            try:
                if statement.args.get("where"):
                    filters = [_sql_filter(statement.args["where"].this, exp)]
            except (ValueError, TypeError):
                simple = False
            for aggregation in aggregates:
                decision("Compute the reviewed aggregation using the correct subject identity and population.", cell)
                for metric in registry.metrics:
                    if metric.domain != domain:
                        continue
                    definition = metric.data.get("expression", {})
                    try:
                        measure = sqlglot.parse_one(definition.get("measure", ""), read=dialect)
                    except (sqlglot.errors.SqlglotError, ValueError):
                        continue
                    if not measure or measure.sql(normalize=True) != aggregation.sql(normalize=True):
                        continue
                    models = {model.split(".")[-1] for _, model in metric.lineage}
                    exact = (simple and len(tables) == 1 and tables == models and
                             not definition.get("entity_filters") and
                             _filter_identity(filters) == _filter_identity(definition.get("mandatory_filters", [])))
                    candidate = {"cell": cell, "metric": metric.id, "match": "exact_candidate" if exact else "possible_drift",
                                 "requires_review": True}
                    if candidate not in report["metric_candidates"]:
                        report["metric_candidates"].append(candidate)
                    if exact:
                        proposed.add(metric.data["name"])

    for number, cell in enumerate(book.cells, 1):
        source, classes = cell.source, set()
        if cell.cell_type == "markdown":
            # Do not ingest narrative statistics or credentials. Keep an actionable source pointer.
            report["cells"].append({"cell": number, "classes": ["narrative"],
                                    "review": "Review narrative for qualitative decisions; text was not copied."})
            continue
        if cell.cell_type != "code":
            continue
        language = book.metadata.get("language_info", {}).get("name", "python")
        if source.lstrip().startswith("%%sql"):
            sql(source.split("\n", 1)[-1], number, classes)
        elif language == "sql":
            sql(source, number, classes)
        else:
            try:
                tree = ast.parse(source)
            except SyntaxError:
                report["review_items"].append({"cell": number, "reason": "dynamic syntax or notebook magic requires review"})
                tree = None
            if tree:
                tagged_parameters = "parameters" in cell.metadata.get("tags", [])
                literals = {}
                for statement in tree.body:
                    if isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
                        for target in statement.targets:
                            if isinstance(target, ast.Name):
                                literals[target.id] = statement.value.value
                if tree.body and isinstance(tree.body[-1], ast.Expr) and isinstance(tree.body[-1].value, (ast.Name, ast.Subscript)):
                    classes.add("output")
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Assign, ast.AnnAssign)):
                        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                        for target in targets:
                            if isinstance(target, ast.Name) and (tagged_parameters or re.search(
                                    r"date|window|threshold|cutoff|period|start|end|cohort|seed", target.id, re.I)):
                                parameter(target.id, number)
                    if isinstance(node, ast.Call):
                        call = _call_name(node.func).split(".")[-1]
                        if call.startswith("read_") or call in ("execute", "sql", "query", "load"):
                            classes.add("load")
                        if call in ("merge", "join", "groupby", "agg", "aggregate", "drop_duplicates", "dropna", "fillna", "filter"):
                            classes.add("transform")
                            decision(f"Review the {call} operation's population, identity and missing-value behavior.", number)
                        if call in ("display", "print", "plot", "show", "to_csv", "to_json", "to_parquet"):
                            classes.add("output")
                        if call in ("read_sql", "read_sql_query", "execute", "sql", "query"):
                            sql_literals = [a.value if isinstance(a, ast.Constant) else literals.get(a.id)
                                            for a in node.args if isinstance(a, (ast.Constant, ast.Name))]
                            sql_literals = [v for v in sql_literals if isinstance(v, str) and re.match(r"\s*(SELECT|WITH)\b", v, re.I)]
                            for value in sql_literals:
                                if re.match(r"\s*(SELECT|WITH)\b", value, re.I):
                                    sql(value, number, classes)
                            if not sql_literals:
                                report["review_items"].append({"cell": number, "reason": "dynamic SQL requires source review"})
                    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                        classes.add("transform")
                        decision("Review numerator and denominator populations and the empty-denominator policy.", number)
                    if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
                        classes.add("transform")
                        if isinstance(node.slice, ast.Constant) and _identifier(node.slice.value):
                            columns.add(node.slice.value)
                    if isinstance(node, ast.Assert):
                        # Only identifier-to-identifier relations enter qualitative checks.
                        test = node.test
                        if (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.left, ast.Name)
                                and isinstance(test.comparators[0], ast.Name)):
                            ops = {ast.LtE: "<=", ast.GtE: ">=", ast.Lt: "<", ast.Gt: ">", ast.Eq: "="}
                            left, right, op = test.left.id, test.comparators[0].id, ops.get(type(test.ops[0]))
                            if op and _identifier(left) and _identifier(right):
                                checks.append(f"{left} {op} {right} for every row")
                        report["review_items"].append({"cell": number, "reason": "Review assertion scope and whether it is a business invariant"})
                    if isinstance(node, ast.Dict):
                        columns.update(k.value for k in node.keys if isinstance(k, ast.Constant) and _identifier(k.value))
                    if isinstance(node, (ast.JoinedStr, ast.Lambda)):
                        report["review_items"].append({"cell": number, "reason": "dynamic expression requires review"})
        report["cells"].append({"cell": number, "classes": sorted(classes) or ["unclassified"]})
    if not decisions:
        decision("Review the source analysis to establish its population, identity and intended output.", 0)
    # Parameter declarations do not by themselves count as method usage.
    if params:
        decision("Bind the reviewed runtime inputs " + ", ".join("<" + p + ">" for p in params) + ".", 0)
    provenance = {"kind": "notebook", "path": source_path or path.name,
                  "ref": ref or report["source_hash"], "extracted_at": date.today().isoformat(),
                  "extracted_by": "context-interview (Stage 6, static notebook import)"}
    if repo:
        provenance["repo"] = repo
    method = {"name": name, "kind": "method", "domain": domain, "aliases": [],
              "description": "Draft analysis method; review source decisions with the analyst.",
              "metrics": sorted(proposed), "lineage": "inherit", "parameters": list(params.values()),
              "decisions": decisions, "output": {"grain": "Review with analyst", "columns": sorted(columns),
              "must_state": ["Reviewed parameter bindings and population"]}, "checks": list(dict.fromkeys(checks)),
              "provenance": provenance}
    body = "# " + name.replace("-", " ").capitalize() + "\n\n## When to use\n\nReview the intended business question with the analyst.\n\n## Procedure\n\n"
    body += "\n".join(f"{i}. {d['rule']} (`{d['id']}`)." for i, d in enumerate(decisions, 1)) + "\n"
    report["review_items"].append({"reason": "Explain every without_this; confirm metric candidates, grain, parameters, outputs and checks before approval"})
    return method, body, report


def render_method(data, body):
    return "---\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True) + "---\n\n" + body
