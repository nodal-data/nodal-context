#!/usr/bin/env python3
"""Preview, explicitly apply, or resume human-reviewed observed-demand edits."""
import argparse
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE if (BASE / "acf_runtime").is_dir() else BASE / "payload"))
from acf_runtime.observed_review import apply, list_pending, prepare
from eval_harness.execution import strict_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["list", "prepare", "apply", "resume"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--observation", help="pending observation ID")
    parser.add_argument("--reviewer", help="human reviewing the interpretation, never a simulator")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--seed", help="canonical seed ID for an equivalent variant")
    choice.add_argument("--changes", type=Path, help="local JSON array of {path,content} draft edits")
    choice.add_argument("--decline", action="store_true", help="dismiss without creating a seed")
    parser.add_argument("--ir", type=Path, help="local JSON reviewed IR; required with --seed")
    parser.add_argument("--domain", help="reviewed owning domain when absent from the queue")
    parser.add_argument("--disposition", default="drafted", help="reviewed disposition or dismissal reason")
    parser.add_argument("--proposal", help="repo-relative .nodal/observed/proposals/<id>.json")
    parser.add_argument("--sha256", help="exact digest returned at preparation, after reviewing the proposal")
    args = parser.parse_args(argv)
    try:
        if args.operation == "list":
            result = {"pending": list_pending(args.root)}
        elif args.operation == "prepare":
            if not args.observation or not args.reviewer or not (args.seed or args.changes or args.decline):
                parser.error("prepare requires --observation, --reviewer and --seed, --changes or --decline")
            if args.seed and not args.ir:
                parser.error("--seed requires --ir")
            if args.decline and args.disposition == "drafted":
                parser.error("dismissal requires an explicit --disposition reason")
            result = prepare(args.root, args.observation, reviewer=args.reviewer,
                changes=strict_json(args.changes.read_text()) if args.changes else [],
                disposition=args.disposition, variant={"seed": args.seed,
                "ir": strict_json(args.ir.read_text())} if args.seed else None,
                reviewed_ir=strict_json(args.ir.read_text()) if args.ir else None, domain=args.domain)
        else:
            if not args.proposal or not args.sha256 or not args.reviewer:
                parser.error("apply/resume requires --proposal, --sha256 and --reviewer after human review")
            result = apply(args.root, args.proposal, reviewer=args.reviewer, sha256=args.sha256)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"review_observed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
