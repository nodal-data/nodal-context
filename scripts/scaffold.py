#!/usr/bin/env python3
"""Scaffold (or upgrade) an analytics-context repo from this tool repo.

This script is the single source of truth for what a generated context repo
contains. `skills/context-interview/references/repo-scaffold.md` describes the
scaffold; this script performs it — change them together.

  python3 scripts/scaffold.py <target-dir>            # fresh scaffold (Stage 0)
  python3 scripts/scaffold.py --upgrade <target-dir>  # refresh support files only
  python3 scripts/scaffold.py --check <target-dir>    # self-check an existing repo

Fresh mode copies `template/` (the authorable content) plus the CI support set.
Upgrade mode refreshes ONLY the support set — it never touches authored content
(`company/`, `domains/`, `entities/`, `evals/`, `context.config.yaml`, README …)
and never touches an existing `.ci/lineage-baseline.json`.

The support set exists because the shipped workflows execute from the context
repo root and have no other way to find their code:
  .github/workflows/   validate-context, eval-delta, context-drift
  .ci/*.py             the scripts those workflows run
  schemas/*.json       ACF JSON Schemas (validate.py resolves ./schemas)
  scripts/dbt_extract.py  imported by .ci/drift.py
  scripts/query_history_extract.py  Stage-0 query-history miner; re-mining (and
                       the upcoming reconciliation mode) runs from the context
                       repo root. No shipped workflow imports it yet.
  eval_harness/        vendored — eval-delta runs `python -m eval_harness.run`
                       from the repo root; there is no pip package.

Every mode ends with a self-check; a non-zero exit names the missing piece.
Stdlib only — safe to run before any pip install.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent.parent

IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")

# The support set: (source relative to the tool repo, copied on upgrade too).
# Directories are copied recursively with IGNORE applied.
SUPPORT_SET = [
    ".github/workflows",
    ".ci",
    "schemas",
    "scripts/dbt_extract.py",
    "scripts/query_history_extract.py",
    "eval_harness",
]

# Never overwrite these target paths (created per-context-repo, not shipped).
PRESERVE = [".ci/lineage-baseline.json"]

WORKFLOWS = ["validate-context.yml", "eval-delta.yml", "context-drift.yml"]


def _fail(msg):
    print(f"scaffold: ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _copy(src: Path, dst: Path):
    if src.is_dir():
        shutil.copytree(src, dst, ignore=IGNORE, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def copy_support_set(target: Path):
    preserved = {}
    for rel in PRESERVE:
        p = target / rel
        if p.exists():
            preserved[rel] = p.read_bytes()
    for rel in SUPPORT_SET:
        src = TOOL_ROOT / rel
        if not src.exists():
            _fail(f"tool repo is missing {rel} — is this a full nodal-context clone?")
        _copy(src, target / rel)
        print(f"scaffold: copied {rel}")
    for rel, blob in preserved.items():
        (target / rel).write_bytes(blob)
        print(f"scaffold: preserved existing {rel}")


def copy_template(target: Path):
    src = TOOL_ROOT / "template"
    if not src.is_dir():
        _fail("tool repo is missing template/")
    shutil.copytree(src, target, ignore=IGNORE, dirs_exist_ok=True)
    print("scaffold: copied template/ (company/, domains/, entities/, evals/, "
          "README, CLAUDE.md, AGENTS.md, .claude/skills/, context.config.yaml)")


def self_check(target: Path) -> int:
    """Verify the scaffold is complete and functional. Returns count of problems."""
    problems = []

    required = ["context.config.yaml", "scripts/dbt_extract.py",
                "scripts/query_history_extract.py", "eval_harness/run.py"]
    required += [f".github/workflows/{w}" for w in WORKFLOWS]
    required += [f".ci/{p.name}" for p in sorted((TOOL_ROOT / ".ci").glob("*.py"))]
    required += [f"schemas/{p.name}" for p in sorted((TOOL_ROOT / "schemas").glob("*.json"))]
    for rel in required:
        if not (target / rel).exists():
            problems.append(f"missing {rel}")

    r = subprocess.run([sys.executable, "-B", "-c", "import eval_harness.run"],
                       cwd=target, capture_output=True, text=True)
    if r.returncode != 0:
        problems.append(f"`import eval_harness.run` failed:\n{r.stderr.strip()}")

    r = subprocess.run([sys.executable, "-B", ".ci/validate.py"],
                       cwd=target, capture_output=True, text=True)
    if r.returncode == 0:
        print("scaffold: validate.py OK")
    elif "missing dependency" in r.stderr:
        # Environment gap, not a scaffold gap — CI installs these itself.
        print("scaffold: WARN: skipped schema validation "
              "(pip install jsonschema pyyaml to run it locally; CI runs it regardless)")
    else:
        problems.append(f"`python .ci/validate.py` failed (exit {r.returncode}):\n"
                        f"{r.stdout.strip()}\n{r.stderr.strip()}")

    if problems:
        print(f"scaffold: self-check FAILED — {len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
    else:
        print(f"scaffold: self-check OK — {target} has the full support set")
    return len(problems)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="the context repo directory")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--upgrade", action="store_true",
                      help="refresh the support set only; never touch authored content")
    mode.add_argument("--check", action="store_true", help="self-check only, copy nothing")
    args = ap.parse_args(argv)

    target = Path(args.target).resolve()
    if target == TOOL_ROOT or TOOL_ROOT in target.parents:
        _fail("target is inside the tool repo — scaffold into a sibling directory "
              "(the tool repo is never authored into)")

    if args.check:
        return 1 if self_check(target) else 0

    if args.upgrade:
        if not (target / "context.config.yaml").exists():
            _fail(f"{target} does not look like a context repo "
                  "(no context.config.yaml); for a new repo run without --upgrade")
        copy_support_set(target)
    else:
        if (target / "context.config.yaml").exists():
            _fail(f"{target} already contains a context repo — use --upgrade to "
                  "refresh its support files without touching authored content")
        target.mkdir(parents=True, exist_ok=True)
        copy_template(target)
        copy_support_set(target)

    if self_check(target):
        return 1

    print(f"""
scaffold: done. Next steps:
  - fresh repo: `git init -b main` + initial commit (the interview skill does this)
  - once a dbt manifest is available, create the drift baseline once and commit it:
      python .ci/drift.py --update-baseline --manifest <source_id>=<path/to/manifest.json>
  - CI needs repo secrets to do more than validate: ANTHROPIC_API_KEY (eval delta),
    DBT_REPO_TOKEN (drift manifest clone fallback)""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
