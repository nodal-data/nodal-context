#!/usr/bin/env python3
"""Fresh BYO-key seed checks; --restore explicitly persists eligible seed statuses."""
import argparse
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE if (BASE / "acf_runtime").is_dir() else BASE / "payload"))
from acf_runtime.regrade import run_regrade
from eval_harness.client import MODEL


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--approved-ref", default="HEAD", help="search this Git revision's seed history for the latest human approval")
    parser.add_argument("--seed", action="append", help="canonical seed ID, e.g. seed:orders.seed.yaml")
    parser.add_argument("--restore", action="store_true", help="restore eligible seeds after fresh passing checks in this invocation")
    parser.add_argument("--model", default=MODEL)
    args = parser.parse_args(argv)
    try:
        report = run_regrade(args.root, approved_ref=args.approved_ref, seed_ids=args.seed,
                             restore=args.restore, model=args.model)
    except (ValueError, OSError):
        print(json.dumps({"status": "error", "category": "invalid_or_changed_regrade_context"}), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    statuses = {r["status"] for r in report["results"]}
    pending = any(r["category"] == "dependency_review_pending" for r in report["results"])
    return 1 if "fail" in statuses else 3 if "skipped" in statuses or pending else 0


if __name__ == "__main__":
    raise SystemExit(main())
