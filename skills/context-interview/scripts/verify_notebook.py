#!/usr/bin/env python3
"""Explicit independent notebook/method runs, or human-confirmed snapshot promotion."""
import argparse
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE if (BASE / "acf_runtime").is_dir() else BASE / "payload"))
from acf_runtime.notebook_verification import verify, confirm
from eval_harness.execution import strict_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="operation", required=True)
    run = sub.add_parser("run")
    run.add_argument("notebook", type=Path)
    run.add_argument("--method", required=True)
    run.add_argument("--question", required=True)
    run.add_argument("--case", type=Path, required=True, help="JSON file of agreed bindings, snapshot, keys and tolerances")
    for role in ("reference", "answer", "judge"):
        run.add_argument("--" + role + "-command", type=strict_json, help="trusted customer executor as a JSON argv array")
    run.add_argument("--timeout", type=int, default=600, help="per-executor timeout in seconds")
    approval = sub.add_parser("confirm")
    approval.add_argument("report", type=Path)
    approval.add_argument("--seed-name", required=True)
    approval.add_argument("--approver", required=True, help="actual human who reviewed the comparison")
    approval.add_argument("--confirmed-at", required=True)
    approval.add_argument("--approved-sql", type=Path, help="optional complete replay query matching the actual independent SQL; capture/encrypt with confirmation")
    args = parser.parse_args(argv)
    try:
        if args.operation == "confirm":
            target = confirm(args.root, args.report, seed_name=args.seed_name,
                             approver=args.approver, confirmed_at=args.confirmed_at, approved_sql=args.approved_sql)
            print("Confirmed snapshot seed: " + str(target.relative_to(args.root.resolve())))
            if args.approved_sql:
                receipt = strict_json((args.report.parent / ("approval-" + args.seed_name + ".json")).read_text())
                publication = receipt["sql_publication"]
                print("Approved SQL publication: " + publication["status"])
                return publication.get("exit_code", 0)
            return 0
        if args.timeout < 1:
            raise ValueError("timeout must be positive")
        directory, report = verify(args.root, args.notebook, args.method, args.question, strict_json(args.case.read_text()),
            reference_command=args.reference_command, answer_command=args.answer_command,
            judge_command=args.judge_command, timeout=args.timeout)
        # No rows, code, credentials, question or raw executor errors in console output.
        print("Notebook verification: " + report["status"] + "; local report: " + str(directory.relative_to(args.root.resolve()) / "comparison.json"))
        return 0 if report["status"] == "pass" else 2 if report["status"] == "fail" else 3
    except (OSError, ValueError, KeyError) as exc:
        print("verify_notebook: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
