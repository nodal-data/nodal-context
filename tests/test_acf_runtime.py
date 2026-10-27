"""ACF 0.3 layout, fragment, graph, method, audit and seed contracts."""
from copy import deepcopy
from pathlib import Path
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_runtime import load_context
from acf_runtime.loader import read_yaml
from acf_fixtures import context, domain, metric, method, seed, write, METHOD_BODY


def run():
    def load(root):
        return load_context(root, schemas=ROOT / "schemas")
    def codes(registry):
        return {d.code for d in registry.diagnostics}
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        context(root)
        base = metric()
        metric_path = write(root, "domains/sales/metrics/orders.yaml", base)
        method_path = write(root, "methods/repeat.md", method(), METHOD_BODY)
        seed_path = write(root, "evals/seeds/orders.seed.yaml", seed())
        r = load(root)
        assert not r.errors, [str(e) for e in r.errors]
        assert r.resolve("orders", "sales").lineage == {("dbt", "orders")}
        assert r.resolve("repeat", "sales", "method").effective_status == "confirmed"
        assert r.seeds[0].data["confirmed_at"] == "2026-10-01"
        # Explicit discovery does not ingest nested repositories or caches.
        write(root, ".nodal/nested/domains/sales/metrics/oops.yaml", {"broken": True})
        assert not load(root).errors
        # Duplicate YAML keys are never silently overwritten.
        original = metric_path.read_text()
        metric_path.write_text(original + "name: duplicate\n")
        assert "parse.invalid" in codes(load(root))
        metric_path.write_text(original)
        for invalid_keys in ("1: invalid\n", "true: invalid\n", "2026-10-01: invalid\n",
                             "? [a, b]\n: invalid\n"):
            metric_path.write_text(original + invalid_keys)
            errors = load(root).errors
            assert any(d.code == "parse.invalid" and "mapping keys must be strings" in d.message for d in errors)
        metric_path.write_text(original)
        # No backward compatibility, including equal mixed-layout definitions.
        old = write(root, "domains/sales/metrics.yaml", {"metrics": [base]})
        assert "layout.legacy" in codes(load(root))
        old.unlink()
        for name in ("metrics.LookML", "metrics.lookml", "METRICS.LOOKML", "Metrics.LookMl"):
            old = root / "domains/sales" / name
            old.write_text("legacy metric artifact")
            assert "layout.legacy" in codes(load(root))
            assert sum("LookML conversion is not supported" in d.message for d in load(root).errors) == 1
            old.unlink()
        cfg = read_yaml(root / "context.config.yaml")
        cfg["version"] = 0.2
        write(root, "context.config.yaml", cfg)
        assert load(root).errors
        cfg["version"] = 0.3
        write(root, "context.config.yaml", cfg)
        # Confirmed audit is mandatory; a draft does not acquire guessed approval.
        bad = deepcopy(base)
        del bad["approver"]
        write(root, metric_path.relative_to(root), bad)
        assert "schema.invalid" in codes(load(root))
        bad["status"] = "draft"
        write(root, metric_path.relative_to(root), bad)
        r = load(root)
        assert not r.errors
        assert r.resolve("repeat", "sales", "method").effective_status == "draft"
        assert r.seeds[0].effective_status == "draft"
        assert "status: confirmed" in method_path.read_text()
        write(root, metric_path.relative_to(root), base)
        # Shared fragments expand conjunctively before every consumer sees metrics.
        shared = {"lineage": {"source": base["lineage"]},
                  "parameters": {"window": [{"name": "start", "note": "Inclusive"}]},
                  "filter_sets": {"window": {"filters": [{"field": "date", "op": ">=", "value": "<start>", "reason": "Aligned window"}]}}}
        write(root, "domains/sales/metrics/_shared.yaml", shared)
        fragmented = deepcopy(base)
        fragmented["lineage"] = {"shared": "source"}
        fragmented["parameters"] = [{"shared": "window"}]
        fragmented["expression"]["include_filters"] = ["window"]
        write(root, metric_path.relative_to(root), fragmented)
        r = load(root)
        expanded = r.resolve("orders", "sales").data
        assert len(expanded["expression"]["mandatory_filters"]) == 2
        assert expanded["parameters"][0]["name"] == "start"
        assert "fragment.low_use" in codes(r)
        fragmented["expression"]["include_filters"] = ["missing"]
        write(root, metric_path.relative_to(root), fragmented)
        broken = load(root)
        diagnostic = next(d for d in broken.errors if d.code == "fragment.invalid")
        assert diagnostic.field == "expression/include_filters/0"
        assert {"path": "domains/sales/metrics/orders.yaml", "field": "expression/include_filters/0"} in diagnostic.related
        assert {"path": "domains/sales/metrics/_shared.yaml", "field": "filter_sets/missing"} in diagnostic.related
        assert "_shared.yaml:filter_sets/missing" in str(diagnostic)
        output = subprocess.run([sys.executable, str(ROOT / ".ci/validate.py"), str(root),
                                 "--schemas", str(ROOT / "schemas"), "--json"], capture_output=True, text=True)
        assert output.returncode == 1, output.stderr
        emitted = next(d for d in json.loads(output.stdout)["diagnostics"] if d["code"] == "fragment.invalid")
        assert emitted["related"] == diagnostic.related
        # The reference/definition locations survive expansion into downstream
        # semantic checks too, not only failed fragment lookup.
        fragmented["expression"]["include_filters"] = ["window"]
        shared["lineage"]["source"][0]["source"] = "missing_source"
        write(root, "domains/sales/metrics/_shared.yaml", shared)
        write(root, metric_path.relative_to(root), fragmented)
        broken = load(root)
        diagnostic = next(d for d in broken.errors if d.code == "lineage.source" and d.path.endswith("orders.yaml"))
        assert {"path": "domains/sales/metrics/_shared.yaml", "field": "lineage/source"} in diagnostic.related
        assert {"path": "domains/sales/metrics/orders.yaml", "field": "lineage/shared"} in diagnostic.related
        assert "related" not in broken.resolve("orders", "sales").data
        shared["lineage"]["source"][0]["source"] = "dbt"
        write(root, "domains/sales/metrics/_shared.yaml", shared)
        write(root, metric_path.relative_to(root), base)
        # Cross-domain lineage and draft cascade follow references.
        domain(root, "finance")
        ratio = metric("share", lineage="inherit", expression={"measure": "metric(sales.orders) / metric(sales.orders)",
                       "allowed_dimensions": ["channel"], "ratio": {"zero_denominator": None, "reason": "Empty population has no rate"}})
        ratio_path = write(root, "domains/finance/metrics/share.yaml", ratio)
        r = load(root)
        assert not r.errors, [str(e) for e in r.errors]
        assert r.resolve("share", "finance").lineage == {("dbt", "orders")}
        assert "metric:finance.share" in r.affected({"metric:sales.orders"})
        ratio["expression"].pop("ratio")
        write(root, ratio_path.relative_to(root), ratio)
        assert "ratio.required" in codes(load(root))
        ratio["expression"]["ratio"] = {"zero_denominator": "null", "reason": "empty"}
        write(root, ratio_path.relative_to(root), ratio)
        assert "schema.invalid" in codes(load(root))
        ratio["expression"]["measure"] = "metric(finance.share)"
        ratio["expression"].pop("ratio")
        write(root, ratio_path.relative_to(root), ratio)
        assert "graph.cycle" in codes(load(root))
        ratio_path.unlink()
        # Blocking decisions affect dependents without rewriting authored status.
        blocked = deepcopy(base)
        blocked["open_decisions"] = [{"id": "refunds", "question": "Refund treatment?", "blocks": ["methods/repeat"]}]
        write(root, metric_path.relative_to(root), blocked)
        r = load(root)
        assert r.resolve("orders", "sales").effective_status == "confirmed"
        assert r.resolve("repeat", "sales", "method").effective_status == "draft"
        assert "status: confirmed" in method_path.read_text()
        write(root, metric_path.relative_to(root), base)
        # Draft notebook rationale is reviewable, but cannot be confirmed empty.
        draft = method()
        draft["decisions"][0]["without_this"] = ""
        draft["status"] = "draft"
        write(root, method_path.relative_to(root), draft, METHOD_BODY)
        assert not load(root).errors
        draft["status"] = "confirmed"
        write(root, method_path.relative_to(root), draft, METHOD_BODY)
        assert load(root).errors
        write(root, method_path.relative_to(root), method(), METHOD_BODY)
        # Duplicate normalized variants and undeclared tokens are blocking.
        variant = {"text": "ORDERS BY CHANNEL LAST MONTH?", "observed_at": "2026-10-20T10:00:00Z", "provenance": "observed"}
        write(root, seed_path.relative_to(root), seed(variants=[variant]))
        assert "variant.duplicate" in codes(load(root))
        bad_seed = seed(); bad_seed["ir"]["time_window"] = "unknown"
        write(root, seed_path.relative_to(root), bad_seed)
        assert "time.undeclared" in codes(load(root))
        write(root, seed_path.relative_to(root), seed())
        # Aliases require notes on every colliding owner; notes don't remove ambiguity.
        alias_metric = metric("another", aliases=["orders"])
        alias_path = write(root, "domains/sales/metrics/another.yaml", alias_metric)
        assert "alias.ambiguous" in codes(load(root))
        for value, path in ((base, metric_path), (alias_metric, alias_path)):
            value["alias_notes"] = ["Ask which order population."]
            write(root, path.relative_to(root), value)
        r = load(root)
        assert len(r.lookup("orders", "sales")) == 2
        assert "alias.ambiguous" not in codes(r)
        # Malformed source shapes fail with diagnostics, not tracebacks.
        for key, value in (("parameters", 3), ("lineage", [None]), ("expression", [])):
            bad = deepcopy(base); bad[key] = value
            write(root, metric_path.relative_to(root), bad)
            assert load(root).errors
    print("test_acf_runtime: OK")


if __name__ == "__main__":
    run()
