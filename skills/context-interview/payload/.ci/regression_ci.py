#!/usr/bin/env python3
"""Trusted-revision CI wrapper with an owned temporary checkout and key cleanup."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval_harness.execution import private_json, strict_json

MARKER = ".nodal-regression-owned.json"


def checked_workspace(path, base):
    path, base = Path(path).absolute(), Path(base).resolve()
    if path.is_symlink() or path.parent.resolve() != base or not path.name.startswith("nodal-regression-"):
        raise ValueError("not an owned regression workspace")
    marker = path / MARKER
    if marker.is_symlink() or not marker.is_file():
        raise ValueError("missing workspace ownership marker")
    data = strict_json(marker.read_text())
    if data.get("path") != str(path) or data.get("owner") != "nodal-regression-ci/1":
        raise ValueError("workspace ownership mismatch")
    return path


def prepare(source, base):
    source, base = Path(source).resolve(), Path(base).resolve()
    commit = subprocess.run(["git", "rev-parse", "--verify", "HEAD^{commit}"], cwd=source,
                            capture_output=True, text=True, check=True).stdout.strip()
    commit_bytes = subprocess.run(["git", "cat-file", "commit", commit], cwd=source,
                                  capture_output=True, check=True).stdout
    files = subprocess.run(["git", "ls-files", "-z"], cwd=source, capture_output=True, check=True).stdout.split(b"\0")
    workspace = Path(tempfile.mkdtemp(prefix="nodal-regression-", dir=base))
    try:
        private_json(workspace / MARKER, {"path": str(workspace), "owner": "nodal-regression-ci/1", "nonce": uuid.uuid4().hex})
        destination = workspace / "context"; destination.mkdir()
        # Copy only tracked files from the already trusted checkout. Never clone
        # ignored local state, keys or plaintext sidecars into secret-bearing work.
        for raw in files:
            if not raw:
                continue
            relative = Path(os.fsdecode(raw))
            original = source / relative
            if relative.is_absolute() or ".." in relative.parts or not original.resolve().is_relative_to(source):
                raise ValueError("tracked path escapes checkout")
            if original.is_symlink() or any(parent.is_symlink() for parent in original.parents if parent != source):
                raise ValueError("symlinks are unsupported in the regression checkout")
            if relative.parts[0] in (".nodal", "specs") or relative.as_posix().startswith("evals/runs/"):
                continue
            if relative.as_posix().startswith("evals/verified/") and relative.suffix not in (".age", ".sops"):
                continue
            if not original.is_file():
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
        # Preserve the exact source identity without copying Git config, hooks,
        # credentials, or excluded plaintext blobs. Only the commit object and
        # detached HEAD are needed; live approval also checks all context bytes.
        subprocess.run(["git", "-c", "init.templateDir=", "init", "-q", str(destination)], check=True)
        copied = subprocess.run(["git", "hash-object", "-t", "commit", "-w", "--stdin"],
                                cwd=destination, input=commit_bytes, capture_output=True, check=True).stdout.decode().strip()
        if copied != commit:
            raise ValueError("source revision changed during preparation")
        (destination / ".git/HEAD").write_text(commit + "\n")
        return workspace
    except Exception:
        shutil.rmtree(workspace)
        raise


def sanitize_report(raw):
    data = strict_json(raw)
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("results"), list):
        raise ValueError("invalid public regression report")
    result = []
    for row in data["results"]:
        if (not isinstance(row, dict) or set(row) != {"seed_id", "status", "category"} or
                not isinstance(row["seed_id"], str) or row["status"] not in ("pass", "fail", "skipped") or
                not isinstance(row["category"], str) or not row["category"].replace("_", "").isalpha()):
            raise ValueError("nonpublic fields in regression report")
        result.append(row)
    return {"schema_version": 1, "results": result}


def execute(workspace, base, env=None):
    workspace = checked_workspace(workspace, base)
    environment = dict(os.environ if env is None else env)
    context = workspace / "context"
    args = [sys.executable, str(context / "scripts/regress.py"), "--root", str(context)]
    for variable, flag in (("NODAL_REGRESSION_EXECUTOR", "--executor"), ("NODAL_REGRESSION_JUDGE", "--judge")):
        if environment.get(variable):
            args.extend([flag, environment[variable]])
    raw_identity = environment.pop("NODAL_VERIFIED_IDENTITY", "")
    key_path = workspace / "identity.txt"
    try:
        if raw_identity:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                stream.write(raw_identity + "\n")
            args.extend(["--identity", str(key_path)])
        result = subprocess.run(args, cwd=context, env=environment, capture_output=True, text=True, check=False)
        # stdout is a restrictive allowlist. Stderr is private and never published.
        if result.returncode not in (0, 1, 3):
            return 2, {"status": "error", "category": "regression_configuration_error"}
        try:
            report = sanitize_report(result.stdout)
        except (ValueError, TypeError):
            return 2, {"status": "error", "category": "invalid_public_report"}
        return result.returncode, report
    finally:
        key_path.unlink(missing_ok=True)


def cleanup(workspace, base):
    workspace = checked_workspace(workspace, base)
    shutil.rmtree(workspace)  # only a room created/marked by prepare(), never caller content


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "cleanup"))
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args(argv)
    try:
        base = Path(os.environ["RUNNER_TEMP"])
        if args.operation == "prepare":
            print("path=" + str(prepare(args.source, base)))
            return 0
        if not args.workspace:
            raise ValueError("workspace required")
        if args.operation == "cleanup":
            cleanup(args.workspace, base)
            return 0
        code, report = execute(args.workspace, base)
        text = json.dumps(report, indent=2)
        print(text)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as summary:
                label = "passed" if code == 0 else "failed" if code == 1 else "skipped/incomplete" if code == 3 else "configuration error"
                summary.write("## Customer regression: " + label + "\n\n```json\n" + text + "\n```\n")
        # A skipped evaluation is displayed explicitly, rather than a numeric pass.
        return code
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        print('{"status":"error","category":"regression_ci_error"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
