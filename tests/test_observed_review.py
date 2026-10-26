"""Reviewed observed edits: isolation, overflow, conflicts and crash recovery."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_fixtures import context, metric, seed, write
from acf_runtime.loader import Schemas, load_context, read_yaml
from acf_runtime.observed import read_queue
from acf_runtime import observed_review as review

REVIEWER = "fictional-test-reviewer"
SEED = "seed:orders.seed.yaml"
SEED_PATH = "evals/seeds/orders.seed.yaml"


def setup(root):
    context(root)
    write(root, "domains/sales/metrics/orders.yaml", metric())
    write(root, SEED_PATH, seed())
    q = root / review.QUEUE
    q.parent.mkdir(parents=True)
    rows = [dict(id=str(i), text=text, asked_at="2026-10-26T10:00:00Z", count=count,
                 status="pending", domain="sales", relation=relation) for i, text, count, relation in (
        (1, "How many purchases did each channel bring in last month?", 7, "equivalent"),
        (2, "Show me the order totals per channel please", 2, "ambiguous"),
        (3, "Give me channel-level order counts for the prior month", 9, "equivalent"),
        (4, "Orders by channel last month?", 1, "equivalent"))]
    q.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return rows


def reject(call, text=None):
    try:
        call()
    except ValueError as exc:
        if text:
            assert text in str(exc), (text, str(exc))
    else:
        raise AssertionError("unsafe/unreviewed mutation was accepted")


def prepare_variant(root, identifier):
    return review.prepare(root, identifier, reviewer=REVIEWER,
                          variant={"seed": SEED, "ir": seed()["ir"]})


def apply(root, prepared):
    return review.apply(root, prepared["proposal"], reviewer=REVIEWER, sha256=prepared["sha256"])


def run():
    schemas = Schemas(ROOT / "schemas")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        rows = setup(root)
        assert [r["id"] for r in review.list_pending(root)] == ["2", "3", "1", "4"]
        before = (root / SEED_PATH).read_bytes()
        prepared = prepare_variant(root, "1")
        assert (root / SEED_PATH).read_bytes() == before
        assert (root / prepared["proposal"]).stat().st_mode & 0o777 == 0o600
        reject(lambda: review.apply(root, prepared["proposal"], reviewer="different", sha256=prepared["sha256"]), "reviewer")
        reject(lambda: review.apply(root, prepared["proposal"], reviewer=REVIEWER, sha256="wrong"), "digest")
        result = apply(root, prepared)
        assert result["status"] == "complete"
        actual = read_yaml(root / SEED_PATH)
        assert actual["expected"] == seed()["expected"] and actual["approver"] == seed()["approver"]
        assert actual["variants"] == [{"text": rows[0]["text"], "observed_at": rows[0]["asked_at"],
                                        "provenance": "observed", "approver": REVIEWER}]
        assert read_queue(root, schemas)[0]["status"] == "linked"
        assert apply(root, prepared)["resumed"]
        assert len(read_yaml(root / SEED_PATH)["variants"]) == 1
        # Same timestamps evict stored-order first; the local history retains overflow.
        apply(root, prepare_variant(root, "2"))
        resolved_row = read_queue(root, schemas)[1]
        assert resolved_row["relation"] == "equivalent" and resolved_row["ir"]["metric"] == "metric:sales.orders"
        third = prepare_variant(root, "3")
        assert third["overflow_count"] == 1 and third["disposition"] == "replaced_oldest"
        receipt = apply(root, third)
        history = json.loads((root / receipt["history"]).read_text())
        assert history["plan"]["overflow"][0]["text"] == rows[0]["text"]
        duplicate = prepare_variant(root, "4")
        assert duplicate["disposition"] == "duplicate_dropped" and duplicate["overflow_count"] == 1
        apply(root, duplicate)
        assert len(read_yaml(root / SEED_PATH)["variants"]) == 2
        assert not review.list_pending(root)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); setup(root)
        path = root / review.QUEUE
        initial = path.read_text()
        path.write_text(initial.replace('"count": 7', '"count": 7, "count": 8', 1))
        reject(lambda: read_queue(root, schemas), "duplicate JSON")
        path.write_text(initial.replace('"domain": "sales"', '"domain": "missing"', 1))
        reject(lambda: review.list_pending(root), "unknown observation domain")
        path.write_text(initial.replace('"domain": "sales"', '"domain": "sales", "nearest_seeds": ["seed:missing"]', 1))
        reject(lambda: review.list_pending(root), "unknown nearest seed")
        path.write_text(initial)
        path.write_text(initial.replace('"domain": "sales"',
            '"domain": "sales", "ir": {"metric": null, "dimensions": ["channel"]}, "nearest_seeds": ["orders"]', 1))
        assert review.list_pending(root)
        path.write_text(initial)
        invalid_ir = initial.replace('"domain": "sales"', '"domain": "sales", "ir": {"result": 123}', 1)
        path.write_text(invalid_ir)
        reject(lambda: review.list_pending(root), "Additional properties")
        checked = subprocess.run([sys.executable, str(ROOT / ".ci/validate.py"), str(root), "--json"],
                                 capture_output=True, text=True)
        assert checked.returncode == 1
        assert any(d["code"] == "observed.invalid" for d in json.loads(checked.stdout)["diagnostics"])
        path.write_text(initial)
        # New-slice IR cannot be retained as an equivalent phrasing.
        reject(lambda: review.prepare(root, "1", reviewer=REVIEWER,
            variant={"seed": SEED, "ir": {"metric": "orders", "dimensions": ["date"]}}), "equivalent")
        reject(lambda: review.prepare(root, "1", reviewer=REVIEWER,
            variant={"seed": SEED, "ir": {**seed()["ir"], "time_window": "whenever"}}), "resolve one interpretation")
        prepared = prepare_variant(root, "1")
        write(root, "domains/sales/metrics/orders.yaml", metric(definition="Changed meaning"))
        reject(lambda: apply(root, prepared), "context changed")
        assert not read_yaml(root / SEED_PATH).get("variants")
        assert not list((root / review.LOCAL / "history").glob("*.json"))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); setup(root)
        # Proposed objects stay draft, and alias/dimension edits demote the object.
        value = metric("new_orders", status="draft")
        value.pop("approver"); value.pop("confirmed_at")
        draft_seed = seed(status="draft", ir={"metric": "new_orders"}, provenance="observed")
        draft_seed.pop("approver"); draft_seed.pop("confirmed_at")
        changes = [{"path": "domains/sales/metrics/new_orders.yaml", "content": yaml.safe_dump(value)},
                   {"path": "evals/seeds/new.seed.yaml", "content": yaml.safe_dump(draft_seed)}]
        prepared = review.prepare(root, "1", reviewer=REVIEWER, changes=changes)
        assert not (root / changes[0]["path"]).exists()
        real_write = review.atomic_private
        def crash_on_seed(path, raw, **kw):
            if path.name == "new.seed.yaml":
                raise OSError("synthetic interrupted write")
            return real_write(path, raw, **kw)
        with patch.object(review, "atomic_private", side_effect=crash_on_seed):
            try:
                apply(root, prepared)
            except OSError:
                pass
            else:
                raise AssertionError("crash injection did not execute")
        assert (root / changes[0]["path"]).exists() and not (root / changes[1]["path"]).exists()
        reject(lambda: prepare_variant(root, "2"), "resume the incomplete")
        # Independent caller edits survive and recovery reports the conflict.
        metric_path = root / changes[0]["path"]
        metric_path.write_text(changes[0]["content"] + "# external edit\n")
        reject(lambda: apply(root, prepared), "context changed")
        metric_path.write_text(changes[0]["content"])
        apply(root, prepared)
        assert not load_context(root).errors
        assert read_queue(root, schemas)[0]["status"] == "promoted"
        assert read_yaml(root / changes[1]["path"])["status"] == "draft"
        # Dismissal does not fabricate a negative seed.
        dismissed = review.prepare(root, "2", reviewer=REVIEWER, disposition="Not an analytics question")
        apply(root, dismissed)
        assert len(list((root / "evals/seeds").glob("*.seed.yaml"))) == 2
        assert read_queue(root, schemas)[1]["destinations"] == []
        reject(lambda: review.prepare(root, "3", reviewer=REVIEWER, changes=[{
            "path": "scripts/exploit.py", "content": "pass"}]), "destination")
        confirmed = [{"path": "domains/sales/metrics/other.yaml", "content": yaml.safe_dump(metric("other"))}]
        reject(lambda: review.prepare(root, "3", reviewer=REVIEWER, changes=confirmed), "remain draft")
        forged = metric("other", status="draft")
        reject(lambda: review.prepare(root, "3", reviewer=REVIEWER, changes=[{
            "path": "domains/sales/metrics/other.yaml", "content": yaml.safe_dump(forged)}]), "confirmation metadata")
        negative = seed(status="draft", expected={"kind": "negative", "reason": "lack_data",
                                                  "must_include": ["State that the required data is unavailable"]})
        for key in ("ir", "approver", "confirmed_at"):
            negative.pop(key)
        prepared = review.prepare(root, "3", reviewer=REVIEWER, disposition="Reviewed unavailable data",
            changes=[{"path": "evals/seeds/unavailable.seed.yaml", "content": yaml.safe_dump(negative)}])
        apply(root, prepared)
        row = read_queue(root, schemas)[2]
        assert row["status"] == "declined" and row["destinations"] == ["evals/seeds/unavailable.seed.yaml"]
        # Symlinked local state and queue paths are rejected, even within the repo.
        queue = root / review.QUEUE
        queue.rename(root / "queue.jsonl"); queue.symlink_to(root / "queue.jsonl")
        reject(lambda: review.list_pending(root), "symlink")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); setup(root)
        prepared = prepare_variant(root, "1")
        # A crash after the queue write but before completion replays without duplicates.
        original_write = review.atomic_private
        def crash_before_complete(path, raw, **kw):
            if path.parent.name == "history" and json.loads(raw)["state"] == "complete":
                raise OSError("synthetic completion interruption")
            return original_write(path, raw, **kw)
        with patch.object(review, "atomic_private", side_effect=crash_before_complete):
            try:
                apply(root, prepared)
            except OSError:
                pass
        assert read_queue(root, schemas)[0]["status"] == "linked"
        apply(root, prepared)
        assert len(read_yaml(root / SEED_PATH)["variants"]) == 1
        ir_path = root / ".nodal/ir.json"; ir_path.write_text(json.dumps(seed()["ir"]))
        command = [sys.executable, str(ROOT / "scripts/match_question.py"), "--root", str(root),
                   "--domain", "sales", "--ir", str(ir_path)]
        process = subprocess.run(command, capture_output=True, text=True)
        assert process.returncode == 0, process.stderr
        match = json.loads(process.stdout)
        assert match["relation"] == "equivalent" and match["seeds"] == [SEED]
        assert "expected" not in match
        process = subprocess.run([*command, "--exclude", SEED], capture_output=True, text=True)
        assert json.loads(process.stdout)["seeds"] == []
        process = subprocess.run([sys.executable, str(ROOT / "scripts/review_observed.py"), "list",
                                  "--root", str(root)], capture_output=True, text=True)
        assert process.returncode == 0 and len(json.loads(process.stdout)["pending"]) == 3
        command = [sys.executable, str(ROOT / "scripts/review_observed.py")]
        result = subprocess.run([*command, "prepare", "--root", str(root), "--observation", "4",
            "--decline", "--reviewer", REVIEWER, "--disposition", "Redundant local observation"],
            capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        preview = json.loads(result.stdout)
        result = subprocess.run([*command, "apply", "--root", str(root), "--reviewer", REVIEWER,
            "--proposal", preview["proposal"], "--sha256", preview["sha256"]], capture_output=True, text=True)
        assert result.returncode == 0 and json.loads(result.stdout)["status"] == "complete", result.stderr
        # Extraction sees definitions only, not seed questions, variants or expected values.
        spec = importlib.util.spec_from_file_location("match_cli", ROOT / "scripts/match_question.py")
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        def extract(question, domain, definitions, **kwargs):
            assert question == "test question" and domain == "sales"
            assert "must_include" not in json.dumps(definitions) and "variants" not in json.dumps(definitions)
            return {"ir": seed()["ir"], "candidates": []}
        with patch.object(module.client, "available", return_value=True), patch.object(module.client, "extract_ir", side_effect=extract), redirect_stdout(io.StringIO()):
            assert module.main(["--root", str(root), "--domain", "sales", "--question", "test question"]) == 0
    print("test_observed_review: OK")


if __name__ == "__main__":
    run()
