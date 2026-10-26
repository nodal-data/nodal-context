#!/usr/bin/env python3
"""Print read-only, demand-weighted ACF coverage. Never decrypts implicitly."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acf_runtime import load_context
from acf_runtime.loader import Schemas
from acf_runtime.observed import read_queue
from acf_runtime.verified import VerifiedSQL, VerificationError, contained
from acf_runtime.regression import seed_fingerprint
from acf_runtime.notebook_verification import checked_evidence as notebook_evidence
from eval_harness.execution import digest, strict_json
from eval_harness.coverage import build_report, render


def evidence(root, seed, config, *, manager=None, check_decryption=False, checked=None, registry=None, notebook_run=None):
    root = Path(root).resolve()
    expected = seed["expected"]
    result = {"state": "unverified", "verified": False}
    if expected["kind"] == "value_at_snapshot":
        result.update(state="snapshot_evidence_recorded", verified=False,
                      source_revision_checked=False)
    if seed.get("verified_query_file"):
        manager = manager or VerifiedSQL(root, config=config)
        availability = manager.probe(seed["verified_query_file"], decrypt=check_decryption)
        result["availability"] = availability
        if availability["plaintext_present"]:
            result["query"] = "plaintext_available"
            # Availability establishes replay capability, not checked result fidelity.
            if result["state"] == "unverified":
                result["state"] = "approved_query_available"
        elif availability["ciphertext_present"]:
            result["query"] = ("encrypted_decryptable" if availability["decryptability"] == "decryptable"
                               else "encrypted_present_decryption_unchecked" if not check_decryption
                               else "encrypted_decryption_unavailable")
            if result["state"] == "unverified":
                result["state"] = "decryptable" if availability["decryptability"] == "decryptable" else "unchecked_without_key"
        else:
            result["query"] = "missing"
            result["stale_reasons"] = ["verified_file_missing"]
        if checked and registry:
            plain, cipher, _ = manager.paths(seed["verified_query_file"])
            artifact = cipher if manager.backend != "none" else plain
            node = registry.nodes[seed["id"]]
            current = (artifact.is_file() and checked.get("fingerprint") == seed_fingerprint(registry, node)
                       and checked.get("artifact_hash") == digest(artifact.read_bytes().hex()))
            if not current:
                result.update(state="stale_verification", verified=False, stale_reasons=["verification_revision_changed"])
            elif checked.get("status") in ("pass", "fail"):
                result.update(state="checked_" + checked["status"], verified=checked["status"] == "pass",
                              checked_at=checked.get("checked_at"))
                if checked["status"] == "fail":
                    result["stale_reasons"] = ["regression_failed"]
            else:
                result["regression"] = "skipped"
    # Notebook source/context freshness is independent of whether SQL replay
    # also exists. A passing SQL regression cannot hide changed notebook evidence.
    if notebook_run and registry:
        notebook = notebook_evidence(root, seed, registry, notebook_run)
        if notebook["verified"] and result["state"] in ("checked_fail", "stale_verification"):
            result.update(notebook=notebook["state"], source_revision_checked=notebook["source_revision_checked"])
        else:
            result.update(notebook)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--check-decryption", action="store_true", help="explicitly probe ciphertext with customer keys; never execute SQL")
    parser.add_argument("--identity", type=Path, help="identity filename for an explicit decryption probe")
    parser.add_argument("--regression-run", help="repo-relative .nodal/regressions/<run>/evidence.json to check against current revisions")
    parser.add_argument("--notebook-run", action="append", default=[], metavar="SEED=REPORT",
                        help="explicitly recheck a confirmed notebook seed's local comparison/approval and source file; no execution")
    args = parser.parse_args(argv)
    try:
        root = Path(args.root).resolve()
        registry = load_context(root)
        notebook_runs = {}
        for binding in args.notebook_run:
            name, separator, path = binding.partition("=")
            key = "seed:" + name.removeprefix("seed:").removeprefix("evals/seeds/")
            node = registry.nodes.get(key)
            if (not separator or not path or key in notebook_runs or not node or node.kind != "evalseed"
                    or node.data.get("provenance") != "notebook"):
                raise ValueError("--notebook-run requires a unique notebook seed ID and local report path")
            contained(root, path, ".nodal/notebook-runs")
            notebook_runs[key] = path
        if args.identity and not args.check_decryption:
            raise ValueError("--identity requires --check-decryption")
        manager = VerifiedSQL(root, config=registry.config, identity=args.identity) if not registry.errors else None
        checked = {}
        if args.regression_run:
            path = contained(root, args.regression_run, ".nodal/regressions")
            checked = strict_json(path.read_text())
            if not isinstance(checked, dict) or not all(isinstance(v, dict) for v in checked.values()):
                raise ValueError("invalid regression evidence")
        schema_dir = root / "schemas" if (root / "schemas").is_dir() else Path(__file__).resolve().parents[1] / "schemas"
        queue = read_queue(root, Schemas(schema_dir), registry)
        for d in registry.diagnostics:
            print(str(d), file=sys.stderr)
        seeds = registry.seed_records()
        tokens = registry.config.get("time_tokens", {})
        result = build_report(registry.definitions(), seeds, queue,
                              tokens.get("calendar", []) + tokens.get("fiscal", []),
                              {s["id"]: evidence(root, s, registry.config, manager=manager,
                                   check_decryption=args.check_decryption, checked=checked.get(s["id"]), registry=registry,
                                   notebook_run=notebook_runs.get(s["id"]))
                               for s in seeds} if not registry.errors else {},
                              all_cells=args.all)
        result["governance"] = registry.governance
        result["diagnostics"] = [vars(d) for d in registry.diagnostics]
        print(json.dumps(result, indent=2) if args.json else render(result), end="\n")
        return 1 if registry.errors else 0
    except (ValueError, OSError) as exc:
        print(f"coverage: ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
