"""Offline fixture safety and retrieval measurement checks; no model calls."""

import copy
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "retrieval_probe", ROOT / "scripts/integration/retrieval_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def capture():
    return {
        "configuration": "skill-only", "host": "fixture", "model": "fixture",
        "settings_id": "same-settings", "fixture_sha256": "fixture", "run_id": "one",
        "tokenizer": "test-counter",
        "events": [{"kind": "evidence", "raw_response": "évidence plus unrelated",
                    "emitted_response": "évidence", "emitted_tokens": 3,
                    "capture_complete": True, "overview": False,
                    "business_execution": False,
                    "model_bodies": ["model.retrieval_fixture.fct_orders"]}],
        "review": {"constraints_retained": True, "approval_preserved": True,
                   "evidence_complete": True, "evidence": "Synthetic unit test, not a live run."},
    }


def rejects(run):
    try:
        probe.compare([run])
    except ValueError:
        return
    raise AssertionError("invalid capture accepted")


def run():
    with tempfile.TemporaryDirectory() as temporary:
        first = Path(temporary) / "one"
        second = Path(temporary) / "two"
        a, b = probe.prepare(first), probe.prepare(second)
        assert a["fixture_sha256"] == b["fixture_sha256"]
        models = yaml.safe_load((first / "models/_marts.yml").read_text())["models"]
        assert len(models) == 32
        assert len(list((first / "models").glob("*.sql"))) == 32
        assert "customer_created_date" in json.dumps(models[0]["data_tests"])
        assert "account_type = 'customer'" in (first / "models/dim_customers.sql").read_text()
        sources = yaml.safe_load((first / "models/_sources.yml").read_text())["sources"]
        declared = {(s["name"], t["name"]) for s in sources for t in s["tables"]}
        referenced = set()
        for sql in (first / "models").glob("*.sql"):
            referenced.update(re.findall(r"source\('([^']+)', '([^']+)'\)", sql.read_text()))
        assert declared == referenced and len(declared) == 32
        # Opt-in real parser smoke test; no database connection or model execution.
        if os.environ.get("RETRIEVAL_PROBE_DBT"):
            profiles = Path(temporary) / "profiles"
            profiles.mkdir()
            (profiles / "profiles.yml").write_text(
                "retrieval_fixture:\n  target: local\n  outputs:\n    local:\n"
                "      type: duckdb\n      path: ':memory:'\n      threads: 1\n")
            subprocess.run([os.environ["RETRIEVAL_PROBE_DBT"], "parse", "--no-partial-parse",
                            "--project-dir", str(first), "--profiles-dir", str(profiles)],
                           check=True, env={**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"})
            manifest = json.loads((first / "target/manifest.json").read_text())
            assert len(manifest["sources"]) == 32
            assert sum(n["resource_type"] == "model" for n in manifest["nodes"].values()) == 32
            assert any(n.get("test_metadata", {}).get("name") == "expression_is_true"
                       for n in manifest["nodes"].values())
        marker = first / "keep.txt"
        marker.write_text("caller data")
        try:
            probe.prepare(first)
        except FileExistsError:
            pass
        else:
            raise AssertionError("existing caller directory accepted")
        assert marker.read_text() == "caller data"

    c = capture()
    report = probe.compare([c])
    result = report["runs"][0]
    assert result["evidence_bytes"] == len("évidence".encode())
    assert result["raw_bytes"] > result["evidence_bytes"]
    assert result["evidence_tokens"] == 3
    assert report["missing_configurations"] == ["baseline", "combined", "server-only"]
    for key in ("host", "fixture_sha256", "review"):
        invalid = copy.deepcopy(c)
        del invalid[key]
        rejects(invalid)
    invalid = copy.deepcopy(c)
    invalid["events"][0]["capture_complete"] = False
    rejects(invalid)
    invalid = copy.deepcopy(c)
    invalid["events"][0]["overview"] = "false"
    rejects(invalid)
    for field, value in (("events", []), ("events", [None]), ("review", None)):
        invalid = copy.deepcopy(c)
        invalid[field] = value
        rejects(invalid)
    rejects(None)
    invalid = copy.deepcopy(c)
    del invalid["events"][0]["emitted_tokens"]
    assert probe.compare([invalid])["runs"][0]["evidence_tokens"] is None
    other = copy.deepcopy(c)
    other["run_id"] = "two"
    other["fixture_sha256"] = "different"
    try:
        probe.compare([c, other])
    except ValueError:
        pass
    else:
        raise AssertionError("unmatched fixtures compared")
    failed = copy.deepcopy(c)
    failed["configuration"] = "combined"
    failed["events"][0].update(overview=True, business_execution=True,
                               model_bodies=["model.retrieval_fixture.supplier_01"])
    failed["review"]["constraints_retained"] = False
    findings = probe.compare([failed])["runs"][0]
    assert len(findings["failures"]) == 3
    assert findings["unrelated_model_bodies"] == 1
    baseline = capture()
    baseline.update(configuration="baseline", run_id="baseline")
    baseline["events"][0]["emitted_tokens"] = 10
    combined = capture()
    combined.update(configuration="combined", run_id="combined")

    def check_acceptance(runs, status, exit_code):
        report = probe.compare(runs)
        assert report["combined_acceptance"]["status"] == status
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.json"
            path.write_text(json.dumps(runs))
            command = subprocess.run([sys.executable, str(ROOT / "scripts/integration/retrieval_probe.py"),
                                      "report", str(path)], capture_output=True, text=True)
            assert command.returncode == exit_code, command.stderr
            assert json.loads(command.stdout) == report
        return report

    check_acceptance([baseline, combined], "pass", 0)
    for count in (10, 30):
        combined["events"][0]["emitted_tokens"] = count
        check_acceptance([baseline, combined], "fail", 1)
    combined["events"][0]["emitted_tokens"] = 3
    check_acceptance([combined], "not_evaluated", 2)
    combined["tokenizer"] = "different-counter"
    report = check_acceptance([baseline, combined], "not_evaluated", 2)
    assert report["token_comparison"]["status"] == "incomparable"
    assert all("evidence_tokens" not in median for median in report["medians"].values())
    assert report["medians"]["combined"]["evidence_bytes"] > 0
    combined["configuration"] = "skill-only"
    assert probe.compare([baseline, combined])["token_comparison"]["status"] == "incomparable"
    combined.update(configuration="combined", tokenizer="test-counter")
    for value in (None, "", "   ", True, ["counter"]):
        missing = copy.deepcopy(combined)
        missing["tokenizer"] = value
        check_acceptance([baseline, missing], "not_evaluated", 2)
    missing = copy.deepcopy(combined)
    del missing["events"][0]["emitted_tokens"]
    check_acceptance([baseline, missing], "not_evaluated", 2)
    execution_only = copy.deepcopy(combined)
    execution_only["events"][0]["kind"] = "execution"
    report = check_acceptance([baseline, execution_only], "not_evaluated", 2)
    assert report["runs"][1]["evidence_tokens"] is None
    assert report["runs"][1]["discovery_tokens"] is None
    combined["events"][0]["emitted_tokens"] = 0
    assert check_acceptance([baseline, combined], "pass", 0)["runs"][1]["evidence_tokens"] == 0
    combined["review"]["constraints_retained"] = False
    check_acceptance([baseline, combined], "fail", 1)
    # Take the median of each run's total, not the sum of category medians.
    totals = []
    for index, (discovery, evidence) in enumerate(((0, 9), (9, 0), (8, 8))):
        item = copy.deepcopy(baseline)
        item["run_id"] = str(index)
        item["events"][0]["emitted_tokens"] = evidence
        item["events"].append({**item["events"][0], "kind": "discovery", "emitted_tokens": discovery})
        totals.append(item)
    assert probe.compare(totals)["medians"]["baseline"]["retrieval_tokens"] == 9
    print("test_retrieval_probe: OK")


if __name__ == "__main__":
    run()
