"""Object impact, status-only preview/apply, pattern boundaries and crash resume."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_fixtures import context, metric, method, seed, write, METHOD_BODY, APPROVAL
from acf_runtime.loader import load_context, read_yaml
from acf_runtime.impact import lineage_impact, cascade
from acf_runtime import drift
from acf_runtime.markdown import draft_pattern, pattern_span, pattern_status


def setup(root):
    context(root)
    write(root, "domains/sales/metrics/orders.yaml", metric())
    path = root / "domains/sales/metrics/orders.yaml"
    path.write_text("# Preserve the analyst's explanation\n" + path.read_text().replace(
                    "status: confirmed", "status: confirmed  # reviewed in interview"))
    write(root, "methods/repeat.md", method(), METHOD_BODY)
    write(root, "evals/seeds/orders.seed.yaml", seed())
    write(root, "evals/seeds/snapshot.seed.yaml", seed(expected={"kind": "value_at_snapshot",
          "value": 13, "as_of": "2026-10-20"}))
    negative = seed(expected={"kind": "negative", "reason": "lack_data"})
    negative.pop("ir")
    write(root, "evals/seeds/unavailable.seed.yaml", negative)
    write(root, "entities/customer.yaml", {"entities": [{"name": "customer", "description": "Canonical customer",
        "status": "confirmed", "lineage": [{"source": "dbt", "models": ["orders"]}]},
        {"name": "unrelated", "description": "Separate entity", "status": "confirmed",
         "lineage": [{"source": "dbt", "models": ["elsewhere"]}]}]})
    entity_seed = seed(expected={"kind": "semantic_entity", "entity": "customer"})
    entity_seed.pop("ir")
    write(root, "evals/seeds/customer.seed.yaml", entity_seed)
    base = root / ".ci/lineage-baseline.json"; base.parent.mkdir()
    base.write_text('{"version":1,"sources":{}}\n')


def reject(call, text):
    try:
        call()
    except ValueError as exc:
        assert text in str(exc), str(exc)
    else:
        raise AssertionError("expected rejection: " + text)


def apply(root, preview):
    return drift.apply(root, preview["plan"], preview["sha256"])


def run():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); setup(root)
        registry = load_context(root)
        assert not registry.errors, list(map(str, registry.errors))
        impact = lineage_impact(registry, {("dbt", "orders")})
        ids = {i["id"] for i in impact["objects"]}
        assert "seed:customer.seed.yaml" in ids and "seed:unavailable.seed.yaml" in ids
        assert "entity:entities/customer.yaml#unrelated" not in ids
        assert impact["snapshot_batch"] == ["seed:snapshot.seed.yaml"]
        assert next(i for i in impact["objects"] if i["id"] == "seed:customer.seed.yaml")["dependency_path"] == [
            "entity:entities/customer.yaml#customer", "seed:customer.seed.yaml"]
        before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
        preview = drift.prepare(root, impact, source_changes={"dbt": {"orders": "changed"}})
        assert preview["status"] == "prepared_not_applied" and preview["files"]
        assert all(p.read_bytes() == raw for p, raw in before.items())
        assert "status: draft" in (root / preview["patch"]).read_text()
        assert (root / preview["plan"]).stat().st_mode & 0o777 == 0o600
        apply(root, preview)
        after = load_context(root)
        assert not after.errors, list(map(str, after.errors))
        for identifier in ids:
            assert after.nodes[identifier].data["status"] == "draft", identifier
        assert after.nodes["entity:entities/customer.yaml#unrelated"].data["status"] == "confirmed"
        assert (root / "domains/sales/metrics/orders.yaml").read_text().startswith("# Preserve the analyst's explanation")
        assert "# reviewed in interview" in (root / "domains/sales/metrics/orders.yaml").read_text()
        assert after.nodes["method:repeat"].body == registry.nodes["method:repeat"].body
        assert after.nodes["metric:sales.orders"].data["approver"] == APPROVAL["approver"]
        assert after.nodes["metric:sales.orders"].data["confirmed_at"] == APPROVAL["confirmed_at"]
        assert (root / ".ci/lineage-baseline.json").read_bytes() == before[root / ".ci/lineage-baseline.json"]
        assert apply(root, preview)["resumed"]
        # Merely re-confirming the metric cannot re-confirm its seeds/methods.
        write(root, "domains/sales/metrics/orders.yaml", metric())
        again = load_context(root)
        assert again.nodes["seed:orders.seed.yaml"].data["status"] == "draft"
        assert again.nodes["method:repeat"].data["status"] == "draft"
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); setup(root)
        impact = lineage_impact(load_context(root), {("dbt", "orders")})
        preview = drift.prepare(root, impact)
        method_path = root / "methods/repeat.md"
        original = method_path.read_bytes(); method_path.write_bytes(original + b"\nNew human note.\n")
        reject(lambda: apply(root, preview), "context changed")
        assert read_yaml(root / "domains/sales/metrics/orders.yaml")["status"] == "confirmed"
        method_path.write_bytes(original)
        baseline_path = root / ".ci/lineage-baseline.json"
        baseline_before = baseline_path.read_bytes()
        baseline_path.write_bytes(baseline_before + b"\n")
        reject(lambda: apply(root, preview), "baseline changed")
        baseline_path.write_bytes(baseline_before)
        real_write = drift.atomic_private
        def interrupted(path, raw, **kwargs):
            if path.name == "orders.seed.yaml":
                raise OSError("synthetic crash between status writes")
            return real_write(path, raw, **kwargs)
        with patch.object(drift, "atomic_private", side_effect=interrupted):
            try:
                apply(root, preview)
            except OSError:
                pass
            else:
                raise AssertionError("interruption injection did not run")
        assert read_yaml(root / "domains/sales/metrics/orders.yaml")["status"] == "draft"
        apply(root, preview)
        assert read_yaml(root / "evals/seeds/orders.seed.yaml")["status"] == "draft"
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); setup(root)
        preview = drift.prepare(root, lineage_impact(load_context(root), {("dbt", "orders")}))
        path = root / preview["plan"]; plan = json.loads(path.read_text())
        edit = next(e for e in plan["edits"] if e["path"] == "domains/sales/metrics/orders.yaml")
        edit["after"] = edit["after"].replace("COUNT(*)", "SUM(revenue)")
        edit["after_sha256"] = drift.sha(edit["after"].encode())
        path.write_bytes(drift.encoded(plan))
        reject(lambda: drift.apply(root, preview["plan"], drift.sha(path.read_bytes())), "other than")
        assert "COUNT(*)" in (root / edit["path"]).read_text()
    # Both explicit anchors and heading anchors isolate the exact query pattern.
    for explicit in (False, True):
        text = ("# Reference\n\n" + ('<a id="pattern-first"></a>\n### First\n' if explicit else "### Pattern First\n")
                + "Without this: first rationale\n```sql\nSELECT count(*) FROM orders\n```\n\n"
                + ('<a id="pattern-second"></a>\n### Second\n' if explicit else "### Pattern Second\n")
                + "Without this: second rationale\n```sql\nSELECT distinct id FROM orders\n```\n")
        start, end = pattern_span(text, "pattern-first")
        assert "second rationale" not in text[start:end]
        assert draft_pattern(text, "pattern-first") == text
        legacy_text = text[:start] + text[start:end].replace(
            "Without this:", "<!-- acf: status: confirmed -->\nWithout this:", 1) + text[end:]
        changed = draft_pattern(legacy_text, "pattern-first")
        assert changed.count("status: draft") == 1
        a, b = pattern_span(changed, "pattern-first"); assert pattern_status(changed[a:b]) == "draft"
        a, b = pattern_span(changed, "pattern-second"); assert pattern_status(changed[a:b]) == "confirmed"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); context(root)
            (root / "domains/sales/reference.md").write_text(text)
            for name in ("first", "second"):
                value = metric(name); value.pop("expression")
                value["deterministic_form"] = "reference.md#pattern-" + name
                value["expression_blocked_by"] = "Requires a reviewed multi-step query pattern."
                write(root, f"domains/sales/metrics/{name}.yaml", value)
            registry = load_context(root)
            assert not registry.errors, list(map(str, registry.errors))
            pattern = "pattern:domains/sales/reference.md#pattern-first"
            assert "status" not in registry.nodes[pattern].data
            # A legacy metric can still be demoted, but its unmarked reference
            # must not acquire an authored approval-status comment.
            edits = drift.status_edits(registry, {pattern, "metric:sales.first"})
            assert not any(e["path"].endswith("reference.md") for e in edits)
            (root / "domains/sales/reference.md").write_text(legacy_text)
            registry = load_context(root)
            impact = cascade([registry], {"pattern:domains/sales/reference.md#pattern-first"})
            preview = drift.prepare(root, impact); apply(root, preview)
            registry = load_context(root)
            assert not registry.errors, list(map(str, registry.errors))
            assert registry.nodes["metric:sales.first"].effective_status == "draft"
            assert registry.nodes["metric:sales.second"].effective_status == "confirmed"
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); setup(root)
        baseline = (root / ".ci/lineage-baseline.json").read_bytes()
        # The fixture manifest lacks this context's models, producing real missing-model drift.
        command = [sys.executable, str(ROOT / ".ci/drift.py"), "--repo-root", str(root),
                   "--manifest", "dbt=" + str(ROOT / "tests/fixtures/mini_manifest.json")]
        result = subprocess.run([*command, "--prepare-patch", "--json-out", str(root / ".nodal/impact.json")],
                                capture_output=True, text=True)
        assert result.returncode == 1, result.stderr + result.stdout
        report = json.loads((root / ".nodal/impact.json").read_text())
        assert report["status"] == "reported_not_applied" and report["patch"]["status"] == "prepared_not_applied"
        assert read_yaml(root / "domains/sales/metrics/orders.yaml")["status"] == "confirmed"
        assert report["impact"]["snapshot_batch"] == ["seed:snapshot.seed.yaml"]
        result = subprocess.run([sys.executable, str(ROOT / ".ci/drift.py"), "--repo-root", str(root),
            "--apply-plan", report["patch"]["plan"], "--sha256", report["patch"]["sha256"]],
            capture_output=True, text=True)
        assert result.returncode == 0 and json.loads(result.stdout)["status"] == "applied", result.stderr
        # Missing models cannot be accidentally blessed into a replacement baseline.
        result = subprocess.run([*command, "--update-baseline"], capture_output=True, text=True)
        assert result.returncode == 2 and "baseline unchanged" in result.stderr
        assert (root / ".ci/lineage-baseline.json").read_bytes() == baseline
    print("test_drift_patches: OK")


if __name__ == "__main__":
    run()
