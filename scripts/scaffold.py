#!/usr/bin/env python3
"""Create, upgrade, or check an ACF analytics-context repository.

This file runs both from a nodal-context source checkout and from the generated
``context-interview`` skill bundle. Both modes consume ``scaffold_manifest.py``.
"""
import argparse
import difflib
import hashlib
import re
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


def _copy(source, destination, preserved=frozenset()):
    if destination in preserved:
        return
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for item in sorted(source.rglob("*")):
            if any(_ignored(part) for part in item.relative_to(source).parents) or _ignored(item):
                continue
            relative = item.relative_to(source)
            output = destination / relative
            if output in preserved:
                continue
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
    preserved = set()
    for relative in _preserved_paths(artifacts):
        path = target / relative
        if path.exists() or path.is_symlink():
            preserved.add(path)

    for artifact in artifacts:
        _copy(_source(artifact), target / artifact.target, preserved)
        print(f"scaffold: copied {artifact.target}")

    for path in sorted(preserved):
        print(f"scaffold: preserved existing {path.relative_to(target)}")


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


def upgrade_review(target):
    """Report fresh-template differences without replacing authored content.

    The previous installed template is not known. These are current authored
    bytes versus incoming defaults, never an automatically applicable migration.
    """
    from acf_runtime.verified import atomic_private, contained
    lines = ["# Scaffold upgrade: authoring-template review", "",
             "Support files are upgraded separately. Authored files below are preserved.",
             "Compare these incoming defaults with your business-specific content; do not",
             "apply this report as a patch or replace reviewed definitions with template stubs.",
             "No prior template baseline is available: differences may be customer edits,",
             "new template guidance, or both. This report contains private authored text.", ""]
    differences = 0
    for artifact in ARTIFACTS:
        if artifact.target is None or not artifact.fresh or artifact.upgrade:
            continue
        source = _source(artifact)
        files = [source] if source.is_file() else sorted(source.rglob("*"))
        for incoming in files:
            suffix = Path() if source.is_file() else incoming.relative_to(source)
            if not incoming.is_file() or any(_ignored(part) for part in (suffix, *suffix.parents)):
                continue
            relative = Path(artifact.target) / suffix
            current = target / relative
            cursor = target
            symlink = False
            for part in relative.parts:
                cursor /= part
                symlink = symlink or cursor.is_symlink()
            if symlink or (current.exists() and not current.is_file()):
                differences += 1
                lines.extend([f"## {relative.as_posix()}", "",
                              "Non-regular or symlink path preserved without reading it.", ""])
                continue
            incoming_bytes = incoming.read_bytes()
            current_bytes = current.read_bytes() if current.exists() else b""
            if current.exists() and current_bytes == incoming_bytes:
                continue
            differences += 1
            state = "Differs from incoming template" if current.exists() else "Absent; not created by upgrade"
            lines.extend([f"## {relative.as_posix()}", "", state + ".", ""])
            try:
                before = current_bytes.decode("utf-8").splitlines(keepends=True)
                after = incoming_bytes.decode("utf-8").splitlines(keepends=True)
            except UnicodeDecodeError:
                lines.extend(["Non-UTF-8 file preserved; inspect it locally.", ""])
                continue
            diff = "".join(difflib.unified_diff(before, after,
                fromfile="authored/" + relative.as_posix(), tofile="incoming-template/" + relative.as_posix()))
            # Fences in authored Markdown must not terminate the report's block.
            fence = "`" * (max((len(s) for s in re.findall(r'`+', diff)), default=0) + 3)
            lines.extend([fence + "diff", diff.rstrip("\n"), fence, ""])
    if not differences:
        lines.extend(["No authoring-template differences found.", ""])
    payload = "\n".join(lines).encode("utf-8")
    fingerprint = hashlib.sha256(payload).hexdigest()[:20]
    report = contained(target, f".nodal/migrations/scaffold-{fingerprint}.md", ".nodal/migrations")
    atomic_private(report, payload)
    print(f"scaffold: private template review ({differences} differences): {report}")
    return report


def self_check(target, fresh=False):
    """Check manifest destinations and executable imports; return problem count."""
    artifacts = tuple(a for a in ARTIFACTS if a.target is not None and (a.fresh or a.upgrade))
    _validate_sources(artifacts)
    # Authored directory templates and .gitkeep files may be replaced/removed as
    # a repo is populated. Support tooling must always remain complete.
    required = artifacts if fresh else tuple(a for a in artifacts if a.upgrade or _source(a).is_file())
    problems = [f"missing {path}" for path in _expected_destinations(required)
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
    parser.add_argument("--sim-marker", type=Path, help="explicit existing local simulation marker to hand off")
    args = parser.parse_args(argv)

    target = Path(args.target).expanduser().resolve()
    _validate_target(target)
    if args.check:
        if args.sim_marker:
            _fail("--check cannot write a simulation marker")
        return 1 if self_check(target) else 0

    selected_mode = "upgrade" if args.upgrade else "fresh"
    artifacts = _active(selected_mode)
    _validate_sources(artifacts)

    marker = target / REQUIRED_CONTEXT_MARKER
    if args.upgrade and not marker.is_file():
        _fail(f"{target} is not a context repo (missing {REQUIRED_CONTEXT_MARKER})")
    if args.upgrade:
        try:
            import yaml
        except ImportError:
            _fail("missing dependency: install pyyaml before checking the context version")
        try:
            config = yaml.safe_load(marker.read_text())
        except (OSError, ValueError, yaml.YAMLError) as exc:
            _fail(f"cannot read context version before upgrade: {exc}")
        if not isinstance(config, dict) or str(config.get("version")) != "0.3":
            _fail("migration required: --upgrade accepts ACF 0.3 only; run the standalone "
                  "split_metrics.py converter and review the 0.3 config/definitions first. No files changed.")
        # Check against the incoming contract before any support files are copied.
        # A manually bumped config does not make a mixed/legacy layout migrated.
        sys.path.insert(0, str(SOURCE_ROOT if REPOSITORY_MODE else SOURCE_ROOT / "payload"))
        try:
            from acf_runtime import load_context
            schema_source = next(_source(a) for a in ARTIFACTS if a.target == "schemas")
            registry = load_context(target, schemas=schema_source)
        except ImportError:
            _fail("missing dependency: install jsonschema and pyyaml before upgrade validation")
        if registry.errors:
            _fail("migration/review required before upgrade; no files changed:\n" + "\n".join(map(str, registry.errors)))
    if not args.upgrade and marker.exists():
        _fail(f"{target} already contains a context repo; use --upgrade")

    if args.sim_marker:
        sys.path.insert(0, str(SOURCE_ROOT if REPOSITORY_MODE else SOURCE_ROOT / "payload"))
        from acf_runtime.simulation import load_marker, handoff
        try:
            simulation = load_marker(args.sim_marker)
            if Path(simulation["responses"]).is_relative_to(target):
                raise ValueError("target would contain the private brief")
            if (target / ".sim-analyst.json").exists() and load_marker(target / ".sim-analyst.json") != simulation:
                raise ValueError("target already has a different simulation marker")
        except (OSError, ValueError) as exc:
            _fail(f"invalid simulation handoff: {exc}")

    target.mkdir(parents=True, exist_ok=True)
    if args.upgrade:
        try:
            upgrade_review(target)
        except (OSError, ValueError) as exc:
            _fail(f"could not prepare private template review; support files unchanged: {exc}")
    _copy_artifacts(target, artifacts)
    if args.sim_marker:
        handoff(args.sim_marker, target)
    if self_check(target, fresh=not args.upgrade):
        return 1

    print("scaffold: done; continue from this repo's SPEC.md, schemas/, scripts/, and eval_harness/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
