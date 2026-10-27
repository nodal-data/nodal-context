#!/usr/bin/env python3
"""Local simulation bookkeeping; never reads the analyst brief or starts an agent."""
import argparse
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE if (BASE / "acf_runtime").is_dir() else BASE / "payload"))
from acf_runtime.simulation import handoff, record, pending, attest_confirmation, check_output, summarize


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["handoff", "record", "pending", "attest-human", "check", "summary"])
    parser.add_argument("--marker", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="context repo / handoff destination")
    parser.add_argument("--id", help="stable question ID or canonical object ID for human attestation")
    parser.add_argument("--stage")
    parser.add_argument("--question-file", type=Path)
    parser.add_argument("--reply-file", type=Path)
    parser.add_argument("--source", choices=["simulated", "human"], default="simulated")
    parser.add_argument("--reviewer")
    parser.add_argument("--require-content", action="store_true", help="check actual draft output and logged exchange")
    args = parser.parse_args(argv)
    try:
        if args.operation == "handoff":
            result = {"marker": str(handoff(args.marker, args.root))}
        elif args.operation == "record":
            if not all((args.id, args.stage, args.question_file, args.reply_file)):
                parser.error("record requires --id, --stage, --question-file and --reply-file")
            result = record(args.marker, identifier=args.id, stage=args.stage,
                question=args.question_file.read_text(), reply=args.reply_file.read_text(),
                source=args.source, reviewer=args.reviewer)
        elif args.operation == "pending":
            result = {"pending": pending(args.marker)}
        elif args.operation == "summary":
            result = summarize(args.root, args.marker)
        elif args.operation == "attest-human":
            result = attest_confirmation(args.marker, args.root, args.id, args.reviewer)
        else:
            problems = check_output(args.root, args.marker, require_content=args.require_content)
            result = {"status": "failed" if problems else "valid_simulation", "problems": problems}
            print(json.dumps(result, indent=2))
            return 1 if problems else 0
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"simulated_analyst: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
