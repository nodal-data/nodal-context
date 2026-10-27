#!/usr/bin/env python3
"""Customer-run approved-query regression. Stdout contains sanitized statuses only."""
import argparse
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE if (BASE / "acf_runtime").is_dir() else BASE / "payload"))
from acf_runtime.regression import run_regression
from acf_runtime.verified import VerificationError
from eval_harness.execution import strict_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--executor", type=strict_json, help="trusted customer JSON argv command; absent = explicit skip")
    parser.add_argument("--judge", type=strict_json, help="optional trusted local semantic judge argv command")
    parser.add_argument("--identity", type=Path, help="customer identity filename, never key text")
    parser.add_argument("--seed", action="append", help="explicit seed ID/path; repeat to select several")
    parser.add_argument("--parameters", type=Path, help="local JSON mapping seed IDs to bound parameter objects")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--branch-test", action="store_true", help="test proposed context; never grants approval")
    args = parser.parse_args(argv)
    try:
        if args.timeout < 1:
            raise VerificationError("timeout_must_be_positive")
        _, report = run_regression(args.root, executor=args.executor, judge=args.judge, identity=args.identity,
            seed_ids=args.seed, parameters=strict_json(args.parameters.read_text()) if args.parameters else None,
            timeout=args.timeout, branch_test=True if args.branch_test else None)
        print(json.dumps(report, indent=2))
        statuses = [r["status"] for r in report["results"]]
        return 1 if "fail" in statuses else 3 if not statuses or "skipped" in statuses else 0
    except VerificationError as exc:
        print(json.dumps({"status": "error", "category": exc.category}), file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print(json.dumps({"status": "error", "category": "regression_configuration_error"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
