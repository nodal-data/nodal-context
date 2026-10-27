#!/usr/bin/env python3
"""Route PR evaluation through base/head context graphs; stdout is GITHUB_OUTPUT."""
import argparse
import os
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acf_runtime.impact import all_domains, path_impact, revisions, snapshot


def _warn(message):
    print("changed_domains: " + message, file=sys.stderr)


list_all_domains = all_domains


def domains_for_changed(files, root=".", base_root=None):
    result = path_impact(root, files, base_root=base_root)
    for reason in result["reasons"]:
        _warn(reason)
    return result["domains"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="PR base revision; compared from its merge base with head")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--root", default=".")
    parser.add_argument("--changed-files", nargs="*", help="explicit paths; requires --base-root for precise routing")
    parser.add_argument("--base-root", help="explicit base context directory for offline testing")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.changed_files is not None:
            result = path_impact(root, args.changed_files, base_root=args.base_root)
        else:
            base = args.base or ("origin/" + os.environ["GITHUB_BASE_REF"] if os.environ.get("GITHUB_BASE_REF") else "origin/main")
            try:
                before, after, paths = revisions(root, base, args.head)
            except ValueError:
                if args.base or os.environ.get("GITHUB_BASE_REF"):
                    raise
                before, after, paths = revisions(root, "main", args.head)
            with snapshot(root, before) as base_root, snapshot(root, after) as head_root:
                schema = root / "schemas" if (root / "schemas").is_dir() else Path(__file__).resolve().parents[1] / "schemas"
                result = path_impact(head_root, paths, base_root=base_root, schemas=schema)
        for reason in result["reasons"]:
            _warn(reason)
        domains = result["domains"]
    except (OSError, ValueError, ImportError) as exc:
        _warn(f"{exc}; evaluating all available domains")
        domains = all_domains(root)
    if any(not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]*", domain) for domain in domains):
        _warn("domain names must be slugs before they can be emitted as workflow output")
        return 1
    _warn(f"selected {len(domains)} domain(s): " + (", ".join(domains) or "(none)"))
    print("domains=" + ",".join(domains))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
