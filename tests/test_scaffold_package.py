"""Manifest, synchronization, and repository/installed scaffold tests."""
import importlib
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def run_command(script, *args):
    return subprocess.run(
        [sys.executable, "-B", str(script), *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def run():
    manifest = importlib.import_module("scaffold_manifest")
    sync = importlib.import_module("sync_skill_payload")

    assert manifest.ARTIFACTS
    bundle_destinations = [a.skill_source for a in manifest.ARTIFACTS]
    assert len(bundle_destinations) == len(set(bundle_destinations))
    assert any(a.target == "SPEC.md" for a in manifest.ARTIFACTS)
    assert any(a.target == "scripts/compile_skill.py" for a in manifest.ARTIFACTS)
    generated_targets = set()
    for artifact in manifest.ARTIFACTS:
        source = ROOT / artifact.root_source
        assert source.exists(), artifact.root_source
        if artifact.target is None:
            continue
        if source.is_file():
            destinations = [Path(artifact.target)]
        else:
            destinations = [Path(artifact.target) / item.relative_to(source)
                            for item in source.rglob("*") if item.is_file()
                            and item.name not in manifest.IGNORED_NAMES
                            and not item.name.endswith(manifest.IGNORED_SUFFIXES)]
        for destination in destinations:
            assert destination not in generated_targets, f"duplicate target: {destination}"
            generated_targets.add(destination)

    assert not any(sync.compare())
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        copied_skill = td / "context-interview"
        shutil.copytree(ROOT / "skills" / "context-interview", copied_skill)
        original_skill = sync.SKILL
        sync.SKILL = copied_skill
        try:
            hidden = copied_skill / "payload/template/evals/captures/.gitkeep"
            hidden.unlink()
            (copied_skill / "payload/extra.txt").write_text("extra")
            (copied_skill / "references/SPEC.md").write_text("diverged")
            executable = copied_skill / "scripts/dbt_extract.py"
            executable.chmod(stat.S_IMODE(executable.stat().st_mode) & ~0o111)
            missing, extra, divergent, mode_divergent = sync.compare()
            assert Path("payload/template/evals/captures/.gitkeep") in missing
            assert Path("payload/extra.txt") in extra
            assert Path("references/SPEC.md") in divergent
            assert Path("scripts/dbt_extract.py") in mode_divergent
        finally:
            sync.SKILL = original_skill

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        target = td / "repo-mode"
        result = run_command(SCRIPTS / "scaffold.py", target)
        assert result.returncode == 0, result.stderr + result.stdout
        for path in (
            "SPEC.md",
            "scripts/compile_skill.py",
            ".claude/skills/data-question/SKILL.md",
            "evals/captures/.gitkeep",
            ".github/workflows/validate-context.yml",
        ):
            assert (target / path).exists(), path
        compiled = subprocess.run(
            [sys.executable, str(target / "scripts/compile_skill.py"), "--help"],
            cwd=target,
            capture_output=True,
            text=True,
        )
        assert compiled.returncode == 0, compiled.stderr

        authored = target / "company/overview.md"
        authored.write_text("customer-authored")
        baseline = target / ".ci/lineage-baseline.json"
        baseline.write_text('{"customer": true}\n')
        (target / ".ci/validate.py").write_text("stale")
        result = run_command(SCRIPTS / "scaffold.py", "--upgrade", target)
        assert result.returncode == 0, result.stderr + result.stdout
        assert authored.read_text() == "customer-authored"
        assert baseline.read_text() == '{"customer": true}\n'
        assert (target / ".ci/validate.py").read_bytes() == (ROOT / ".ci/validate.py").read_bytes()

        unsafe = run_command(SCRIPTS / "scaffold.py", ROOT / "unsafe-target")
        assert unsafe.returncode != 0 and "inside the tool repository" in unsafe.stderr

        isolated = td / "installed/context-interview"
        shutil.copytree(ROOT / "skills/context-interview", isolated)
        installed_target = td / "installed-output"
        result = run_command(isolated / "scripts/scaffold.py", installed_target)
        assert result.returncode == 0, result.stderr + result.stdout
        assert (installed_target / "SPEC.md").is_file()
        unsafe = run_command(isolated / "scripts/scaffold.py", isolated / "bad-target")
        assert unsafe.returncode != 0 and "inside the installed skill directory" in unsafe.stderr

        incomplete = td / "incomplete/context-interview"
        shutil.copytree(ROOT / "skills/context-interview", incomplete)
        shutil.rmtree(incomplete / "payload/schemas")
        result = run_command(incomplete / "scripts/scaffold.py", td / "incomplete-output")
        assert result.returncode != 0 and "incomplete installed skill bundle" in result.stderr

    print("test_scaffold_package: OK")


if __name__ == "__main__":
    run()
