"""Offline simulation boundaries and opt-in short live clean-room acceptance."""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_fixtures import context, metric, method, seed, write, METHOD_BODY
from acf_runtime.simulation import (MARKER, load_marker, handoff, record, pending,
                                    attest_confirmation, check_output)
from acf_runtime.loader import load_context
from eval_harness.adapters.acf import build_ncr
from eval_harness.report import render

HARNESS = ROOT / "scripts/integration/clean_test.py"


def run_harness(*args, env=None):
    return subprocess.run([sys.executable, str(HARNESS), *map(str, args)], cwd=ROOT,
                          capture_output=True, text=True, env=env)


def marker(room, mode="non-interactive"):
    project = room / "project"; project.mkdir()
    brief = room / "responses.md"; brief.write_text("Synthetic private brief. Do not open in the interviewer.")
    path = project / MARKER
    path.write_text(json.dumps({"responses": str(brief), "log": str(room / "log.md"), "mode": mode}))
    return path


def draft(value):
    value = deepcopy(value)
    value["status"] = "draft"
    for key in ("approver", "confirmed_at"):
        value.pop(key, None)
    return value


def populate(root):
    context(root)
    write(root, "domains/sales/domain.yaml", {"name": "sales", "summary": "Fictional simulation",
          "status": "draft", "grain": "order", "lineage": [{"source": "dbt", "models": ["orders"]}]})
    write(root, "domains/sales/metrics/orders.yaml", draft(metric()))
    write(root, "methods/repeat.md", draft(method()), METHOD_BODY)
    write(root, "evals/seeds/orders.seed.yaml", draft(seed()))


def reject(call, message):
    try:
        call()
    except (ValueError, OSError) as exc:
        assert message in str(exc), str(exc)
    else:
        raise AssertionError("expected rejection: " + message)


def fake_host(path):
    path.write_text('''#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
project = Path.cwd()
sys.path.insert(0, str(project))
sys.path.insert(0, str(project / "tests"))
from acf_runtime.simulation import record, pending
from test_simulation import populate
marker = project / ".sim-analyst.json"
output = project.parent / "analytics-context"
prompt = sys.argv[-1]
assert str(marker) in prompt and "Keep simulator-only artifacts draft" in prompt
assert str(output / ".sim-analyst.json") in prompt
Path(os.environ["SIM_TEST_PROMPT"]).write_text(prompt)
if os.environ.get("SIM_TEST_MODE") == "early_pending":
    record(marker, identifier="q-open", stage="0", question="Which business should this represent?",
           reply="NOT_CONFIDENT: the fictional brief does not say")
    print("Synthetic host paused for actual human input")
    raise SystemExit(0)
if not (output / "context.config.yaml").exists():
    subprocess.run([sys.executable, str(project / "scripts/scaffold.py"), str(output),
                    "--sim-marker", str(marker)], check=True)
populate(output)
record(output / ".sim-analyst.json", identifier="q-metric", stage="2",
       question="How do you count orders?", reply="CONFIDENT: Count eligible non-test orders.")
if os.environ.get("SIM_TEST_MODE") == "forged":
    import yaml
    path = output / "domains/sales/metrics/orders.yaml"
    data = yaml.safe_load(path.read_text())
    data.update(status="confirmed", approver="simulator", confirmed_at="2026-10-26")
    path.write_text(yaml.safe_dump(data))
print("Synthetic host created ACF 0.3 drafts; no warehouse, dashboard or notebook executed.")
''')
    path.chmod(0o755)


def run():
    with tempfile.TemporaryDirectory() as directory:
        room = Path(directory).resolve(); source = marker(room)
        root = room / "analytics-context"
        # Patch file-reading to prove marker/state helpers never open the brief.
        real_read = Path.read_text
        def guarded(path, *args, **kwargs):
            assert path.name != "responses.md", "helper read the private knowledge brief"
            return real_read(path, *args, **kwargs)
        with patch.object(Path, "read_text", guarded):
            handoff(source, root)
            assert load_marker(root / MARKER) == load_marker(source)
            result = record(source, identifier="q1", stage="3", question="Which entity?",
                            reply="CONFIDENT: canonical customer identity")
            assert result["next"] == "continue_drafting"
            assert record(root / MARKER, identifier="q1", stage="3", question="Which entity?",
                          reply="CONFIDENT: canonical customer identity") == result
            uncertain = record(source, identifier="q2", stage="6", question="Which cohort anchor?",
                               reply="NOT_CONFIDENT: acquisition or activity is unspecified")
            assert uncertain["next"] == "pause" and len(pending(root / MARKER)) == 1
            reject(lambda: record(source, identifier="q2", stage="6", question="Which cohort anchor?",
                                  reply="CONFIDENT: acquisition"), "actual human")
            record(root / MARKER, identifier="q2", stage="6", question="Which cohort anchor?",
                   reply="Activity cohort", source="human", reviewer="fictional-human")
            assert not pending(source)
        state = json.loads(Path(load_marker(source)["state"]).read_text())
        assert len(state["events"]) == 3 and state["questions"]["q2"]["source"] == "human"
        assert Path(load_marker(source)["state"]).stat().st_mode & 0o777 == 0o600
        assert Path(load_marker(source)["log"]).stat().st_mode & 0o777 == 0o600
        assert not (root / "responses.md").exists()
        reject(lambda: record(source, identifier="q1", stage="3", question="Different question",
                              reply="CONFIDENT: yes"), "different question")
        reject(lambda: record(source, identifier="q3", stage="3", question="Which?", reply="CONFIDENT: yes",
                              reviewer="simulator"), "cannot name a human")
        populate(root)
        assert not check_output(root, source, require_content=True)
        registry = load_context(root)
        assert not registry.errors and all(n.data.get("status") == "draft" for n in registry.nodes.values())
        ncr = build_ncr(root)
        assert not ncr.seeds_for("sales") and len(ncr.seeds_for("sales", "draft")) == 1
        assert "not human-verified coverage" in render([{"domain": "sales", "selection": "draft", "seeds": []}])
        write(root, "domains/sales/metrics/orders.yaml", metric())
        assert any("simulator cannot confirm metric:sales.orders" in p for p in check_output(root))
        reject(lambda: attest_confirmation(source, root, "metric:sales.orders", "wrong-name"), "match")
        attest_confirmation(source, root, "metric:sales.orders", "fictional-test-owner")
        assert not check_output(root)
        path = root / "domains/sales/metrics/orders.yaml"
        path.write_text(path.read_text() + "# changed after human review\n")
        assert any("receipt is missing" in p for p in check_output(root))
        changed = metric(status="draft", definition="Revised interpretation pending human review")
        write(root, "domains/sales/metrics/orders.yaml", changed)
        assert not check_output(root)  # earlier genuine approval may remain historical on a draft
        changed["approver"] = "invented-human"
        write(root, "domains/sales/metrics/orders.yaml", changed)
        assert any("unsubstantiated" in p for p in check_output(root))
        # Fresh scaffolding can explicitly hand off an external marker outside a harness.
        other = room / "other-context"
        process = subprocess.run([sys.executable, str(ROOT / "scripts/scaffold.py"), str(other),
                                  "--sim-marker", str(source)], capture_output=True, text=True)
        assert process.returncode == 0, process.stderr + process.stdout
        assert load_marker(other / MARKER) == load_marker(source)
        assert not (other / "responses.md").exists()
        # The entire private room must not become the context root.
        reject(lambda: handoff(source, room), "contain the private brief")
    with tempfile.TemporaryDirectory() as directory:
        room = Path(directory).resolve(); source = marker(room, "interactive")
        result = record(source, identifier="q1", stage="2", question="What is revenue?", reply="unstructured reply")
        assert result["next"] == "ask_human" and len(pending(source)) == 1
    with tempfile.TemporaryDirectory() as directory:
        room = Path(directory).resolve(); source = marker(room)
        assert record(source, identifier="batch-ok", stage="0", question="Company and owner?",
                      reply="CONFIDENT: 1a. Fictional shop. 1b. Fictional owner.")["next"] == "continue_drafting"
        for identifier, reply in (
                ("numbered", "1a CONFIDENT: Fictional shop.\n1b CONFIDENT: Fictional owner."),
                ("mixed", "CONFIDENT: 1a. Fictional shop.\n1b NOT_CONFIDENT: Owner missing.")):
            assert record(source, identifier=identifier, stage="0", question="Company and owner?",
                          reply=reply)["next"] == "pause"
        assert len(pending(source)) == 2
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory).resolve()
        brief = base / "operator-brief.md"; brief.write_text("Synthetic fixture, not customer data.")
        binary = base / "bin"; binary.mkdir(); fake_host(binary / "claude")
        environment = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ.get("PATH", ""),
                       "SIM_TEST_PROMPT": str(base / "prompt.txt"), "SIM_TEST_MODE": "early_pending"}
        room = base / "quick-room"
        prepared = run_harness("--auto=" + str(brief), "--host", "claude", room, "--prepare-only", env=environment)
        assert prepared.returncode == 0, prepared.stderr + prepared.stdout
        source = room / "project" / MARKER; output = room / "analytics-context"
        assert load_marker(source) == load_marker(output / MARKER)
        assert Path(load_marker(source)["responses"]).stat().st_mode & 0o777 == 0o600
        for private in ("specs", "shorelanev4.context.md", "responses.md", ".nodal", "clean-test.sh"):
            assert not (room / "project" / private).exists(), private
        launched = run_harness("--launch-prepared", room, "--non-interactive", env=environment)
        assert launched.returncode == 3, launched.stderr + launched.stdout
        assert not (output / "context.config.yaml").exists()
        assert len(pending(source)) == 1
        paused_summary = json.loads((room / "simulation-summary.json").read_text())
        assert not paused_summary["context_created"]
        assert paused_summary["pending_human_questions"][0]["id"] == "q-open"
        prompt = Path(environment["SIM_TEST_PROMPT"]).read_text()
        assert "NOT_CONFIDENT" in prompt and "Do not guess" in prompt
        assert str(room / "project/skills/context-interview/scripts/scaffold.py") in prompt
        assert str(room / "project/skills/context-interview/scripts/simulated_analyst.py") in prompt
        assert str(output / ".ci/validate.py") in prompt
        assert "paths do not grant permission" in prompt
        # Resume works even when the first unresolved question preceded scaffolding.
        resumed = run_harness("--resume", room, "--prepare-only", env=environment)
        assert resumed.returncode == 0, resumed.stderr + resumed.stdout
        assert (output / ".nodal-clean-test-resume-marker").exists()
        assert len(pending(output / MARKER)) == 1
        record(source, identifier="q-open", stage="0", question="Which business should this represent?",
               reply="The synthetic sales fixture", source="human", reviewer="fictional-human")
        environment["SIM_TEST_MODE"] = "draft"
        resumed = run_harness("--resume", room, "--non-interactive", env=environment)
        assert resumed.returncode == 0, resumed.stderr + resumed.stdout
        assert not check_output(output, source, require_content=True)
        assert load_context(output).methods and len(load_context(output).metrics) == 1
        summary = json.loads((room / "simulation-summary.json").read_text())
        assert summary["context_valid"] and summary["draft_metrics"] == ["domains/sales/metrics/orders.yaml"]
        assert summary["draft_methods"] and summary["verification_work"]
        assert summary["execution_verification"] == "not_established_by_simulation"
        assert Path(summary["exchange_log"]).is_file() and not summary["pending_human_questions"]
        assert (room / "simulation-summary.json").stat().st_mode & 0o777 == 0o600
        assert "draft capture summary" in resumed.stdout and "simulation does not establish execution" in resumed.stdout
        before = (output / "domains/sales/metrics/orders.yaml").read_bytes()
        resumed = run_harness("--resume", room, "--prepare-only", env=environment)
        assert resumed.returncode == 0 and (output / "domains/sales/metrics/orders.yaml").read_bytes() == before
        assert load_marker(source)["mode"] == "interactive"  # mode follows the selected launch, not old argv
        replacement = base / "different.md"; replacement.write_text("Different fictional business")
        refused = run_harness("--resume", room, "--brief", replacement, "--prepare-only", env=environment)
        assert refused.returncode == 2 and "differs" in refused.stderr
        refused = run_harness("--auto=" + str(brief), "--host", "none", room, "--prepare-only", env=environment)
        assert refused.returncode == 2 and "refusing to replace" in refused.stderr
        assert (output / "domains/sales/metrics/orders.yaml").read_bytes() == before
        forged = base / "forged-room"; environment["SIM_TEST_MODE"] = "forged"
        result = run_harness("--brief", brief, "--host", "claude", "--work-dir", forged,
                             "--non-interactive", env=environment)
        assert result.returncode == 1 and "simulator cannot confirm" in result.stderr
    # Copy filtering is explicit, including accidentally tracked sensitive files.
    sys.path.insert(0, str(ROOT / "scripts/integration"))
    spec = importlib.util.spec_from_file_location("clean_test", HARNESS)
    harness = importlib.util.module_from_spec(spec); spec.loader.exec_module(harness)
    for name in ("specs/a.md", "responses.md", "customer.context.md", "examples/raw.ipynb",
                 "evals/runs/raw.json", "evals/verified/answer.sql", ".sim-analyst.json",
                 "simulated-analyst-log.md", ".codex/auth.json", ".aws/credentials"):
        assert harness._private_path(Path(name)), name
    for name in ("SPEC.md", "schemas/config.schema.json", "evals/verified/answer.sql.age", "evals/runs/.gitkeep"):
        assert not harness._private_path(Path(name)), name
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory).resolve(); source = base / "source"; source.mkdir()
        for name in ("SPEC.md", "specs/plan.md", "raw.ipynb", "notes/custom-brief.md", ".env",
                     "responses.md", "schemas/config.schema.json", "evals/verified/answer.sql",
                     "evals/verified/answer.sql.age"):
            path = source / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic fixture")
        subprocess.run(["git", "init", "--quiet"], cwd=source, check=True)
        subprocess.run(["git", "add", "--force", "."], cwd=source, check=True)
        destination = base / "copy"
        with patch.object(harness, "ROOT", source):
            harness._copy_source_checkout(destination, brief=source / "notes/custom-brief.md")
        assert (destination / "SPEC.md").exists() and (destination / "schemas/config.schema.json").exists()
        assert (destination / "evals/verified/answer.sql.age").exists()
        for name in ("specs", "raw.ipynb", "notes/custom-brief.md", ".env", "responses.md", "evals/verified/answer.sql"):
            assert not (destination / name).exists(), name
    # Compatibility wrapper delegates flags without implementing copy/delete or permission policy.
    wrapper = ROOT / "clean-test.sh"
    if wrapper.exists():
        text = wrapper.read_text()
        assert "scripts/integration/clean_test.sh" in text and "rm -rf" not in text
        checked = subprocess.run([str(wrapper), "--help"], capture_output=True, text=True)
        assert checked.returncode == 0 and "--auto" in checked.stdout and "--resume" in checked.stdout
    print("test_simulation: OK (offline; no actual agent or warehouse)")


def live(host, prepare_only=False):
    """Maintainer-operated, explicitly selected real host run using fictional input."""
    room = Path(tempfile.mkdtemp(prefix="nodal-sim-live-")).resolve()
    brief = room / "fictional-brief.md"
    brief.write_text("""# Fictional Northstar Shop — simulated analyst brief
This is an offline fictional test. Build a 30-minute test drive for one domain,
sales, and leave everything draft. Company name: Northstar Shop. Business: sells
goods directly to retail customers, who pay Northstar Shop for those goods.
Sales domain owner: Morgan, a fictional business owner, not a real approver.
Warehouse: none available. No dbt repo, dashboard, credentials,
website, notebook, external tools or query history are available; skip verification.
Lineage source: fictional raw SQL orders model, source id sample, warehouse sqlite.
Domain grain: one order row. Table: orders. Fields: order_id, customer_id, channel,
ordered_at, is_test. orders is the only table in this test drive. order_id is the
sole, stable, unique order identifier; there are no duplicate rows or alternate
order IDs. is_test is a non-null boolean. The two priority metrics are orders and
ordering_customers. orders counts rows excluding is_test=true. ordering_customers
counts distinct customer_id among those same eligible orders within the selected
window; counting order rows instead overcounts customers with multiple purchases.
Both are flow metrics, date basis ordered_at, UTC, last_month token. Dimensions:
channel and ordered_at. Date windows include the start and exclude the end.
The ambiguous entity term is customer: people sometimes mean a contact/display
name alias, but sales analysis means the canonical purchasing customer_id. A
customer can have multiple names; those names are not identifiers or join keys.
Customers have one canonical customer_id, no alternate ID system in this test;
join/group by customer_id, never by a name. Each order belongs to one customer;
each customer may have many orders and may buy through several channels.
Method repeat: count distinct canonical customer_id with at least two eligible
orders within the window parameter, grouped by channel. Decisions: canonical
identity prevents alias double counting; exclude test orders consistently; require
two orders within the same selected window. Output: channel and repeat_customers;
state window and identity basis. Each customer counts once within each channel.
Checks: repeat customers cannot exceed eligible distinct customers in that channel.
Aliases: purchases means orders. Caveats: test rows excluded, ordered_at not
payment date, and no live result claims. Standard hygiene: always exclude test
orders from both metrics and the method; no exception is in scope. The silent
failure is summing per-channel distinct customer counts as if they were a global
distinct customer count: multi-channel customers then count twice. Recompute the
global distinct count instead. Seed question: Orders by channel last month?
Expected SQL shape: exclude test orders, group by channel and use ordered_at.
No numbers are supplied and no snapshot should be confirmed. Unknown business
questions require NOT_CONFIDENT; do not guess. No real approver is supplied.
""")
    brief.chmod(0o600)
    destination = room / "run"
    prompt = ("Use context-interview for a short simulated test drive of one domain. "
              "Create valid ACF 0.3 draft metric, method and seed files. Ask at most five "
              "batched business questions of the isolated responder. The marker carries "
              "the private brief path; never read it as interviewer. This is offline: "
              "do not connect to a warehouse/browser or configure/install services. "
              "Do not seek approval to create the already requested ../analytics-context "
              "destination. Keep definitions draft, record questions and stop on missing knowledge.")
    command = [sys.executable, str(HARNESS), "--package-source", "source-checkout",
        "--host", host, "--work-dir", str(destination), "--brief", str(brief),
        "--non-interactive", "--prompt", prompt]
    if prepare_only:
        command.append("--prepare-only")
    result = subprocess.run(command, cwd=ROOT)
    print(f"test_simulation: live artifacts preserved at {room}")
    if prepare_only:
        print("test_simulation: prepared only; launch through the harness with operator-owned permissions, then inspect draft metric/method/seed output")
        return result.returncode
    if result.returncode:
        return result.returncode
    context_root = destination / "analytics-context"
    problems = check_output(context_root, require_content=True)
    if not load_context(context_root).methods:
        problems.append("live simulation produced no method draft")
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", choices=["claude", "codex"], help="explicitly run a real host, using customer-owned authentication")
    parser.add_argument("--prepare-only", action="store_true", help="prepare the --live fictional room for operator permissions without starting a host")
    args = parser.parse_args()
    if args.prepare_only and not args.live:
        parser.error("--prepare-only requires --live")
    if args.live:
        raise SystemExit(live(args.live, args.prepare_only))
    run()
