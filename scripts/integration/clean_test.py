#!/usr/bin/env python3
"""Prepare and run an isolated Nodal integration test.

The harness tests a source checkout, native-plugin payload, or project-local
skills installation without copying ignored operator data into the clean room.
It never deletes a supplied directory.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from assert_context_repo import check_context_repo


ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ID = "nodal-analytics@nodal"
SKILL_NAMES = ("context-interview", "dashboard-verify", "setup-nodal")
ROOM_MARKER = ".nodal-clean-test.json"
RESUME_MARKER = ".nodal-clean-test-resume-marker"


class HarnessError(RuntimeError):
    pass


def _is_within(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _temp_roots():
    roots = {Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve()}
    return tuple(sorted(roots, key=str))


def _require_temp_room(room):
    if not any(_is_within(room, root) and room != root for root in _temp_roots()):
        allowed = ", ".join(map(str, _temp_roots()))
        raise HarnessError(f"clean rooms must be beneath an OS temporary directory ({allowed})")


def _command_json(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise HarnessError(f"required command is unavailable: {command[0]}") from exc
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise HarnessError(f"{' '.join(command)} failed: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HarnessError(f"{' '.join(command)} returned malformed JSON") from exc


def _skills_dir(package_root):
    candidates = (
        package_root / "skills",
        package_root / ".agents" / "skills",
        package_root / ".claude" / "skills",
        package_root,
    )
    for candidate in candidates:
        if all((candidate / name / "SKILL.md").is_file() for name in SKILL_NAMES):
            return candidate
    raise HarnessError(
        f"could not find all Nodal skills beneath {package_root}; "
        "pass the project or collection created by skills.sh"
    )


def _validate_package(package_root, package_source):
    package_root = package_root.expanduser().resolve()
    skills = _skills_dir(package_root)
    required = (
        skills / "context-interview" / "scripts" / "scaffold.py",
        skills / "context-interview" / "payload" / "template" / ".gitignore",
        skills / "context-interview" / "payload" / "template" / "evals" / "captures" / ".gitkeep",
        skills / "setup-nodal" / "scripts" / "nodal_config.py",
        skills / "setup-nodal" / "assets" / "chrome-devtools.mcp.json",
    )
    missing = [str(path.relative_to(package_root)) for path in required if not path.is_file()]
    if missing:
        raise HarnessError(f"incomplete {package_source} package; missing: {', '.join(missing)}")

    manifest = {
        "claude-plugin": package_root / ".claude-plugin" / "plugin.json",
        "codex-plugin": package_root / ".codex-plugin" / "plugin.json",
    }.get(package_source)
    if manifest and not manifest.is_file():
        raise HarnessError(f"{package_source} root lacks {manifest.relative_to(package_root)}")
    return package_root, skills


def _discover_package(package_source):
    if package_source == "source-checkout":
        return ROOT
    if package_source == "claude-plugin":
        plugins = _command_json(["claude", "plugin", "list", "--json"])
        for plugin in plugins:
            if plugin.get("id") == PLUGIN_ID and plugin.get("enabled"):
                install_path = plugin.get("installPath")
                if install_path:
                    return Path(install_path)
        raise HarnessError(f"enabled Claude plugin {PLUGIN_ID} was not found")
    if package_source == "codex-plugin":
        listing = _command_json(["codex", "plugin", "list", "--json"])
        for plugin in listing.get("installed", []):
            if plugin.get("pluginId") != PLUGIN_ID or not plugin.get("enabled"):
                continue
            source = plugin.get("source") or {}
            path = source.get("path")
            if path:
                return Path(path)
        raise HarnessError(f"enabled Codex plugin {PLUGIN_ID} was not found")
    raise HarnessError("skills mode requires --package-root from a skills.sh installation")


def resolve_package(package_source, package_root=None):
    root = Path(package_root) if package_root else _discover_package(package_source)
    return _validate_package(root, package_source)


def _copy_path(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        destination.symlink_to(os.readlink(source))
    elif source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination)


def _copy_source_checkout(destination):
    """Copy tracked and non-ignored worktree files, including uncommitted edits."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode(errors="replace").strip()
        raise HarnessError(f"git ls-files failed: {detail}")
    destination.mkdir(parents=True)
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = Path(os.fsdecode(raw))
        source = ROOT / relative
        if source.exists() or source.is_symlink():
            if source.is_symlink() and not _is_within(source.resolve(), ROOT):
                raise HarnessError(f"source worktree contains an external symlink: {relative}")
            _copy_path(source, destination / relative)


def _copy_skills(skills, project, host):
    target = project / (".claude/skills" if host == "claude" else ".agents/skills")
    target.mkdir(parents=True, exist_ok=True)
    for name in SKILL_NAMES:
        shutil.copytree(skills / name, target / name, symlinks=True)


def _init_project(project):
    result = subprocess.run(
        ["git", "init", "--quiet"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise HarnessError(f"could not initialize clean project: {result.stderr.strip()}")


def _new_room(path=None):
    if path is None:
        return Path(tempfile.mkdtemp(prefix="nodal-clean-test-")).resolve()
    room = Path(path).expanduser().resolve()
    _require_temp_room(room)
    if room.exists() and any(room.iterdir()):
        raise HarnessError(f"work directory must be absent or empty; refusing to replace {room}")
    room.mkdir(parents=True, exist_ok=True)
    return room


def _write_marker(room, package_source, host, package_root):
    data = {
        "version": 1,
        "package_source": package_source,
        "host": host,
        "package_root": str(package_root),
        "project": "project",
        "context_repo": "analytics-context",
    }
    (room / ROOM_MARKER).write_text(json.dumps(data, indent=2) + "\n")


def _load_resume_room(path):
    room = Path(path).expanduser().resolve()
    _require_temp_room(room)
    marker = room / ROOM_MARKER
    if not marker.is_file():
        raise HarnessError(f"resume directory lacks {ROOM_MARKER}: {room}")
    try:
        data = json.loads(marker.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError(f"resume marker is unreadable or malformed: {marker}") from exc
    if data.get("version") != 1:
        raise HarnessError(f"unsupported clean-test marker version in {marker}")
    return room, data


def _room_child(room, relative, label):
    if not isinstance(relative, str) or not relative:
        raise HarnessError(f"clean-test marker has an invalid {label}")
    child = (room / relative).resolve()
    if not _is_within(child, room):
        raise HarnessError(f"clean-test marker {label} escapes the clean room")
    return child


def _add_brief(brief, room, project):
    source = Path(brief).expanduser().resolve()
    if not source.is_file():
        raise HarnessError(f"simulated-analyst brief does not exist: {source}")
    destination = room / "responses.md"
    shutil.copy2(source, destination)
    destination.chmod(0o600)
    log = room / "simulated-analyst-log.md"
    payload = {"responses": str(destination), "log": str(log)}
    marker = project / ".sim-analyst.json"
    marker.write_text(json.dumps(payload, indent=2) + "\n")
    marker.chmod(0o600)


def _default_prompt(host, package_source, resumed, brief):
    if resumed:
        intent = "Resume the existing analytics context interview in ../analytics-context."
    else:
        intent = "Build an analytics context repository in ../analytics-context."
    if brief:
        intent += " Use the configured simulated analyst and complete the test-drive flow."
    if host == "codex":
        return f"$context-interview {intent}"
    command = (
        "/nodal-analytics:context-interview"
        if package_source == "claude-plugin"
        else "/context-interview"
    )
    return f"{command} {intent}"


def _launch(args, room, project, output, package_root, package_source, resumed):
    prompt = args.prompt or _default_prompt(args.host, package_source, resumed, args.brief)
    environment = os.environ.copy()

    if args.host == "claude":
        command = ["claude", "--add-dir", str(room), "--setting-sources", "project,local"]
        environment["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
        if args.operator_settings:
            settings = Path(args.operator_settings).expanduser().resolve()
            if not settings.is_file():
                raise HarnessError(f"operator settings file does not exist: {settings}")
            command.extend(["--settings", str(settings)])
        if args.mcp_config:
            mcp_config = Path(args.mcp_config).expanduser().resolve()
            if not mcp_config.is_file():
                raise HarnessError(f"MCP configuration does not exist: {mcp_config}")
            command.extend(["--mcp-config", str(mcp_config)])
        if args.unsafe_bypass:
            command.append("--dangerously-skip-permissions")
        elif args.non_interactive:
            command.extend(["--permission-mode", "acceptEdits"])
        if args.non_interactive:
            command.extend(["--print", "--no-session-persistence"])
        command.append(prompt)
    elif args.host == "codex":
        command = ["codex"]
        if args.non_interactive:
            command.extend(["exec", "--ephemeral"])
        command.extend(
            [
                "-C",
                str(project),
                "--add-dir",
                str(output),
            ]
        )
        if args.unsafe_bypass:
            command.append("--dangerously-bypass-approvals-and-sandbox")
        elif args.non_interactive:
            command.extend(["--sandbox", "workspace-write", "--approve-for-me"])
        command.append(prompt)
    else:
        return 0

    print(f"clean_test: launching {args.host} in {project}")
    result = subprocess.run(command, cwd=project, env=environment)
    return result.returncode


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package-source",
        choices=("source-checkout", "claude-plugin", "codex-plugin", "skills"),
        help="distribution artifact to exercise (new-room default: source-checkout)",
    )
    parser.add_argument("--package-root", help="explicit installed package/project root")
    parser.add_argument(
        "--host",
        choices=("claude", "codex", "none"),
        help="agent host to launch (new-room default: claude)",
    )
    location = parser.add_mutually_exclusive_group()
    location.add_argument("--work-dir", help="new absent or empty clean-room directory")
    location.add_argument(
        "--resume",
        metavar="WORK_DIR",
        help="reuse a prior clean room without deleting it",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="prepare files but do not launch a host",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="run the selected host in print/exec mode",
    )
    parser.add_argument(
        "--unsafe-bypass",
        action="store_true",
        help="explicitly bypass host safeguards; use only inside a hard sandbox",
    )
    parser.add_argument("--brief", help="ignored local simulated-analyst brief")
    parser.add_argument("--prompt", help="override the initial host prompt")
    parser.add_argument("--operator-settings", help="ignored local Claude settings JSON")
    parser.add_argument("--mcp-config", help="ignored local Claude MCP configuration")
    parser.add_argument(
        "--skip-assert",
        action="store_true",
        help="do not validate the generated context repo after the host exits",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    if args.unsafe_bypass and not args.non_interactive:
        raise HarnessError("--unsafe-bypass requires --non-interactive")
    resumed = bool(args.resume)
    if resumed:
        room, metadata = _load_resume_room(args.resume)
        package_source = metadata.get("package_source")
        host = metadata.get("host")
        if package_source not in ("source-checkout", "claude-plugin", "codex-plugin", "skills"):
            raise HarnessError("clean-test marker has an invalid package_source")
        if host not in ("claude", "codex", "none"):
            raise HarnessError("clean-test marker has an invalid host")
        if args.package_source and args.package_source != package_source:
            raise HarnessError("--package-source does not match the resumed clean room")
        if args.host and args.host != host:
            raise HarnessError("--host does not match the resumed clean room")
        args.host = host
        package_root_arg = args.package_root or metadata.get("package_root")
        project = _room_child(room, metadata.get("project"), "project path")
        output = _room_child(room, metadata.get("context_repo"), "context_repo path")
        initial_problems = check_context_repo(output)
        if initial_problems:
            detail = "; ".join(initial_problems)
            raise HarnessError(f"cannot resume an invalid context repo: {detail}")
        (output / RESUME_MARKER).write_text(f"resume test {uuid.uuid4()}\n")
    else:
        package_source = args.package_source or "source-checkout"
        host = args.host or "claude"
        args.host = host
        package_root_arg = args.package_root
        room = _new_room(args.work_dir)
        project = room / "project"
        output = room / "analytics-context"

    if host != "claude" and (args.operator_settings or args.mcp_config):
        raise HarnessError("--operator-settings and --mcp-config are Claude-only")

    if host != "none" and package_source == "claude-plugin" and host != "claude":
        raise HarnessError("claude-plugin package tests require --host claude")
    if host != "none" and package_source == "codex-plugin" and host != "codex":
        raise HarnessError("codex-plugin package tests require --host codex")

    package_root, skills = resolve_package(package_source, package_root_arg)
    native_plugin = package_source in ("claude-plugin", "codex-plugin")
    if native_plugin and host != "none" and not args.prepare_only:
        enabled_root = _discover_package(package_source).expanduser().resolve()
        if enabled_root != package_root:
            raise HarnessError(
                f"selected {package_source} root is not the enabled native installation: "
                f"{package_root} != {enabled_root}"
            )

    if not resumed:
        if package_source == "source-checkout":
            _copy_source_checkout(project)
            if host == "codex":
                _copy_skills(project / "skills", project, host)
        else:
            project.mkdir(parents=True)
            if package_source == "skills":
                _copy_skills(skills, project, host)
        _init_project(project)
        output.mkdir()
        _write_marker(room, package_source, host, package_root)

    if args.brief:
        _add_brief(args.brief, room, project)

    print(f"clean_test: work directory: {room}")
    print(f"clean_test: project:        {project}")
    print(f"clean_test: context repo:   {output}")
    print(f"clean_test: package source: {package_source} ({package_root})")
    if args.prepare_only:
        print("clean_test: prepared only; no host launched")
        return 0

    exit_code = _launch(args, room, project, output, package_root, package_source, resumed)
    if exit_code:
        print(
            f"clean_test: {host} exited with status {exit_code}; preserving {room}",
            file=sys.stderr,
        )
        return exit_code
    if args.skip_assert:
        print(f"clean_test: assertions skipped; preserving {room}")
        return 0

    problems = check_context_repo(output, RESUME_MARKER if resumed else None)
    if problems:
        print(f"clean_test: post-run assertions FAILED — preserving {room}", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"clean_test: post-run assertions OK — preserving {room}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HarnessError as exc:
        print(f"clean_test: ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
