#!/usr/bin/env python3
"""CI secret-workspace preparation, sanitized publishing and owned cleanup."""
import importlib.util
import json
from pathlib import Path
import os
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("regression_ci", ROOT / ".ci/regression_ci.py")
ci = importlib.util.module_from_spec(spec); spec.loader.exec_module(ci)


def run():
    with TemporaryDirectory() as temp:
        base = Path(temp).resolve()
        source = base / "source"; source.mkdir()
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        scripts = source / "scripts"; scripts.mkdir()
        (scripts / "regress.py").write_text('''import json, os, sys
from pathlib import Path
assert 'NODAL_VERIFIED_IDENTITY' not in os.environ
if '--identity' in sys.argv:
    key = Path(sys.argv[sys.argv.index('--identity') + 1])
    assert key.stat().st_mode & 0o777 == 0o600
print(json.dumps({'schema_version': 1, 'results': [{'seed_id': 'seed:test', 'status': 'skipped', 'category': 'executor_unconfigured'}]}))
sys.exit(3)
''')
        verified = source / "evals/verified"; verified.mkdir(parents=True)
        (verified / "test.sql").write_text("PRIVATE_QUERY")
        (verified / "test.sql.age").write_text("encrypted")
        subprocess.run(["git", "add", "."], cwd=source, check=True)
        (source / "ignored-key.txt").write_text("PRIVATE_KEY")
        room = ci.prepare(source, base)
        assert not (room / "context/ignored-key.txt").exists()
        assert not (room / "context/evals/verified/test.sql").exists()
        assert (room / "context/evals/verified/test.sql.age").is_file()
        code, report = ci.execute(room, base, env={**os.environ, "NODAL_VERIFIED_IDENTITY": "synthetic-key-text"})
        assert code == 3 and report["results"][0]["status"] == "skipped"
        assert not (room / "identity.txt").exists()
        assert "PRIVATE" not in json.dumps(report)
        # Invalid output never gets published, even when the child exits zero.
        (room / "context/scripts/regress.py").write_text("print('PRIVATE_QUERY and rows')")
        code, report = ci.execute(room, base, env={**os.environ, "NODAL_VERIFIED_IDENTITY": "synthetic-key-text"})
        assert code == 2 and report["category"] == "invalid_public_report"
        assert not (room / "identity.txt").exists()
        ci.cleanup(room, base)
        assert not room.exists() and source.is_dir()
        # Never remove a caller directory, even a similarly named one.
        caller = base / "nodal-regression-caller"; caller.mkdir()
        try:
            ci.cleanup(caller, base)
        except ValueError:
            pass
        else:
            raise AssertionError("caller-owned directory was accepted for cleanup")
        assert caller.is_dir()
    workflow = (ROOT / ".github/workflows/verified-regression.yml").read_text()
    assert "workflow_dispatch" in workflow and "github.event.repository.default_branch" in workflow
    assert "if: always()" in workflow and "persist-credentials: false" in workflow
    # Inspect parsed triggers/actions, not comments that name forbidden patterns.
    import yaml
    data = yaml.safe_load(workflow)
    triggers = data.get("on", data.get(True))
    assert set(triggers) == {"workflow_dispatch"}
    steps = data["jobs"]["regression"]["steps"]
    assert not any("upload-artifact" in step.get("uses", "") or "github-script" in step.get("uses", "") for step in steps)
    print("test_regression_ci: OK")


if __name__ == "__main__":
    run()
