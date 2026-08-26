"""Offline safety, packaging-mode, assertion, and resume tests for clean_test."""

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


def run_harness(*args):
    return subprocess.run(
        [sys.executable, "-B", str(HARNESS), *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def scaffold(target):
    return subprocess.run(
        [sys.executable, "-B", str(ROOT / "scripts/scaffold.py"), str(target)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


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
