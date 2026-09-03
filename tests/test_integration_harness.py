"""Offline safety, packaging-mode, assertion, and resume tests for clean_test."""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "scripts" / "integration"
HARNESS = INTEGRATION / "clean_test.py"
ASSERT = INTEGRATION / "assert_context_repo.py"
ASSERT_ONBOARDING = INTEGRATION / "assert_agent_onboarding.py"
ASSERT_SETUP = INTEGRATION / "assert_setup_lifecycle.py"


def run_harness(*args, env=None):
    return subprocess.run(
        [sys.executable, "-B", str(HARNESS), *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def scaffold(target):
    return subprocess.run(
        [sys.executable, "-B", str(ROOT / "scripts/scaffold.py"), str(target)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def write_fake_codex(path):
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
with Path(os.environ["FAKE_CODEX_LOG"]).open("a") as stream:
    stream.write(json.dumps({"args": args, "codex_home": os.environ.get("CODEX_HOME")}) + "\\n")

if args[:3] == ["plugin", "marketplace", "add"]:
    print("{}")
elif args[:2] == ["plugin", "add"]:
    print("{}")
elif args[:3] == ["plugin", "list", "--json"]:
    print(json.dumps({"installed": [{
        "pluginId": "nodal-analytics@nodal",
        "enabled": True,
        "source": {"path": os.environ["FAKE_PLUGIN_ROOT"]},
    }]}))
elif args and args[0] == "exec":
    project = Path.cwd()
    if "NODAL_AGENT_GUIDE.md" in args[-1]:
        codex_home = Path(os.environ["CODEX_HOME"])
        (codex_home / "config.toml").write_text(
            '[marketplaces.nodal]\\nsource_type = "local"\\nsource = "fixture"\\n\\n'
            '[plugins."nodal-analytics@nodal"]\\nenabled = true\\n'
        )
        print("Nodal supplies governed analytics context. I selected exactly one install path.")
        print("Start a new task before $setup-nodal; credentials are never requested.")
        print("Installation method: Codex native plugin")
        print("Duplicate installation: no")
        print("Configuration written: no")
        print("Next task: restart Codex and invoke $setup-nodal")
        print("Credentials requested: no")
    else:
        (project / ".nodal.local.json").write_text(json.dumps({
            "version": 1,
            "context_repo": "../analytics-context",
            "context_sources": [],
            "browser": {"mode": "automated", "binding": "chrome-devtools"},
        }) + "\\n")
        (project / ".mcp.json").write_text(json.dumps({
            "mcpServers": {"chrome-devtools": {"command": "npx", "args": ["example"]}}
        }) + "\\n")
        print("The optional browser uses a visible, dedicated Chrome profile; credentials remain with the user.")
        print("Binding status: configured")
        print("Next action: restart and approve the project server once")
        print("Repeat installation offer: no")
else:
    print("unexpected fake Codex arguments", args, file=sys.stderr)
    raise SystemExit(2)
"""
    )
    path.chmod(0o755)


def write_fake_claude(path):
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

Path(os.environ["FAKE_CLAUDE_LOG"]).write_text(json.dumps({
    "args": sys.argv[1:],
    "disable_auto_memory": os.environ.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY"),
}) + "\\n")
print("isolated Claude test")
"""
    )
    path.chmod(0o755)


def run():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        source_room = td / "source-room"
        result = run_harness(
            "--package-source",
            "source-checkout",
            "--host",
            "codex",
            "--work-dir",
            source_room,
            "--prepare-only",
        )
        assert result.returncode == 0, result.stderr + result.stdout
        project = source_room / "project"
        assert (project / "SPEC.md").is_file()
        assert (project / ".agents/skills/context-interview/SKILL.md").is_file()
        assert (project / ".agents/skills/analytics-plan/SKILL.md").is_file()
        assert (project / ".agents/skills/verify-result/SKILL.md").is_file()
        assert (project / ".agents/skills/challenge-result/SKILL.md").is_file()
        assert (project / ".agents/skills/analyst-handoff/SKILL.md").is_file()
        assert (project / ".git").is_dir()
        for private in (
            "FINDINGS.md",
            "clean-test.sh",
            ".env",
            ".envrc",
            ".nodal.local.json",
            ".mcp.json",
            ".claude/settings.local.json",
            "shorelane.context.md",
            "3y.context.md",
        ):
            assert not (project / private).exists(), private

        result = run_harness(
            "--package-source",
            "source-checkout",
            "--host",
            "none",
            "--work-dir",
            source_room,
            "--prepare-only",
        )
        assert result.returncode == 2
        assert "refusing to replace" in result.stderr
        assert (source_room / "project/SPEC.md").is_file()

        outside_temp = ROOT / "unsafe-clean-room"
        result = run_harness("--work-dir", outside_temp, "--prepare-only")
        assert result.returncode == 2
        assert "must be beneath an OS temporary directory" in result.stderr
        assert not outside_temp.exists()

        skills_install = td / "skills-install"
        (skills_install / ".agents").mkdir(parents=True)
        shutil.copytree(ROOT / "skills", skills_install / ".agents/skills")
        skills_room = td / "skills-room"
        result = run_harness(
            "--package-source",
            "skills",
            "--package-root",
            skills_install,
            "--host",
            "claude",
            "--work-dir",
            skills_room,
            "--prepare-only",
        )
        assert result.returncode == 0, result.stderr + result.stdout
        assert (skills_room / "project/.claude/skills/setup-nodal/SKILL.md").is_file()
        assert (skills_room / "project/.claude/skills/analytics-plan/SKILL.md").is_file()
        assert (skills_room / "project/.claude/skills/verify-result/SKILL.md").is_file()
        assert (skills_room / "project/.claude/skills/challenge-result/SKILL.md").is_file()
        assert (skills_room / "project/.claude/skills/analyst-handoff/SKILL.md").is_file()
        assert not (skills_room / "project/.agents").exists()

        for mode in ("claude-plugin", "codex-plugin"):
            room = td / mode
            result = run_harness(
                "--package-source",
                mode,
                "--package-root",
                ROOT,
                "--host",
                "none",
                "--work-dir",
                room,
                "--prepare-only",
            )
            assert result.returncode == 0, result.stderr + result.stdout

        fake_bin = td / "fake-bin"
        fake_bin.mkdir()
        fake_codex = fake_bin / "codex"
        write_fake_codex(fake_codex)
        fake_log = td / "fake-codex.jsonl"
        fake_env = os.environ.copy()
        fake_env.update(
            {
                "PATH": f"{fake_bin}{os.pathsep}{fake_env['PATH']}",
                "FAKE_CODEX_LOG": str(fake_log),
                "FAKE_PLUGIN_ROOT": str(ROOT),
            }
        )
        isolated_room = td / "isolated-codex-room"
        result = run_harness(
            "--package-source",
            "codex-plugin",
            "--host",
            "codex",
            "--work-dir",
            isolated_room,
            "--isolated-host",
            "--scenario",
            "browser-install-lifecycle",
            "--prepare-only",
            env=fake_env,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        isolated_home = isolated_room / "codex-home"
        assert isolated_home.is_dir()
        marker = json.loads((isolated_room / ".nodal-clean-test.json").read_text())
        assert marker["version"] == 2
        assert marker["isolated_host"] is True
        assert marker["codex_home"] == "codex-home"
        assert marker["scenario"] == "browser-install-lifecycle"
        records = [json.loads(line) for line in fake_log.read_text().splitlines()]
        assert records[0]["args"][:3] == ["plugin", "marketplace", "add"]
        assert records[1]["args"][:2] == ["plugin", "add"]
        assert records[2]["args"] == ["plugin", "list", "--json"]
        assert all(record["codex_home"] == str(isolated_home.resolve()) for record in records)
        assert "codex login --device-auth" in result.stdout
        assert "--launch-prepared" in result.stdout

        result = run_harness(
            "--launch-prepared",
            isolated_room,
            "--package-root",
            td,
            "--non-interactive",
            env=fake_env,
        )
        assert result.returncode == 2
        assert "does not match the prepared clean room" in result.stderr

        result = run_harness(
            "--launch-prepared",
            isolated_room,
            "--non-interactive",
            env=fake_env,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        assert "setup lifecycle assertions OK" in result.stdout
        assert (isolated_room / "codex-transcript.log").is_file()
        records = [json.loads(line) for line in fake_log.read_text().splitlines()]
        assert records[-1]["args"][0] == "exec"
        assert "--ignore-user-config" not in records[-1]["args"]
        assert json.loads(
            (isolated_room / "project/.nodal.local.json").read_text()
        )["browser"] == {"mode": "automated", "binding": "chrome-devtools"}

        bad_transcript = td / "bad-transcript.log"
        bad_transcript.write_text("Binding status: configured\n")
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ASSERT_SETUP),
                str(isolated_room / "project"),
                str(bad_transcript),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "session restart" in result.stderr
        assert "no-repeat installation receipt" in result.stderr

        onboarding_room = td / "agent-onboarding-room"
        result = run_harness(
            "--package-source",
            "source-checkout",
            "--host",
            "codex",
            "--work-dir",
            onboarding_room,
            "--isolated-host",
            "--scenario",
            "agent-guided-onboarding",
            "--prepare-only",
            env=fake_env,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        onboarding_project = onboarding_room / "project"
        assert (onboarding_project / "NODAL_AGENT_GUIDE.md").is_file()
        assert not (onboarding_project / "SPEC.md").exists()
        assert not (onboarding_project / ".agents/skills").exists()
        result = run_harness(
            "--launch-prepared",
            onboarding_room,
            "--non-interactive",
            env=fake_env,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        assert "agent onboarding assertions OK" in result.stdout
        assert not (onboarding_project / ".nodal.local.json").exists()
        assert not (onboarding_project / ".mcp.json").exists()
        onboarding_records = [
            json.loads(line) for line in fake_log.read_text().splitlines()
        ]
        onboarding_exec = next(
            record
            for record in reversed(onboarding_records)
            if record["args"] and record["args"][0] == "exec"
        )
        assert str((onboarding_room / "codex-home").resolve()) in onboarding_exec["args"]

        bad_onboarding = td / "bad-onboarding.log"
        bad_onboarding.write_text("Nodal analytics context is installed.\n")
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ASSERT_ONBOARDING),
                str(onboarding_project),
                str(bad_onboarding),
                str(onboarding_room / "codex-home"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "new-session boundary" in result.stderr
        assert "no duplicate installation" in result.stderr

        fake_claude = fake_bin / "claude"
        write_fake_claude(fake_claude)
        fake_claude_log = td / "fake-claude.json"
        fake_env["FAKE_CLAUDE_LOG"] = str(fake_claude_log)
        isolated_claude_room = td / "isolated-claude-room"
        result = run_harness(
            "--package-source",
            "claude-plugin",
            "--package-root",
            ROOT,
            "--host",
            "claude",
            "--work-dir",
            isolated_claude_room,
            "--isolated-host",
            "--non-interactive",
            "--skip-assert",
            env=fake_env,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        claude_record = json.loads(fake_claude_log.read_text())
        assert "--bare" in claude_record["args"]
        assert "--plugin-dir" in claude_record["args"]
        assert "--setting-sources" not in claude_record["args"]
        assert claude_record["disable_auto_memory"] == "1"
        assert (isolated_claude_room / "claude-transcript.log").is_file()

        mismatched = run_harness(
            "--package-source",
            "claude-plugin",
            "--package-root",
            ROOT,
            "--host",
            "codex",
            "--work-dir",
            td / "mismatched-host",
            "--prepare-only",
        )
        assert mismatched.returncode == 2
        assert "require --host claude" in mismatched.stderr

        generated = td / "generated-context"
        result = scaffold(generated)
        assert result.returncode == 0, result.stderr + result.stdout
        result = subprocess.run(
            [sys.executable, "-B", str(ASSERT), str(generated)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr + result.stdout

        extraction = generated / "scripts/dbt_extract.py"
        extraction.chmod(stat.S_IMODE(extraction.stat().st_mode) & ~0o111)
        result = subprocess.run(
            [sys.executable, "-B", str(ASSERT), str(generated)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "not executable: scripts/dbt_extract.py" in result.stderr

        resume_room = td / "resume-room"
        result = run_harness(
            "--package-source",
            "source-checkout",
            "--host",
            "none",
            "--work-dir",
            resume_room,
            "--prepare-only",
        )
        assert result.returncode == 0, result.stderr + result.stdout
        result = scaffold(resume_room / "analytics-context")
        assert result.returncode == 0, result.stderr + result.stdout
        result = run_harness("--resume", resume_room, "--prepare-only")
        assert result.returncode == 0, result.stderr + result.stdout
        assert (resume_room / "analytics-context/.nodal-clean-test-resume-marker").is_file()

        invalid_resume = td / "not-a-room"
        invalid_resume.mkdir()
        result = run_harness("--resume", invalid_resume, "--prepare-only")
        assert result.returncode == 2
        assert "lacks .nodal-clean-test.json" in result.stderr

        escaping_resume = td / "escaping-room"
        escaping_resume.mkdir()
        (escaping_resume / ".nodal-clean-test.json").write_text(
            '{"version": 1, "package_source": "source-checkout", "host": "none", '
            '"package_root": ".", "project": "../escape", "context_repo": "analytics-context"}\n'
        )
        result = run_harness("--resume", escaping_resume, "--prepare-only")
        assert result.returncode == 2
        assert "project path escapes the clean room" in result.stderr

    print("test_integration_harness: OK")


if __name__ == "__main__":
    run()
