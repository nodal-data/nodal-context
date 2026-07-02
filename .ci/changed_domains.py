#!/usr/bin/env python3
"""Emit the set of domains whose context changed in a PR, for the eval-delta workflow.

`eval-delta.yml` runs this and appends stdout to $GITHUB_OUTPUT:

    python .ci/changed_domains.py >> "$GITHUB_OUTPUT"

so the ONLY thing printed to stdout is one line:

    domains=<comma-separated,sorted,unique>

which is consumed as `--domains "${{ steps.changed.outputs.domains }}"`. All diagnostics
go to stderr so they don't pollute the output value.

Mapping rules (paths are repo-root-relative, as git reports them):
  • domains/<name>/…            -> domain <name>
  • <root>/evals/…/*.seed.yaml  -> the seed's own `domain:` field
  • entities/…  (shared, top-level, not under a domain)  -> CROSS-CUTTING
  • a seed whose domain can't be read                    -> CROSS-CUTTING
A cross-cutting change conservatively expands to ALL domains (a shared entity or an
unresolvable seed can affect any domain). `_`-prefixed dirs (e.g. _domain-template)
are ignored.

Change set comes from `git diff --name-only <base>...HEAD`. Base ref: --base, else
$GITHUB_BASE_REF (as origin/<ref>), else origin/main, else main. If the diff can't be
computed (base not fetched, etc.) it fails SAFE → all domains.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path


def _warn(msg):
    print(f"changed_domains: {msg}", file=sys.stderr)


def list_all_domains(root="."):
    d = Path(root) / "domains"
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir() and not p.name.startswith("_"))


def _seed_domain(path):
    """Read a seed's `domain:` field. None if unreadable / pyyaml missing."""
    try:
        import yaml
    except ImportError:
        return None
    try:
        doc = yaml.safe_load(Path(path).read_text()) or {}
        return doc.get("domain") if isinstance(doc, dict) else None
    except Exception:
        return None


def domains_for_changed(files, root="."):
    """Map a list of changed repo-relative paths to the domain set to evaluate."""
    domains, cross = set(), False
    for f in files:
        parts = Path(f).parts
        if len(parts) >= 2 and parts[0] == "domains" and not parts[1].startswith("_"):
            domains.add(parts[1])
        elif parts and parts[0] == "entities":          # shared, cross-domain entities
            cross = True
        elif f.endswith(".seed.yaml"):
            d = _seed_domain(Path(root) / f)
            if d:
                domains.add(d)
            else:
                _warn(f"could not resolve domain for seed {f}; treating as cross-cutting")
                cross = True
    if cross:
        return list_all_domains(root)
    return sorted(domains)


def _resolve_base(arg):
    if arg:
        return arg
    base_ref = os.environ.get("GITHUB_BASE_REF")
    if base_ref:
        return f"origin/{base_ref}"
    return None  # try origin/main then main


def changed_files_via_git(base):
    """`git diff --name-only base...HEAD`. Fetches base on demand. None on failure."""
    candidates = [base] if base else ["origin/main", "main"]
    for ref in candidates:
        try:
            out = subprocess.run(
                ["git", "diff", "--name-only", f"{ref}...HEAD"],
                check=True, capture_output=True, text=True,
            )
            return [l for l in out.stdout.splitlines() if l.strip()]
        except subprocess.CalledProcessError:
            # base may not be fetched (shallow checkout) — try to fetch it once
            short = ref.split("/", 1)[1] if ref.startswith("origin/") else ref
            try:
                subprocess.run(["git", "fetch", "--no-tags", "--depth=1", "origin", short],
                               check=True, capture_output=True, text=True)
                out = subprocess.run(
                    ["git", "diff", "--name-only", f"{ref}...HEAD"],
                    check=True, capture_output=True, text=True,
                )
                return [l for l in out.stdout.splitlines() if l.strip()]
            except subprocess.CalledProcessError as e:
                _warn(f"git diff against {ref} failed: "
                      f"{(e.stderr or '').strip().splitlines()[-1] if e.stderr else e}")
                continue
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="base git ref to diff against (e.g. origin/main)")
    ap.add_argument("--root", default=".", help="repo root (default: .)")
    ap.add_argument("--changed-files", nargs="*",
                    help="bypass git; supply changed paths directly (for testing)")
    args = ap.parse_args(argv)

    if args.changed_files is not None:
        files = args.changed_files
    else:
        files = changed_files_via_git(_resolve_base(args.base))
        if files is None:
            _warn("could not determine changed files; failing SAFE to all domains")
            print(f"domains={','.join(list_all_domains(args.root))}")
            return 0

    domains = domains_for_changed(files, args.root)
    _warn(f"{len(files)} changed file(s) -> {len(domains)} domain(s): "
          f"{', '.join(domains) or '(none)'}")
    print(f"domains={','.join(domains)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
