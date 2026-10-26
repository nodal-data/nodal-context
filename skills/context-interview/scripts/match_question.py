#!/usr/bin/env python3
"""Read-only ACF question matching; explicit --question enables BYO-key extraction."""
import argparse
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE if (BASE / "acf_runtime").is_dir() else BASE / "payload"))
from acf_runtime import load_context
from eval_harness import client
from eval_harness.execution import strict_json
from acf_runtime.matching import match_registry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--domain", required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--ir", type=Path, help="extracted or reviewed JSON IR; no model call")
    selection.add_argument("--question", help="extract IR using the configured BYO-key model")
    parser.add_argument("--candidate", action="append", default=[], help="viable canonical candidate; never a probability threshold")
    parser.add_argument("--exclude", action="append", default=[], help="seed ID to hold out, including its variants")
    parser.add_argument("--model", default=client.MODEL)
    parser.add_argument("--branch-test", action="store_true", help="test proposed context; never grants approval")
    args = parser.parse_args(argv)
    try:
        registry = load_context(args.root, branch_test=True if args.branch_test else None)
        if registry.errors:
            raise ValueError("context must validate before matching")
        if args.domain not in registry.domains:
            raise ValueError("unknown domain")
        extracted = {"ir": strict_json(args.ir.read_text()), "candidates": args.candidate} if args.ir else None
        if extracted is None:
            if not client.available():
                raise ValueError("extraction is unavailable; provide reviewed --ir or configure the BYO-key client")
            # Seed questions, variants, expected answers and verified SQL are never sent.
            extracted = client.extract_ir(args.question, args.domain, registry.definitions(), model=args.model)
            extracted["candidates"] = [*extracted.get("candidates", []), *args.candidate]
        result = match_registry(registry, extracted["ir"], args.domain,
            candidates=extracted.get("candidates"), exclude=args.exclude)
        if extracted.get("unresolved_reason"):
            result["unresolved_reason"] = extracted["unresolved_reason"]
        result["governance"] = registry.governance
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"match_question: {exc}", file=sys.stderr)
        return 1
    except Exception:
        # SDK failures may contain private request content or authentication details.
        print("match_question: extraction_failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
