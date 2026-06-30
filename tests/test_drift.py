"""Golden behavior test for .ci/drift.py — stdlib only, no pytest dep.

Reuses tests/fixtures/mini_manifest.json (models: stg_orders, dim_customer,
fct_orders) as the "current" dbt state, builds a baseline from it, then mutates the
baseline to simulate upstream change and asserts drift is detected precisely.

Run: python3 tests/test_drift.py   (exit 0 = pass)
"""
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".ci"))
import drift  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "mini_manifest.json"

# One domain ("orders") whose context describes three dbt_core models.
DOMAINS = {"orders": [("dbt_core", ["stg_orders", "dim_customer", "fct_orders"])]}
REFERENCED = {"dbt_core": {"stg_orders", "dim_customer", "fct_orders"}}


def _current(manifests):
    return drift.compute_current(REFERENCED, manifests)


def run():
    manifests = {"dbt_core": str(FIXTURE)}
    current, missing, unchecked = _current(manifests)

    # --- current state reflects the manifest -------------------------------
    assert not missing and not unchecked, (missing, unchecked)
    fct = current["dbt_core"]["fct_orders"]
    assert "order_id" in fct["columns"], fct["columns"]
    # accepted_values / relationships / not_null all surface as comparable test sigs
    assert any(s.startswith("accepted_values:") for s in fct["tests"]), fct["tests"]
    assert any(s.startswith("relationships:") for s in fct["tests"]), fct["tests"]

    # --- clean: baseline == current => no drift ----------------------------
    baseline = drift.build_baseline(current)
    assert baseline["version"] == drift.BASELINE_VERSION
    changes = drift.diff_signatures(baseline, current)
    assert changes == {}, changes
    _, drifted = drift.build_report(DOMAINS, changes, {}, [], ROOT)
    assert drifted is False

    # --- column drift: baseline missing a column => "added"; extra => "removed"
    tampered = copy.deepcopy(baseline)
    bfct = tampered["sources"]["dbt_core"]["models"]["fct_orders"]
    removed_col = bfct["columns"].pop()            # current has it, baseline doesn't
    bfct["columns"].append("zzz_legacy_col")       # baseline has it, current doesn't
    a_test = bfct["tests"].pop()                    # current has it, baseline doesn't
    bfct["tests"].append("not_null:ghost_col")     # baseline has it, current doesn't

    changes = drift.diff_signatures(tampered, current)
    rec = changes["dbt_core"]["fct_orders"]
    assert removed_col in rec["columns_added"], rec
    assert "zzz_legacy_col" in rec["columns_removed"], rec
    assert a_test in rec["tests_added"], rec
    assert "not_null:ghost_col" in rec["tests_removed"], rec

    report, drifted = drift.build_report(DOMAINS, changes, {}, [], ROOT)
    assert drifted is True
    assert "domain: orders" in report
    assert "fct_orders" in report

    # --- dropped model: referenced but absent from the manifest ------------
    extra_ref = {"dbt_core": REFERENCED["dbt_core"] | {"fct_ghost"}}
    _, missing2, _ = drift.compute_current(extra_ref, manifests)
    assert missing2.get("dbt_core") == ["fct_ghost"], missing2
    domains_g = {"orders": [("dbt_core", ["fct_ghost"])]}
    _, drifted = drift.build_report(domains_g, {}, missing2, [], ROOT)
    assert drifted is True

    # --- unchecked source: referenced but no manifest supplied -------------
    _, _, unchecked3 = drift.compute_current(REFERENCED, {})
    assert unchecked3 == ["dbt_core"], unchecked3

    # --- new model: in current, not in baseline ----------------------------
    base_no_fct = copy.deepcopy(baseline)
    del base_no_fct["sources"]["dbt_core"]["models"]["fct_orders"]
    changes = drift.diff_signatures(base_no_fct, current)
    assert changes["dbt_core"]["fct_orders"] == {"new_model": True}, changes

    # --- affected-file listing picks up real files on disk -----------------
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        dom = repo / "domains" / "orders"
        dom.mkdir(parents=True)
        (dom / "domain.yaml").write_text("name: orders\n")
        (dom / "reference.md").write_text("# orders\n")
        files = drift._domain_files(repo, "orders")
        assert files == ["domains/orders/domain.yaml", "domains/orders/reference.md"], files

    # --- load_config round-trips the seam (only if PyYAML present) ----------
    try:
        import yaml  # noqa: F401
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "context.config.yaml"
            cfg.write_text(
                "version: 0.1\nwarehouse: snowflake\n"
                "lineage_sources:\n  - id: dbt_core\n    type: dbt\n"
                "domains:\n  orders:\n    lineage:\n"
                "      - source: dbt_core\n        models: [fct_orders, dim_customer]\n"
            )
            domains, referenced = drift.load_config(cfg)
            assert domains == {"orders": [("dbt_core", ["fct_orders", "dim_customer"])]}
            assert referenced == {"dbt_core": {"fct_orders", "dim_customer"}}
    except ImportError:
        print("test_drift: PyYAML not installed; skipped load_config round-trip")

    print("test_drift: OK")


if __name__ == "__main__":
    run()
