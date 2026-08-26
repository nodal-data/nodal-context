#!/usr/bin/env python3
"""Create, upgrade, or check an ACF analytics-context repository.

This file runs both from a nodal-context source checkout and from the generated
``context-interview`` skill bundle. Both modes consume ``scaffold_manifest.py``.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from scaffold_manifest import ARTIFACTS, IGNORED_NAMES, IGNORED_SUFFIXES, REQUIRED_CONTEXT_MARKER


SCRIPT_ROOT = Path(__file__).resolve().parent
CONTAINER_ROOT = SCRIPT_ROOT.parent
REPOSITORY_MODE = (CONTAINER_ROOT / "skills" / "context-interview" / "SKILL.md").is_file()
SOURCE_ROOT = CONTAINER_ROOT


def _fail(message):
    print(f"scaffold: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def _ignored(path):
    return path.name in IGNORED_NAMES or path.name.endswith(IGNORED_SUFFIXES)


def _source(artifact):
    relative = artifact.root_source if REPOSITORY_MODE else artifact.skill_source
    return SOURCE_ROOT / relative


def _is_within(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _validate_target(target):
    forbidden = SOURCE_ROOT.resolve()
    if _is_within(target, forbidden):
        scope = "tool repository" if REPOSITORY_MODE else "installed skill directory"
        _fail(f"target is inside the {scope}; choose a project sibling such as ../analytics-context")


def _active(mode):
    flag = "fresh" if mode == "fresh" else "upgrade"
    return tuple(a for a in ARTIFACTS if a.target is not None and getattr(a, flag))


def _validate_sources(artifacts):
    missing = [a.skill_source if not REPOSITORY_MODE else a.root_source
               for a in artifacts if not _source(a).exists()]
    if missing:
        where = "tool repository" if REPOSITORY_MODE else "installed skill bundle"
        _fail(f"incomplete {where}; missing: {', '.join(missing)}")


def _copy(source, destination):
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for item in sorted(source.rglob("*")):
            if any(_ignored(part) for part in item.relative_to(source).parents) or _ignored(item):
                continue
            relative = item.relative_to(source)
            output = destination / relative
            if item.is_dir():
                output.mkdir(parents=True, exist_ok=True)
            elif item.is_symlink():
                output.parent.mkdir(parents=True, exist_ok=True)
                if output.exists() or output.is_symlink():
                    output.unlink()
                output.symlink_to(item.readlink())
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, output)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _preserved_paths(artifacts):
    return tuple(dict.fromkeys(path for artifact in artifacts for path in artifact.preserve))


def _copy_artifacts(target, artifacts):
    preserved = {}
    for relative in _preserved_paths(artifacts):
        path = target / relative
        if path.is_file():
            preserved[relative] = (path.read_bytes(), path.stat().st_mode)

    for artifact in artifacts:
        _copy(_source(artifact), target / artifact.target)
        print(f"scaffold: copied {artifact.target}")

    for relative, (content, mode) in preserved.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(mode)
        print(f"scaffold: preserved existing {relative}")


def _expected_destinations(artifacts):
    expected = set()
    for artifact in artifacts:
        source = _source(artifact)
        destination = Path(artifact.target)
        if source.is_file() or source.is_symlink():
            expected.add(destination)
            continue
        for item in source.rglob("*"):
            if item.is_dir() or _ignored(item) or any(_ignored(p) for p in item.relative_to(source).parents):
                continue
            expected.add(destination / item.relative_to(source))
    return sorted(expected, key=str)


def self_check(target):
    """Check manifest destinations and executable imports; return problem count."""
    artifacts = tuple(a for a in ARTIFACTS if a.target is not None and (a.fresh or a.upgrade))
    _validate_sources(artifacts)
    problems = [f"missing {path}" for path in _expected_destinations(artifacts)
                if not (target / path).exists()]
    if not (target / REQUIRED_CONTEXT_MARKER).is_file():
        marker_problem = f"missing {REQUIRED_CONTEXT_MARKER}"
        if marker_problem not in problems:
            problems.append(marker_problem)

    if not problems:
        result = subprocess.run(
            [sys.executable, "-B", "-c", "import eval_harness.run"],
            cwd=target,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            problems.append(f"`import eval_harness.run` failed: {result.stderr.strip()}")

    validator = target / ".ci" / "validate.py"
    if not problems and validator.is_file():
        result = subprocess.run(
            [sys.executable, "-B", str(validator)], cwd=target, capture_output=True, text=True
        )
        if result.returncode == 0:
            print("scaffold: validate.py OK")
        elif "missing dependency" in result.stderr:
            print("scaffold: WARN: schema validation dependencies are unavailable")
        else:
            problems.append(
                f"`python .ci/validate.py` failed (exit {result.returncode}):\n"
                f"{result.stdout.strip()}\n{result.stderr.strip()}"
            )

    if problems:
        print(f"scaffold: self-check FAILED — {len(problems)} problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
    else:
        print(f"scaffold: self-check OK — {target} matches the artifact manifest")
    return len(problems)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="analytics-context repository destination")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--upgrade", action="store_true", help="refresh support artifacts only")
    mode.add_argument("--check", action="store_true", help="check without writing")
    args = parser.parse_args(argv)

    target = Path(args.target).expanduser().resolve()
    _validate_target(target)
    if args.check:
        return 1 if self_check(target) else 0

    selected_mode = "upgrade" if args.upgrade else "fresh"
    artifacts = _active(selected_mode)
    _validate_sources(artifacts)

    marker = target / REQUIRED_CONTEXT_MARKER
    if args.upgrade and not marker.is_file():
        _fail(f"{target} is not a context repo (missing {REQUIRED_CONTEXT_MARKER})")
    if not args.upgrade and marker.exists():
        _fail(f"{target} already contains a context repo; use --upgrade")

    target.mkdir(parents=True, exist_ok=True)
    _copy_artifacts(target, artifacts)
    if self_check(target):
        return 1

    print("scaffold: done; continue from this repo's SPEC.md, schemas/, scripts/, and eval_harness/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
