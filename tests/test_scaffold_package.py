"""Manifest, synchronization, and repository/installed scaffold tests."""
import importlib
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import yaml

from acf_fixtures import context, metric, method, seed, write, METHOD_BODY


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


CUSTOMER_WORKFLOWS = ("context-approval.yml", "context-drift.yml")


def check_customer_workflows(target):
    for name in CUSTOMER_WORKFLOWS:
        expected = ROOT / "template/.github/workflows" / name
        installed = target / ".github/workflows" / name
        assert installed.read_bytes() == expected.read_bytes(), name


def run():
    manifest = importlib.import_module("scaffold_manifest")
    sync = importlib.import_module("sync_skill_payload")

    assert manifest.ARTIFACTS
    # Shipping customer governance must not activate it in the package repo.
    active_workflows = list((ROOT / ".github/workflows").glob("*.y*ml"))
    for workflow in active_workflows:
        assert yaml.safe_load(workflow.read_text()).get("name") not in {
            "context-approval", "context-drift"
        }, workflow
    for name in CUSTOMER_WORKFLOWS:
        assert not (ROOT / ".github/workflows" / name).exists()
    bundle_destinations = [a.skill_source for a in manifest.ARTIFACTS]
    assert len(bundle_destinations) == len(set(bundle_destinations))
    assert any(a.target == "SPEC.md" for a in manifest.ARTIFACTS)
    spec = next(a for a in manifest.ARTIFACTS if a.target == "SPEC.md")
    assert spec.root_source == "skills/context-interview/references/SPEC.md"
    # Sync must preserve the canonical reference when source and destination
    # are the same file, and must not read the ignored root copy.
    with tempfile.TemporaryDirectory() as td:
        source_root = Path(td)
        skill_root = source_root / "skills/context-interview"
        reference = source_root / spec.root_source
        reference.parent.mkdir(parents=True)
        reference.write_text("canonical specification")
        (source_root / "SPEC.md").write_text("local notes")
        with patch.object(sync, "ROOT", source_root), patch.object(sync, "SKILL", skill_root), \
                patch.object(sync, "ARTIFACTS", (spec,)):
            sync.write()
            assert sync.check() == 0
        assert reference.read_text() == "canonical specification"
        assert (source_root / "SPEC.md").read_text() == "local notes"
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
            stray_cache = copied_skill / "payload/.pytest_cache"
            stray_cache.mkdir()
            (stray_cache / "README.md").write_text("dev-time cache artifact")
            missing, extra, divergent, mode_divergent = sync.compare()
            assert Path("payload/template/evals/captures/.gitkeep") in missing
            assert Path("payload/extra.txt") in extra
            assert Path("payload/.pytest_cache/README.md") not in extra
            assert Path("references/SPEC.md") in divergent
            assert Path("scripts/dbt_extract.py") in mode_divergent
        finally:
            sync.SKILL = original_skill

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        target = td / "repo-mode"
        result = run_command(SCRIPTS / "scaffold.py", target)
        assert result.returncode == 0, result.stderr + result.stdout
        check_customer_workflows(target)
        for path in (
            "SPEC.md",
            "scripts/compile_skill.py",
            "evals/captures/.gitkeep",
            ".github/workflows/validate-context.yml",
        ):
            assert (target / path).exists(), path
        assert not (target / ".claude/skills/data-question").exists()
        assert "Answering a data question" in (target / "AGENTS.md").read_text()
        assert "Answering a data question" in (target / "CLAUDE.md").read_text()
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
        for name in CUSTOMER_WORKFLOWS:
            (target / ".github/workflows" / name).write_text("stale customer workflow")
        result = run_command(SCRIPTS / "scaffold.py", "--upgrade", target)
        assert result.returncode == 0, result.stderr + result.stdout
        check_customer_workflows(target)
        assert authored.read_text() == "customer-authored"
        assert baseline.read_text() == '{"customer": true}\n'

        # A copy failure after processing .ci must never transiently overwrite the
        # customer's baseline; restoration at the end of the upgrade is too late.
        scaffold = importlib.import_module("scaffold")
        real_copy = scaffold._copy
        baseline_stat = baseline.stat()
        def fail_after_ci(source, destination, preserved=frozenset()):
            real_copy(source, destination, preserved)
            if destination == target / ".ci":
                raise OSError("injected support-copy failure")
        with patch.object(scaffold, "_copy", side_effect=fail_after_ci):
            try:
                scaffold._copy_artifacts(target, tuple(a for a in manifest.ARTIFACTS if a.target == ".ci"))
            except OSError as exc:
                assert str(exc) == "injected support-copy failure"
            else:
                raise AssertionError("expected injected copy failure")
        assert baseline.read_text() == '{"customer": true}\n'
        assert baseline.stat().st_mtime_ns == baseline_stat.st_mtime_ns
        assert baseline.stat().st_mode == baseline_stat.st_mode
        assert (target / ".ci/validate.py").read_bytes() == (ROOT / ".ci/validate.py").read_bytes()
        reports = list((target / ".nodal/migrations").glob("scaffold-*.md"))
        assert len(reports) == 1 and "private template review" in result.stdout
        review = reports[0].read_text()
        assert "customer-authored" in review and "authored/company/overview.md" in review
        assert "do not" in review and "apply this report as a patch" in review
        assert reports[0].stat().st_mode & 0o077 == 0
        repeated = run_command(SCRIPTS / "scaffold.py", "--upgrade", target)
        assert repeated.returncode == 0, repeated.stderr
        assert list((target / ".nodal/migrations").glob("scaffold-*.md")) == reports

        # A populated repo need not keep unused authoring templates or .gitkeeps.
        shutil.rmtree(target / "domains/_domain-template")
        (target / "methods/_method-template.md").unlink()
        (target / "evals/captures/.gitkeep").unlink()
        result = run_command(SCRIPTS / "scaffold.py", "--upgrade", target)
        assert result.returncode == 0, result.stderr + result.stdout
        assert not (target / "domains/_domain-template").exists()
        assert not (target / "methods/_method-template.md").exists()
        assert authored.read_text() == "customer-authored"
        assert baseline.read_text() == '{"customer": true}\n'

        unsafe = run_command(SCRIPTS / "scaffold.py", ROOT / "unsafe-target")
        assert unsafe.returncode != 0 and "inside the tool repository" in unsafe.stderr

        isolated = td / "installed/context-interview"
        shutil.copytree(ROOT / "skills/context-interview", isolated)
        installed_target = td / "installed-output"
        result = run_command(isolated / "scripts/scaffold.py", installed_target)
        assert result.returncode == 0, result.stderr + result.stdout
        check_customer_workflows(installed_target)
        assert (installed_target / "SPEC.md").is_file()
        converter = subprocess.run(
            [sys.executable, str(isolated / "scripts/split_metrics.py"), "--help"],
            cwd=td, capture_output=True, text=True,
        )
        assert converter.returncode == 0, converter.stderr
        for script in ("import_notebook.py", "verify_notebook.py", "notebook_reference.py", "verified.py", "regress.py", "review_observed.py", "match_question.py", "simulated_analyst.py"):
            result = subprocess.run([sys.executable, str(isolated / "scripts" / script), "--help"],
                                    cwd=td, capture_output=True, text=True)
            assert result.returncode == 0, (script, result.stderr)
            result = subprocess.run([sys.executable, str(installed_target / "scripts" / script), "--help"],
                                    cwd=td, capture_output=True, text=True)
            assert result.returncode == 0, (script, result.stderr)
        # Old-version upgrade refusal happens before any support-file mutation.
        marker = installed_target / "context.config.yaml"
        original_marker = marker.read_text()
        marker.write_text(original_marker.replace("'0.3'", "'0.2'").replace('"0.3"', '"0.2"'))
        before = {p.relative_to(installed_target): p.read_bytes()
                  for p in installed_target.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
        refusal = run_command(isolated / "scripts/scaffold.py", "--upgrade", installed_target)
        assert refusal.returncode != 0 and "migration required" in refusal.stderr
        after = {p.relative_to(installed_target): p.read_bytes()
                 for p in installed_target.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
        assert before == after
        marker.write_text(original_marker)
        # Version 0.3 with a legacy wrapper is also rejected without copying files.
        legacy = installed_target / "domains/legacy/metrics.yaml"
        legacy.parent.mkdir()
        legacy.write_text("metrics: []\n")
        sentinel = installed_target / ".ci/validate.py"
        sentinel.write_text("preserve on refused upgrade")
        refusal = run_command(isolated / "scripts/scaffold.py", "--upgrade", installed_target)
        assert refusal.returncode != 0 and "no files changed" in refusal.stderr
        assert sentinel.read_text() == "preserve on refused upgrade"

        # Complete standalone migration with the installed converter, followed by
        # an upgrade of populated 0.3 context. No old runtime is invoked.
        legacy.unlink()
        context(installed_target)
        config = yaml.safe_load(marker.read_text())
        config["version"] = "0.2"
        write(installed_target, "context.config.yaml", config)
        draft_metric = metric(status="draft")
        draft_metric.pop("approver"); draft_metric.pop("confirmed_at")
        legacy = write(installed_target, "domains/sales/metrics.yaml", {"metrics": [draft_metric]})
        old_bytes = legacy.read_bytes()
        def convert(*options):
            return subprocess.run([sys.executable, str(isolated / "scripts/split_metrics.py"),
                                   str(legacy.parent), *options], cwd=td, capture_output=True, text=True)
        preview = convert("--check")
        assert preview.returncode == 0, preview.stderr
        assert legacy.read_bytes() == old_bytes and not (legacy.parent / "metrics").exists()
        converted = convert()
        assert converted.returncode == 0, converted.stderr
        assert not legacy.exists()
        migrated = installed_target / "domains/sales/metrics/orders.yaml"
        migrated_data = yaml.safe_load(migrated.read_text())
        assert migrated_data == draft_metric  # no fabricated approval or semantic change
        assert yaml.safe_load(marker.read_text())["version"] == "0.2"
        assert any(p.read_bytes() == old_bytes for p in (installed_target / ".nodal/migrations").rglob("*") if p.is_file())
        refusal = run_command(isolated / "scripts/scaffold.py", "--upgrade", installed_target)
        assert refusal.returncode != 0 and sentinel.read_text() == "preserve on refused upgrade"
        # Explicit synthetic human review is separate from conversion/upgrade.
        config["version"] = "0.3"
        write(installed_target, "context.config.yaml", config)
        write(installed_target, "domains/sales/metrics/orders.yaml", metric())
        write(installed_target, "methods/repeat.md", method(), METHOD_BODY)
        write(installed_target, "evals/seeds/orders.seed.yaml", seed())
        preserved = {
            ".ci/lineage-baseline.json": '{"reviewed_baseline": true}\n',
            ".gitignore": ".nodal/\nevals/verified/*.sql\nevals/observed/\n# Customer ignores\nprivate/\n",
            "AGENTS.md": "# Customer agent instructions\nRetain this instruction.\n",
            "CLAUDE.md": "# Customer host instructions\n",
            ".nodal.local.json": '{"version": 1, "classification": "fixture"}\n',
            "evals/verified/orders.sql": "SELECT COUNT(*) FROM orders WHERE test = false;\n",
            "evals/verified/orders.sql.age": "synthetic ciphertext-preservation fixture, not decryptable\n",
            "evals/observed/queue.jsonl": "",
        }
        for path, contents in preserved.items():
            destination = installed_target / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(contents)
        for path in ("context.config.yaml", "domains/sales/metrics/orders.yaml",
                     "methods/repeat.md", "evals/seeds/orders.seed.yaml"):
            preserved[path] = (installed_target / path).read_text()
        for scaffold_script in (isolated / "scripts/scaffold.py", SCRIPTS / "scaffold.py"):
            upgraded = run_command(scaffold_script, "--upgrade", installed_target)
            assert upgraded.returncode == 0, upgraded.stderr + upgraded.stdout
            assert all((installed_target / p).read_text() == text for p, text in preserved.items())
            assert (installed_target / ".ci/validate.py").read_bytes() == (ROOT / ".ci/validate.py").read_bytes()
        checked = run_command(isolated / "scripts/scaffold.py", "--check", installed_target)
        assert checked.returncode == 0, checked.stderr + checked.stdout
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
