#!/usr/bin/env python3
"""Statically draft an ACF method from a notebook; never execute notebook cells."""
import argparse
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE if (BASE / "acf_runtime").is_dir() else BASE / "payload"))
from acf_runtime.loader import load_context
from acf_runtime.notebooks import draft_notebook, render_method


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--name", required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--source-path", help="notebook path in its source repository")
    parser.add_argument("--repo")
    parser.add_argument("--ref", help="actual pinned source revision; defaults to content hash")
    parser.add_argument("--dialect", help="SQL dialect for static parsing")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        registry = load_context(root)
        from acf_runtime.governance import require_working_branch
        require_working_branch(root, registry.config.get("approval_branch", "main"))
        if registry.errors:
            raise ValueError("context must validate before importing a method")
        data, body, report = draft_notebook(args.notebook, name=args.name, domain=args.domain,
            registry=registry, source_path=args.source_path, repo=args.repo, ref=args.ref, dialect=args.dialect)
        destination = root / "methods" / (args.name + ".md")
        local = root / ".nodal" / "imports" / (args.name + ".json")
        if not destination.resolve().is_relative_to(root) or not local.resolve().is_relative_to(root):
            raise ValueError("output path escapes context root")
        if destination.exists() or local.exists():
            raise ValueError("draft/report already exists; review it or choose a new method name")
        destination.parent.mkdir(parents=True, exist_ok=True)
        local.parent.mkdir(parents=True, exist_ok=True)
        with local.open("x") as stream:
            local.chmod(0o600)
            stream.write(json.dumps(report, indent=2) + "\n")
        try:
            with destination.open("x") as stream:
                stream.write(render_method(data, body))
        except Exception:
            local.unlink()
            raise
        print(f"Draft: {destination.relative_to(root)}; review report: {local.relative_to(root)}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"import_notebook: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
