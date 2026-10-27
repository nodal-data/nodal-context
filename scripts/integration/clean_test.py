#!/usr/bin/env python3
"""Prepare and run an isolated Nodal integration test.

The harness tests a source checkout, native-plugin payload, or project-local
skills installation without copying ignored operator data into the clean room.
It never deletes a supplied directory.
"""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from assert_agent_onboarding import check_agent_onboarding
from assert_context_repo import check_context_repo
from assert_setup_lifecycle import check_setup_lifecycle


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from acf_runtime.simulation import MARKER as SIM_MARKER, handoff, load_marker, pending, check_output, summarize
from acf_runtime.verified import atomic_private
PLUGIN_ID = "nodal-analytics@nodal"
SKILL_NAMES = (
    "analytics-plan",
    "analyst-handoff",
    "challenge-result",
    "context-interview",
    "dashboard-verify",
    "setup-nodal",
    "verify-result",
)
ROOM_MARKER = ".nodal-clean-test.json"
RESUME_MARKER = ".nodal-clean-test-resume-marker"
BROWSER_LIFECYCLE_SCENARIO = "browser-install-lifecycle"
AGENT_ONBOARDING_SCENARIO = "agent-guided-onboarding"


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


def _command_json(command, environment=None):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
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


def _discover_package(package_source, environment=None):
    if package_source == "source-checkout":
        return ROOT
    if package_source == "claude-plugin":
        plugins = _command_json(
            ["claude", "plugin", "list", "--json"], environment=environment
        )
        for plugin in plugins:
            if plugin.get("id") == PLUGIN_ID and plugin.get("enabled"):
                install_path = plugin.get("installPath")
                if install_path:
                    return Path(install_path)
        raise HarnessError(f"enabled Claude plugin {PLUGIN_ID} was not found")
    if package_source == "codex-plugin":
        listing = _command_json(
            ["codex", "plugin", "list", "--json"], environment=environment
        )
        for plugin in listing.get("installed", []):
            if plugin.get("pluginId") != PLUGIN_ID or not plugin.get("enabled"):
                continue
            source = plugin.get("source") or {}
            path = source.get("path")
            if path:
                return Path(path)
        raise HarnessError(f"enabled Codex plugin {PLUGIN_ID} was not found")
    raise HarnessError("skills mode requires --package-root from a skills.sh installation")


def resolve_package(package_source, package_root=None, environment=None):
    root = (
        Path(package_root)
        if package_root
        else _discover_package(package_source, environment=environment)
    )
    return _validate_package(root, package_source)


def _normalize_marketplace_source(source):
    candidate = Path(source).expanduser()
    if candidate.exists():
        return str(candidate.resolve())
    return source


def _install_isolated_codex_plugin(source, ref, environment):
    source = _normalize_marketplace_source(source or str(ROOT))
    marketplace = ["codex", "plugin", "marketplace", "add", source]
    if ref:
        marketplace.extend(["--ref", ref])
    marketplace.append("--json")
    print(f"clean_test: adding isolated Codex marketplace: {source}")
    _command_json(marketplace, environment=environment)
    print(f"clean_test: installing isolated Codex plugin: {PLUGIN_ID}")
    _command_json(
        ["codex", "plugin", "add", PLUGIN_ID, "--json"],
        environment=environment,
    )


def _copy_path(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        destination.symlink_to(os.readlink(source))
    elif source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination)


def _private_path(relative):
    """Exclude operator data even if it was accidentally tracked or force-added."""
    parts = relative.parts
    name = relative.name.lower()
    private_dirs = {"specs", ".git", ".nodal", ".venv", ".codex", ".aws", ".ssh",
                    "__pycache__", ".nodal-dashboard-verify-profile"}
    if set(parts) & private_dirs:
        return True
    if any(parts[i:i + 2] in (("evals", "runs"), ("evals", "captures"), ("evals", "observed"))
           for i in range(len(parts) - 1)) and name != ".gitkeep":
        return True
    if "verified" in parts and name.endswith(".sql"):
        return True
    return (name in {"findings.md", ".env", ".envrc", ".nodal.local.json", ".mcp.json",
                     "settings.local.json", SIM_MARKER, "clean-test.sh", "clean-test.local.sh",
                     "simulated-analyst-log.md", "simulated-analyst-log.state.json"}
            or name.endswith((".context.md", ".ipynb", ".pyc", "-transcript.log"))
            or (name.startswith("responses") and name.endswith(".md")))


def _copy_source_checkout(destination, brief=None):
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
        if _private_path(relative) or (brief and source.resolve() == Path(brief).resolve()):
            continue
        if source.exists() or source.is_symlink():
            if source.is_dir() and not source.is_symlink():
                raise HarnessError(f"source entry is a nested repository/directory, not a package file: {relative}")
            if source.is_symlink() and (source.readlink().is_absolute() or not _is_within(source.resolve(), ROOT)):
                raise HarnessError(f"source worktree contains an absolute or external symlink: {relative}")
            _copy_path(source, destination / relative)


def _copy_skills(skills, project, host):
    target = project / (".claude/skills" if host == "claude" else ".agents/skills")
    target.mkdir(parents=True, exist_ok=True)
    for name in SKILL_NAMES:
        source = skills / name
        for path in source.rglob("*"):
            if path.is_symlink() and (path.readlink().is_absolute() or not _is_within(path.resolve(), source.resolve())):
                raise HarnessError("installed skill contains an absolute or external symlink")
        shutil.copytree(source, target / name, symlinks=True,
                        ignore=lambda directory, names: [n for n in names if _private_path(Path(directory).relative_to(source) / n)])


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
    room.chmod(0o700)
    return room


def _write_marker(
    room,
    package_source,
    host,
    package_root,
    isolated_host,
    scenario,
    marketplace_source,
    marketplace_ref,
):
    data = {
        "version": 2,
        "package_source": package_source,
        "host": host,
        "package_root": str(package_root),
        "project": "project",
        "context_repo": "analytics-context",
        "isolated_host": isolated_host,
        "scenario": scenario,
    }
    if isolated_host and host == "codex":
        data["codex_home"] = "codex-home"
    if marketplace_source:
        data["marketplace_source"] = marketplace_source
    if marketplace_ref:
        data["marketplace_ref"] = marketplace_ref
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
    if data.get("version") not in (1, 2):
        raise HarnessError(f"unsupported clean-test marker version in {marker}")
    return room, data


def _room_child(room, relative, label):
    if not isinstance(relative, str) or not relative:
        raise HarnessError(f"clean-test marker has an invalid {label}")
    child = (room / relative).resolve()
    if not _is_within(child, room):
        raise HarnessError(f"clean-test marker {label} escapes the clean room")
    return child


def _add_brief(brief, room, project, output, non_interactive=False):
    source = Path(brief).expanduser().resolve()
    if not source.is_file():
        raise HarnessError(f"simulated-analyst brief does not exist: {source}")
    destination = room / "responses.md"
    marker = project / SIM_MARKER
    if marker.exists():
        # A resume keeps the original copied brief and transcript; no silent rebind.
        existing = load_marker(marker)
        if source != Path(existing["responses"]) and source.read_bytes() != Path(existing["responses"]).read_bytes():
            raise HarnessError("resume brief differs from this run; start a new room for a different brief")
        return _simulation_mode(room, project, output, non_interactive)
    shutil.copy2(source, destination)
    destination.chmod(0o600)
    log = room / "simulated-analyst-log.md"
    payload = {"responses": str(destination), "log": str(log), "run_id": str(uuid.uuid4()),
               "mode": "non-interactive" if non_interactive else "interactive"}
    marker.write_text(json.dumps(payload, indent=2) + "\n")
    marker.chmod(0o600)
    handoff(marker, output)
    return marker


def _simulation_mode(room, project, output, non_interactive):
    marker = project / SIM_MARKER
    if not marker.exists():
        return None
    data = load_marker(marker)
    for key in ("responses", "log", "state"):
        if Path(data[key]).parent != room:
            raise HarnessError("simulation pointers must remain in the clean room")
    if (output / SIM_MARKER).exists() and load_marker(output / SIM_MARKER) != data:
        raise HarnessError("project/context simulation markers disagree")
    data["mode"] = "non-interactive" if non_interactive else "interactive"
    for path in (marker, output / SIM_MARKER):
        if path.is_symlink():
            raise HarnessError("simulation marker cannot be a symlink")
        path.write_text(json.dumps(data, indent=2) + "\n")
        path.chmod(0o600)
    return marker


def _setup_command(host, package_source):
    if host == "codex":
        return "$setup-nodal"
    if package_source == "claude-plugin":
        return "/nodal-analytics:setup-nodal"
    return "/setup-nodal"


def _browser_lifecycle_prompt(host, package_source):
    command = _setup_command(host, package_source)
    return f"""{command} Set up Nodal in this clean project. I have named a dashboard
called Clean Test Dashboard and want automated dashboard verification. I explicitly consent to
adding the bundled Chrome DevTools MCP project binding and confirm the normal sanitized
.nodal.local.json destination with ../analytics-context as the context repository. Do not request
or handle credentials, and do not require warehouse connectivity for this test.

After adding the binding, invoke setup-nodal a second time in this same session. The second check
must distinguish an already configured but not-yet-live binding from a missing binding, request the
required session restart and one-time project-server approval, and must not offer installation
again. In the final user-facing response, explain that the browser is optional, visible, and uses a
dedicated Chrome profile while credentials remain with the user. End with this lifecycle receipt,
using these labels exactly and filling in the observed values:

- Binding status: configured
- Next action: restart and approve the project server once
- Repeat installation offer: no
"""


def _agent_onboarding_prompt():
    return f"""Help me understand and set up Nodal Analytics for this clean Codex project. Read
NODAL_AGENT_GUIDE.md first and follow it step by step. This is a local release-candidate test, so
use {ROOT} as the Codex marketplace source instead of GitHub. I explicitly consent to the one
Codex native-plugin installation after you explain what it changes. Do not install project-local
skills, do not write .nodal.local.json or .mcp.json, and do not try to use the newly installed
skill in this task. Verify the installation, explain the required new-task boundary, and tell me
the exact setup-nodal invocation for the next task. Never request or handle credentials.

End with this onboarding receipt, using these labels exactly and filling in the observed values:

- Installation method: Codex native plugin
- Duplicate installation: no
- Configuration written: no
- Next task: restart Codex and invoke $setup-nodal
- Credentials requested: no
"""


def _default_prompt(host, package_source, resumed, brief, scenario=None):
    if scenario == AGENT_ONBOARDING_SCENARIO:
        return _agent_onboarding_prompt()
    if scenario == BROWSER_LIFECYCLE_SCENARIO:
        return _browser_lifecycle_prompt(host, package_source)
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


def _host_environment(host, room, isolated_host, metadata=None):
    environment = os.environ.copy()
    if isolated_host and host == "codex":
        relative = (metadata or {}).get("codex_home", "codex-home")
        codex_home = _room_child(room, relative, "Codex home")
        codex_home.mkdir(parents=True, exist_ok=True)
        environment["CODEX_HOME"] = str(codex_home)
    return environment


def _run_with_transcript(command, cwd, environment, transcript):
    transcript.parent.mkdir(parents=True, exist_ok=True)
    if transcript.is_symlink():
        raise HarnessError("transcript cannot be a symlink")
    descriptor = os.open(transcript, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    transcript.chmod(0o600)
    with os.fdopen(descriptor, "w") as stream:
        try:
            process = subprocess.Popen(
                command, cwd=cwd, env=environment, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1,
            )
        except FileNotFoundError as exc:
            raise HarnessError(f"required command is unavailable: {command[0]}") from exc
        for line in process.stdout:
            print(line, end="", flush=True)
            stream.write(line)
    return process.wait()


def _launch(
    args,
    room,
    project,
    output,
    package_root,
    package_source,
    resumed,
    environment,
):
    prompt = args.prompt or _default_prompt(
        args.host,
        package_source,
        resumed,
        args.sim_marker,
        scenario=args.scenario,
    )
    if args.sim_marker:
        # Surface the actual installed paths, rather than asking the host to
        # guess between discovery symlinks and canonical scripts. Operators can
        # grant these exact commands for noninteractive sessions.
        try:
            simulation_skills = _skills_dir(project)
        except HarnessError:
            simulation_skills = _skills_dir(package_root)
        simulation_scripts = (simulation_skills / "context-interview" / "scripts").resolve()
        prompt += (f"\nSimulation marker: {args.sim_marker}. It is also present at {output / SIM_MARKER}. "
                   "Read the marker and references/simulated-analyst.md; do not read the brief yourself. "
                   "Only an isolated responder may read it. Log each question with scripts/simulated_analyst.py. "
                   "For a batched exchange, require one leading CONFIDENT: prefix only if every item is supported; "
                   "otherwise use one leading NOT_CONFIDENT: prefix. Put any numbering after the prefix. "
                   "Keep simulator-only artifacts draft with no approver or confirmed_at. "
                   "Authentication, warehouse, notebook and dashboard actions require real execution. "
                   "Do not invent execution evidence; unavailable verification may be skipped.")
        prompt += (f" Use python3 with these absolute script paths: scaffold {simulation_scripts / 'scaffold.py'}; "
                   f"simulation helper {simulation_scripts / 'simulated_analyst.py'}; "
                   f"after scaffolding, validation {output / '.ci' / 'validate.py'}. "
                   "Use these paths rather than alternate copies or discovery symlinks so operator permission grants match. "
                   "The paths do not grant permission; if the host denies execution, report the exact denied command and stop.")
        if args.non_interactive:
            prompt += (" On NOT_CONFIDENT or an unavailable responder, record the pending question and stop. "
                       "Do not guess to finish. Resume from the pending question in the shared simulation state.")
        else:
            prompt += " On NOT_CONFIDENT, ask the real user; pending questions in the shared state take priority on resume."
        if resumed and not (output / "context.config.yaml").exists():
            prompt += " The prior run paused before scaffolding. Continue setup in the same destination, preserving its marker."

    if args.host == "claude":
        command = ["claude"]
        if args.isolated_host:
            command.append("--bare")
        command.extend(["--add-dir", str(room)])
        if not args.isolated_host:
            command.extend(["--setting-sources", "project,local"])
        if args.isolated_host and package_source == "claude-plugin":
            command.extend(["--plugin-dir", str(package_root)])
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
        if args.isolated_host:
            command.extend(["--add-dir", environment["CODEX_HOME"]])
        if args.sim_marker:
            command.extend(["--add-dir", str(room)])
        if args.unsafe_bypass:
            command.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            command.extend(["--sandbox", "workspace-write"])
            if args.non_interactive:
                command.append("--approve-for-me")
        command.append(prompt)
    else:
        return 0, None

    print(f"clean_test: launching {args.host} in {project}")
    if args.non_interactive:
        transcript = room / f"{args.host}-transcript.log"
        print(f"clean_test: transcript:     {transcript}")
        return _run_with_transcript(command, project, environment, transcript), transcript
    result = subprocess.run(command, cwd=project, env=environment)
    return result.returncode, None


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
    location.add_argument(
        "--launch-prepared",
        metavar="WORK_DIR",
        help="launch a room previously created with --prepare-only",
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
        "--isolated-host",
        action="store_true",
        help="exclude normal host customizations (fresh CODEX_HOME or Claude --bare)",
    )
    parser.add_argument(
        "--marketplace-source",
        help="local path or Git source installed into an isolated Codex home",
    )
    parser.add_argument(
        "--marketplace-ref",
        help="Git ref used with --marketplace-source for an isolated Codex install",
    )
    parser.add_argument(
        "--scenario",
        choices=(AGENT_ONBOARDING_SCENARIO, BROWSER_LIFECYCLE_SCENARIO),
        help="run a release scenario with scenario-specific assertions",
    )
    parser.add_argument(
        "--unsafe-bypass",
        action="store_true",
        help="explicitly bypass host safeguards; use only inside a hard sandbox",
    )
    parser.add_argument("--brief", help="ignored local simulated-analyst brief")
    parser.add_argument("--auto", action="store_true", help="legacy quick simulation: use local responses.md or RESPONSES.md")
    parser.add_argument("legacy_work_dir", nargs="?", help="legacy positional clean-room destination; must be absent or empty")
    parser.add_argument("--prompt", help="override the initial host prompt")
    parser.add_argument("--operator-settings", help="ignored local Claude settings JSON")
    parser.add_argument("--mcp-config", help="ignored local Claude MCP configuration")
    parser.add_argument(
        "--skip-assert",
        action="store_true",
        help="do not validate the generated context repo after the host exits",
    )
    raw = list(sys.argv[1:] if argv is None else argv)
    normalized = []
    for token in raw:
        normalized.extend(["--brief", token.split("=", 1)[1]] if token.startswith("--auto=") else [token])
    args = parser.parse_args(normalized)
    if args.auto and args.brief:
        parser.error("use --auto or --brief, not both")
    if args.auto:
        args.brief = str(next((ROOT / name for name in ("responses.md", "RESPONSES.md")
                               if (ROOT / name).is_file()), ROOT / "responses.md"))
    if args.legacy_work_dir:
        if args.work_dir or args.resume or args.launch_prepared:
            parser.error("positional destination cannot be combined with another room selection")
        args.work_dir = args.legacy_work_dir
    return args


def main(argv=None):
    args = _parse_args(argv)
    if args.scenario and args.brief:
        raise HarnessError("simulated interviews and installation scenarios are separate runs")
    if args.brief and not Path(args.brief).expanduser().is_file():
        raise HarnessError("simulated-analyst brief does not exist")
    if args.unsafe_bypass and not args.non_interactive:
        raise HarnessError("--unsafe-bypass requires --non-interactive")
    if args.launch_prepared and args.prepare_only:
        raise HarnessError("--launch-prepared cannot be combined with --prepare-only")

    resumed = bool(args.resume)
    prepared_launch = bool(args.launch_prepared)
    existing_room = resumed or prepared_launch
    metadata = None
    if existing_room:
        room, metadata = _load_resume_room(args.resume or args.launch_prepared)
        package_source = metadata.get("package_source")
        host = metadata.get("host")
        if package_source not in ("source-checkout", "claude-plugin", "codex-plugin", "skills"):
            raise HarnessError("clean-test marker has an invalid package_source")
        if host not in ("claude", "codex", "none"):
            raise HarnessError("clean-test marker has an invalid host")
        if args.package_source and args.package_source != package_source:
            raise HarnessError("--package-source does not match the existing clean room")
        if args.host and args.host != host:
            raise HarnessError("--host does not match the existing clean room")
        args.host = host
        stored_scenario = metadata.get("scenario")
        if args.scenario and args.scenario != stored_scenario:
            raise HarnessError("--scenario does not match the existing clean room")
        args.scenario = stored_scenario
        stored_isolation = bool(metadata.get("isolated_host", False))
        if args.isolated_host and not stored_isolation:
            raise HarnessError("--isolated-host does not match the existing clean room")
        args.isolated_host = stored_isolation
        stored_marketplace_source = metadata.get("marketplace_source")
        stored_marketplace_ref = metadata.get("marketplace_ref")
        if args.marketplace_source and args.marketplace_source != stored_marketplace_source:
            raise HarnessError("--marketplace-source does not match the existing clean room")
        if args.marketplace_ref and args.marketplace_ref != stored_marketplace_ref:
            raise HarnessError("--marketplace-ref does not match the existing clean room")
        args.marketplace_source = stored_marketplace_source
        args.marketplace_ref = stored_marketplace_ref
        stored_package_root = metadata.get("package_root")
        if not isinstance(stored_package_root, str) or not stored_package_root:
            raise HarnessError("clean-test marker has an invalid package_root")
        if prepared_launch and args.package_root:
            requested_root = Path(args.package_root).expanduser().resolve()
            if requested_root != Path(stored_package_root).expanduser().resolve():
                raise HarnessError("--package-root does not match the prepared clean room")
        package_root_arg = args.package_root or stored_package_root
        project = _room_child(room, metadata.get("project"), "project path")
        output = _room_child(room, metadata.get("context_repo"), "context_repo path")
        if resumed:
            if args.scenario:
                raise HarnessError("release scenarios cannot use --resume; use --launch-prepared")
            early_simulation = ((project / SIM_MARKER).is_file() and (output / SIM_MARKER).is_file()
                                and output.is_dir() and all(p.name in (SIM_MARKER, RESUME_MARKER)
                                                           for p in output.iterdir()))
            initial_problems = [] if early_simulation else check_context_repo(output)
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

    if args.scenario and not args.prepare_only and not args.non_interactive:
        raise HarnessError("--scenario requires --non-interactive when a host is launched")
    if args.scenario == AGENT_ONBOARDING_SCENARIO and not (
        args.isolated_host and host == "codex" and package_source == "source-checkout"
    ):
        raise HarnessError(
            "agent-guided-onboarding requires --package-source source-checkout, "
            "--host codex, and --isolated-host"
        )
    if args.isolated_host and host == "none":
        raise HarnessError("--isolated-host requires --host claude or --host codex")
    if host != "claude" and (args.operator_settings or args.mcp_config):
        raise HarnessError("--operator-settings and --mcp-config are Claude-only")

    if host != "none" and package_source == "claude-plugin" and host != "claude":
        raise HarnessError("claude-plugin package tests require --host claude")
    if host != "none" and package_source == "codex-plugin" and host != "codex":
        raise HarnessError("codex-plugin package tests require --host codex")

    if args.marketplace_ref and not args.marketplace_source:
        raise HarnessError("--marketplace-ref requires --marketplace-source")
    marketplace_install = (
        not existing_room
        and args.isolated_host
        and host == "codex"
        and package_source == "codex-plugin"
    )
    if (
        not existing_room
        and (args.marketplace_source or args.marketplace_ref)
        and not marketplace_install
    ):
        raise HarnessError(
            "--marketplace-source and --marketplace-ref require a new isolated "
            "Codex native-plugin room"
        )
    if marketplace_install and package_root_arg:
        raise HarnessError(
            "--package-root cannot be combined with isolated Codex plugin installation"
        )

    environment = _host_environment(
        host,
        room,
        args.isolated_host,
        metadata=metadata,
    )
    if marketplace_install:
        args.marketplace_source = args.marketplace_source or str(ROOT)
        _install_isolated_codex_plugin(
            args.marketplace_source,
            args.marketplace_ref,
            environment,
        )
    elif (
        not existing_room
        and args.isolated_host
        and host == "claude"
        and package_source == "claude-plugin"
        and not package_root_arg
    ):
        package_root_arg = ROOT

    package_root, skills = resolve_package(
        package_source,
        package_root_arg,
        environment=environment,
    )
    native_plugin = package_source in ("claude-plugin", "codex-plugin")
    if native_plugin and host != "none" and not args.prepare_only and not args.isolated_host:
        enabled_root = _discover_package(
            package_source,
            environment=environment,
        ).expanduser().resolve()
        if enabled_root != package_root:
            raise HarnessError(
                f"selected {package_source} root is not the enabled native installation: "
                f"{package_root} != {enabled_root}"
            )

    if not existing_room:
        if package_source == "source-checkout":
            if args.scenario == AGENT_ONBOARDING_SCENARIO:
                project.mkdir(parents=True)
                shutil.copy2(
                    ROOT / "docs" / "agent-guide.md",
                    project / "NODAL_AGENT_GUIDE.md",
                )
            else:
                _copy_source_checkout(project, args.brief)
                if host == "codex":
                    _copy_skills(project / "skills", project, host)
        else:
            project.mkdir(parents=True)
            if package_source == "skills":
                _copy_skills(skills, project, host)
        _init_project(project)
        output.mkdir()
        _write_marker(
            room,
            package_source,
            host,
            package_root,
            args.isolated_host,
            args.scenario,
            args.marketplace_source,
            args.marketplace_ref,
        )

    if args.brief:
        args.sim_marker = _add_brief(args.brief, room, project, output, args.non_interactive)
    else:
        args.sim_marker = _simulation_mode(room, project, output, args.non_interactive)

    print(f"clean_test: work directory: {room}")
    print(f"clean_test: project:        {project}")
    print(f"clean_test: context repo:   {output}")
    print(f"clean_test: package source: {package_source} ({package_root})")
    print(f"clean_test: isolated host:  {'yes' if args.isolated_host else 'no'}")
    if args.isolated_host and host == "codex":
        print(f"clean_test: Codex home:     {environment['CODEX_HOME']}")
    if args.scenario:
        print(f"clean_test: scenario:       {args.scenario}")
    if args.sim_marker:
        print(f"clean_test: simulation:     {args.sim_marker}; output is draft test context")
    if args.prepare_only:
        print("clean_test: prepared only; no host launched")
        if args.isolated_host and host == "codex":
            codex_home = shlex.quote(environment["CODEX_HOME"])
            print(
                "clean_test: authenticate:  "
                f"CODEX_HOME={codex_home} codex login --device-auth"
            )
        if host != "none":
            room_arg = shlex.quote(str(room))
            suffix = " --non-interactive" if args.scenario else ""
            print(
                "clean_test: then launch:   "
                f"scripts/integration/clean_test.sh --launch-prepared {room_arg}{suffix}"
            )
        return 0

    exit_code, transcript = _launch(
        args,
        room,
        project,
        output,
        package_root,
        package_source,
        resumed,
        environment,
    )
    if args.sim_marker:
        summary = summarize(output, args.sim_marker)
        summary_path = room / "simulation-summary.json"
        atomic_private(summary_path, (json.dumps(summary, indent=2) + "\n").encode(), overwrite=summary_path.exists())
        print(f"clean_test: draft capture summary: {summary_path}")
        print(f"clean_test: exchange log: {summary['exchange_log']}")
        print(f"clean_test: drafts: {len(summary['draft_metrics'])} metrics, {len(summary['draft_methods'])} methods; "
              f"{len(summary['pending_human_questions'])} pending human questions, {len(summary['open_decisions'])} open decisions")
        print(f"clean_test: verification: {len(summary['verification_work'])} follow-up items; simulation does not establish execution")
    if exit_code:
        print(
            f"clean_test: {host} exited with status {exit_code}; preserving {room}",
            file=sys.stderr,
        )
        return exit_code
    if args.sim_marker:
        waiting = pending(args.sim_marker)
        if waiting:
            print(f"clean_test: simulation paused — {len(waiting)} pending human question(s); preserving {room}")
            return 3
    if args.skip_assert:
        print(f"clean_test: assertions skipped; preserving {room}")
        return 0

    if args.scenario == AGENT_ONBOARDING_SCENARIO:
        resolve_package("codex-plugin", environment=environment)
        problems = check_agent_onboarding(
            project,
            transcript,
            environment["CODEX_HOME"],
        )
        assertion_label = "agent onboarding"
    elif args.scenario == BROWSER_LIFECYCLE_SCENARIO:
        problems = check_setup_lifecycle(project, transcript)
        assertion_label = "setup lifecycle"
    else:
        problems = check_context_repo(output, RESUME_MARKER if resumed else None)
        if args.sim_marker:
            problems.extend(check_output(output, args.sim_marker, require_content=True))
        assertion_label = "post-run"
    if problems:
        print(
            f"clean_test: {assertion_label} assertions FAILED — preserving {room}",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"clean_test: {assertion_label} assertions OK — preserving {room}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HarnessError, ValueError, OSError) as exc:
        print(f"clean_test: ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
