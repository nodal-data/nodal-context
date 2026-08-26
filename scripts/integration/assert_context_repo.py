#!/usr/bin/env python3
"""Assert that an interview produced a complete, runnable context repository."""

import argparse
import os
import subprocess
import sys
from pathlib import Path


REQUIRED_FILES = (
    "SPEC.md",
    "context.config.yaml",
    ".gitignore",
    ".ci/validate.py",
    ".claude/skills/data-question/SKILL.md",
    ".github/workflows/validate-context.yml",
    "eval_harness/__init__.py",
    "eval_harness/run.py",
    "evals/captures/.gitkeep",
    "evals/playbooks/.gitkeep",
    "evals/runs/.gitkeep",
    "evals/verified/.gitkeep",
    "schemas/config.schema.json",
    "scripts/compile_skill.py",
    "scripts/dbt_extract.py",
    "scripts/query_history_extract.py",
)

EXECUTABLE_FILES = (
    "scripts/dbt_extract.py",
    "scripts/query_history_extract.py",
)


def _run(command, cwd):
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True)


def check_context_repo(target, resume_marker=None):
    """Return human-readable problems found in ``target``."""
    target = Path(target).expanduser().resolve()
    problems = []

    for relative in REQUIRED_FILES:
        path = target / relative
        if not path.is_file():
            problems.append(f"missing {relative}")

    for relative in EXECUTABLE_FILES:
        path = target / relative
        if path.is_file() and not os.access(path, os.X_OK):
            problems.append(f"not executable: {relative}")

    if resume_marker:
        marker = target / resume_marker
        if not marker.is_file():
            problems.append(f"resume marker was removed: {resume_marker}")

    if problems:
        return problems

    imported = _run(
        [sys.executable, "-B", "-c", "import eval_harness.run"],
        target,
    )
    if imported.returncode:
        problems.append(f"eval harness import failed: {imported.stderr.strip()}")

    compiled = _run(
        [sys.executable, "-B", "scripts/compile_skill.py", "--help"],
        target,
    )
    if compiled.returncode:
        problems.append(f"compile_skill.py failed: {compiled.stderr.strip()}")

    validated = _run([sys.executable, "-B", ".ci/validate.py"], target)
    if validated.returncode and "missing dependency" not in validated.stderr:
        detail = "\n".join(
            part for part in (validated.stdout.strip(), validated.stderr.strip()) if part
        )
        problems.append(f"context validation failed (exit {validated.returncode}): {detail}")

    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="generated analytics-context repository")
    parser.add_argument(
        "--resume-marker",
        help="relative marker that must survive a resumed interview",
    )
    args = parser.parse_args(argv)

    problems = check_context_repo(args.target, args.resume_marker)
    if problems:
        print(f"assert_context_repo: FAILED — {len(problems)} problem(s)", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(f"assert_context_repo: OK — {Path(args.target).expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
