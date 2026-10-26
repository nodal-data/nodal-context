"""Format-neutral structural question matching. No ACF, model or warehouse I/O.

Definitions are dictionaries keyed by canonical ID, supplied by an adapter.
Required entries: kind, domain, name; optional fields are documented in INTERFACE.
"""
from copy import deepcopy
from dataclasses import dataclass, field
import json
import unicodedata


def text_key(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def stable(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def normalize_filter(value):
    if not isinstance(value, dict):
        raise ValueError("filter must be an object")
    if "field" in value:
        if "op" not in value or set(value) - {"field", "op", "value", "reason"}:
            raise ValueError("invalid filter fields")
        result = {"field": value["field"], "op": value["op"]}
        if "value" in value:
            result["value"] = deepcopy(value["value"])
        return result
    groups = set(value) & {"any_of", "all_of"}
    if len(groups) != 1 or set(value) - groups - {"reason"}:
        raise ValueError("filter requires exactly one any_of/all_of group")
    key = next(iter(groups))
    children = value[key]
    if not isinstance(children, list) or not children:
        raise ValueError("filter group must be a nonempty list")
    unique = {stable(child): child for child in map(normalize_filter, children)}
    return {key: [unique[k] for k in sorted(unique)]}


def resolve(reference, domain, kind, definitions, aliases=True):
    if not isinstance(reference, str):
        return []
    if reference.startswith(("metric:", "method:")):
        return [reference] if reference in definitions and definitions[reference]["kind"] == kind else []
    if kind == "method":
        canonical = "method:" + reference.removeprefix("methods/").removesuffix(".md")
    else:
        canonical = "metric:" + (reference if "." in reference else domain + "." + reference)
    direct = [canonical] if canonical in definitions else []
    # Explicit qualification expresses an analyst's selection; aliases never redirect it.
    if not aliases or "." in reference or reference.startswith("methods/"):
        return direct
    candidates = set(direct)
    for key, item in definitions.items():
        if item.get("domain") == domain and text_key(reference) in {
                text_key(a) for a in [item["name"], *item.get("aliases", [])]}:
            candidates.add(key)
    return sorted(candidates)


@dataclass
class Normalized:
    ir: dict = field(default_factory=dict)
    identity: dict = field(default_factory=dict)
    target: str | None = None
    state: str = "unresolved"
    candidates: list = field(default_factory=list)
    blockers: list = field(default_factory=list)
    unsupported: list = field(default_factory=list)


def normalize(ir, domain, definitions, *, question=True):
    result = Normalized()
    if not isinstance(ir, dict) or ("metric" in ir) == ("method" in ir):
        result.unsupported.append("exactly one metric/method is required")
        return result
    kind = "method" if "method" in ir else "metric"
    allowed = ({"method", "metrics", "parameters", "dimensions", "time_window"} if kind == "method"
               else {"metric", "dimensions", "filters", "grain", "time_window"})
    unknown = set(ir) - allowed
    if unknown:
        result.unsupported.extend(sorted(unknown))
        return result
    candidates = resolve(ir[kind], domain, kind, definitions, aliases=question)
    result.candidates = candidates
    if len(candidates) != 1:
        result.state = "ambiguous" if candidates else "unresolved"
        return result
    key = candidates[0]
    target = definitions[key]
    if target.get("kind") != kind or not target.get("defined", False):
        return result
    result.target = key
    result.ir = deepcopy(ir)
    result.ir[kind] = key
    # An adapter may declare the allowed vocabulary. Missing capability is
    # different from an explicitly empty vocabulary; non-ACF adapters need not
    # adopt ACF config to participate in matching.
    window = ir.get("time_window")
    if isinstance(window, str) and "time_tokens" in target and window not in target["time_tokens"]:
        result.unsupported.append("unknown_time_token")
        return result
    result.blockers = list(target.get("blockers", []))
    if target.get("effective_status", "draft") != "confirmed":
        result.blockers.append("definition_not_confirmed")
    dims = ir.get("dimensions", [])
    if not isinstance(dims, list) or not all(isinstance(d, str) for d in dims):
        result.unsupported.append("dimensions must be a string list")
        return result
    # Adapters supply only column aliases whose qualification they can prove.
    column_map = target.get("column_aliases", {})
    ambiguous_columns = set(target.get("ambiguous_columns", []))
    if kind == "method" and isinstance(ir.get("metrics"), list):
        selected = set()
        for ref in ir["metrics"]:
            matches = resolve(ref, domain, "metric", definitions, aliases=False)
            if len(matches) == 1 and matches[0] in target.get("metrics", []):
                selected.add(matches[0])
        # An alternative branch that this question did not select must not make
        # the single selected metric's proven columns ambiguous. Composition
        # validation below still rejects invalid/undeclared metric selections.
        if len(selected) == 1:
            scoped = definitions[next(iter(selected))]
            column_map = scoped.get("column_aliases", {})
            ambiguous_columns = set(scoped.get("ambiguous_columns", []))
    used_columns = set(dims)
    dimensions = sorted({column_map.get(d, d) for d in dims})
    result.ir["dimensions"] = dimensions
    identity = {kind: key, "dimensions": dimensions}
    if kind == "metric":
        allowed_dimensions = {column_map.get(d, d) for d in target.get("dimensions", [])}
        if not set(dimensions).issubset(allowed_dimensions):
            result.blockers.append("dimension_not_allowed")
        try:
            filters = ir.get("filters", [])
            if not isinstance(filters, list):
                raise ValueError("filters must be a list")
            filters = [normalize_filter(f) for f in filters]
            for item in filters:
                def qualify(f):
                    if "field" in f:
                        used_columns.add(f["field"])
                        f["field"] = column_map.get(f["field"], f["field"])
                    else:
                        for children in f.values():
                            for child in children:
                                qualify(child)
                qualify(item)
            filters = [normalize_filter(f) for f in filters]
            filters = sorted({stable(f): f for f in filters}.values(), key=stable)
        except (ValueError, TypeError) as exc:
            result.unsupported.append(str(exc))
            return result
        grain = ir.get("grain", target.get("grain", ""))
        identity.update(filters=filters, grain=grain)
        result.ir.update(filters=filters, grain=grain)
    else:
        params, metrics = ir.get("parameters"), ir.get("metrics")
        if not isinstance(params, dict) or not isinstance(metrics, list) or not metrics:
            result.unsupported.append("method IR requires parameters and nonempty resolved metrics")
            return result
        declared = {p["name"]: p for p in target.get("parameters", [])}
        unknown = set(params) - set(declared)
        if unknown:
            result.unsupported.extend(f"parameter:{p}" for p in sorted(unknown))
            return result
        bound = {p: deepcopy(d["default"]) for p, d in declared.items() if "default" in d}
        bound.update(params)
        resolved = set()
        for ref in metrics:
            matches = resolve(ref, domain, "metric", definitions, aliases=False)
            if len(matches) != 1 or matches[0] not in target.get("metrics", []):
                result.unsupported.append(f"metric:{ref}")
                return result
            resolved.add(matches[0])
        checked_dims = set(dimensions)
        for p, v in bound.items():
            if declared[p].get("dimension"):
                if not isinstance(v, str):
                    result.unsupported.append(f"dimension_parameter:{p}")
                    return result
                if not v.startswith("<"):
                    used_columns.add(v)
                    checked_dims.add(column_map.get(v, v))
        for metric in resolved:
            definition = definitions[metric]
            aliases = definition.get("column_aliases", {})
            allowed_dimensions = {aliases.get(d, d) for d in definition.get("dimensions", [])}
            if not checked_dims.issubset(allowed_dimensions):
                result.blockers.append(f"dimension_not_allowed:{metric}")
            if definition.get("effective_status", "draft") != "confirmed":
                result.blockers.append(f"dependency_not_confirmed:{metric}")
        identity.update(metrics=sorted(resolved), parameters=sorted(bound))
        result.ir.update(metrics=sorted(resolved), parameters=bound)
    if used_columns & ambiguous_columns:
        result.unsupported.extend("ambiguous_column:" + name for name in sorted(used_columns & ambiguous_columns))
        return result
    result.identity = identity
    result.state = "resolved"
    return result


def relation(question, seed):
    if question.state != "resolved":
        return question.state
    if seed.state != "resolved":
        return "unresolved"
    if question.target != seed.target:
        return "related_only"
    return "equivalent" if question.identity == seed.identity else "same_metric_new_slice"


def match_question(ir, domain, definitions, seeds, *, candidates=None, exclude=()):
    """Match a question to seeds; expected outputs never influence identity.

    Seeds: iterable of dictionaries with id/domain/ir/expected/effective_status.
    exclude supports leave-one-out evaluation (also excludes that seed's variants).
    """
    if isinstance(ir, dict) and "parts" in ir:
        return {"relation": "decomposes", "parts": [
            match_question(part, domain, definitions, seeds, exclude=exclude) for part in ir["parts"]]}
    if candidates:
        viable = set()
        for ref in candidates:
            for kind in ("metric", "method"):
                viable.update(resolve(ref, domain, kind, definitions))
        if len(viable) > 1:
            return {"relation": "ambiguous", "candidates": sorted(viable), "seeds": [], "blockers": ["analyst_selection_required"]}
    query = normalize(ir, domain, definitions)
    result = {"relation": query.state, "target": query.target, "ir": query.ir,
              "candidates": query.candidates, "seeds": [], "blockers": query.blockers,
              "unsupported": query.unsupported}
    if query.state != "resolved":
        return result
    related = []
    same_target = False
    for seed in seeds:
        if seed.get("id") in exclude or seed.get("domain") != domain:
            continue
        normalized = normalize(seed.get("ir"), seed["domain"], definitions, question=False)
        same_target |= normalized.state == "resolved" and normalized.target == query.target
        rel = relation(query, normalized)
        if rel == "equivalent":
            result["seeds"].append(seed.get("id"))
            related.append(seed)
    result["relation"] = ("equivalent" if related else
                          "same_metric_new_slice" if same_target else
                          "related_only")
    if related:
        expectations = {stable(s.get("expected", {})) for s in related
                        if s.get("expected", {}).get("kind") != "value_at_snapshot"}
        # Snapshot numbers only conflict for the identical pinned date and window.
        snapshots = {}
        for seed in related:
            expected = seed.get("expected", {})
            if expected.get("kind") == "value_at_snapshot":
                scope = stable([expected.get("as_of"), seed.get("ir", {}).get("time_window"),
                                seed.get("ir", {}).get("parameters")])
                snapshots.setdefault(scope, set()).add(stable(expected))
        if len(expectations) > 1 or any(len(v) > 1 for v in snapshots.values()):
            result["blockers"].append("ground_truth_conflict")
        if all(s.get("effective_status", s.get("status", "draft")) != "confirmed" for s in related):
            result["blockers"].append("matched_seeds_not_confirmed")
        if any(s.get("expected", {}).get("kind") == "negative" for s in related):
            result["blockers"].append("negative_seed_requires_escalation")
    return result
