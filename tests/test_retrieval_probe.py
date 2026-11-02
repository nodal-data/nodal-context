"""Offline fixture safety and retrieval measurement checks; no model calls."""

import copy
import importlib.util
import json
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
    print("test_retrieval_probe: OK")


if __name__ == "__main__":
    run()
