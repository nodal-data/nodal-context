#!/usr/bin/env python3
"""Explicit capture/encrypt/decrypt/probe of approved SQL. Never prints SQL or keys."""
import argparse
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE if (BASE / "acf_runtime").is_dir() else BASE / "payload"))
from acf_runtime import load_context
from acf_runtime.verified import VerifiedSQL, VerificationError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["capture", "encrypt", "decrypt", "probe"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--file", help="repo-relative evals/verified/<name>.sql")
    selection.add_argument("--seed", help="seed ID or evals/seeds/<name>.seed.yaml")
    parser.add_argument("--identity", type=Path, help="customer identity filename, never private-key text")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--approved-input", type=Path, help="capture only: human-approved local SQL file")
    parser.add_argument("--check-decryption", action="store_true", help="probe only: explicitly test decryptability without saving plaintext")
    args = parser.parse_args(argv)
    try:
        manager = VerifiedSQL(args.root, identity=args.identity)
        query = args.file
        identifier = args.seed or (Path(query).name if query else "selected-file")
        if args.seed:
            registry = load_context(args.root)
            if registry.errors:
                raise VerificationError("invalid_context")
            selection = args.seed.removeprefix("seed:").removeprefix("evals/seeds/")
            node = registry.nodes.get("seed:" + selection)
            if not node or not node.data.get("verified_query_file"):
                raise VerificationError("seed_has_no_verified_query_pointer")
            query = node.data["verified_query_file"]
            identifier = node.id
        if args.operation == "capture":
            if not args.approved_input:
                raise VerificationError("capture_requires_approved_input")
            result = manager.capture(query, args.approved_input.read_bytes(), overwrite=args.overwrite)
        elif args.operation == "probe":
            result = manager.probe(query, decrypt=args.check_decryption)
        else:
            result = getattr(manager, args.operation)(query, overwrite=args.overwrite)
        print(json.dumps({"id": identifier, **result}))
        return result.get("exit_code", 0)
    except VerificationError as exc:
        print(json.dumps({"status": "error", "category": exc.category}), file=sys.stderr)
        return exc.code
    except OSError:
        print(json.dumps({"status": "error", "category": "verification_io_error"}), file=sys.stderr)
        return 8


if __name__ == "__main__":
    raise SystemExit(main())
