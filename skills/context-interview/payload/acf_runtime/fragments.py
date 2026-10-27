"""Expand explicit domain-local fragments without overriding authored filters."""
from copy import deepcopy
from pathlib import PurePosixPath


class FragmentError(ValueError):
    def __init__(self, message, reference_field):
        super().__init__(message)
        self.reference_field = reference_field


def expand_metric(metric, shared, usage=None, path="", origins=None):
    result = deepcopy(metric)
    usage = usage if usage is not None else {}

    def get(namespace, name, reference_field, expanded_field):
        if origins is not None and isinstance(name, str):
            origins.append({"reference_field": reference_field, "expanded_field": expanded_field,
                            "path": str(PurePosixPath(path).parent / "_shared.yaml"),
                            "field": f"{namespace}/{name}"})
        if not isinstance(name, str) or name not in shared.get(namespace, {}):
            raise FragmentError(f"missing {namespace} fragment {name!r} in _shared.yaml", reference_field)
        usage.setdefault((str(PurePosixPath(path).parent), namespace, name), set()).add(path)
        value = deepcopy(shared[namespace][name])
        def contains_ref(obj):
            if isinstance(obj, dict):
                return "shared" in obj or "include_filters" in obj or any(contains_ref(v) for v in obj.values())
            return isinstance(obj, list) and any(contains_ref(v) for v in obj)
        if contains_ref(value):
            raise FragmentError(f"nested shared references are unsupported: {namespace}/{name}", reference_field)
        return value

    lineage = result.get("lineage")
    if isinstance(lineage, dict):
        if set(lineage) != {"shared"}:
            raise ValueError("lineage fragment reference must contain only shared")
        result["lineage"] = get("lineage", lineage["shared"], "lineage/shared", "lineage")
    params = []
    for index, param in enumerate(result.get("parameters", [])):
        if isinstance(param, dict) and "shared" in param:
            if set(param) != {"shared"}:
                raise ValueError("parameter fragment reference must contain only shared")
            params.extend(get("parameters", param["shared"], f"parameters/{index}/shared", "parameters"))
        else:
            params.append(param)
    if "parameters" in result:
        result["parameters"] = params
    names = [p.get("name") for p in params if isinstance(p, dict)]
    if len(names) != len(set(names)):
        raise ValueError("duplicate parameter names after fragment expansion")
    expr = result.get("expression")
    if isinstance(expr, dict):
        includes = expr.pop("include_filters", [])
        if not isinstance(includes, list):
            raise ValueError("include_filters must be a list")
        filters = expr.get("mandatory_filters", [])
        if not isinstance(filters, list):
            raise ValueError("mandatory_filters must be a list")
        filters = deepcopy(filters)
        for index, name in enumerate(includes):
            filters.extend(get("filter_sets", name, f"expression/include_filters/{index}",
                               "expression/mandatory_filters")["filters"])
        if includes or "mandatory_filters" in expr:
            expr["mandatory_filters"] = filters
    return result
