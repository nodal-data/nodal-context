"""Offline acquisition tests; local disposable Git only, no network or credentials."""
import base64
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".ci"))
import collect_manifests as cm
import drift

RAW = b'{"nodes": {}, "sources": {}}'
GOOD = base64.b64encode(RAW).decode()


def rejects(operation):
    try:
        operation()
    except ValueError:
        return
    raise AssertionError("invalid input accepted")


def run():
    with tempfile.TemporaryDirectory(prefix="acf-collect-test-") as tmp:
        room = Path(tmp)
        out = room / "path with spaces"
        event = {"client_payload": {"manifests": {
            "dbt_core": GOOD, "broken": "!!notb64", "../../escape": GOOD, "not_dbt": GOOD,
            "odd / --manifest=x=y": GOOD,
        }}}
        sources = {"dbt_core", "broken", "odd / --manifest=x=y"}
        acquired = cm.from_payload(event, out, sources)
        assert set(acquired) == {"dbt_core", "odd / --manifest=x=y"}
        assert all(Path(p).parent == out.resolve() and Path(p).read_bytes() == RAW for p in acquired.values())
        assert not (room / "escape.json").exists()
        assert len(list(out.iterdir())) == 2
        for event in ({}, [], {"client_payload": []}, {"client_payload": {"manifests": []}}):
            assert cm.from_payload(event, out, sources) == {}
        for raw in (b'null', b'[]', b'{"nodes": []}', b'{"nodes": {}, "nodes": {}}',
                    b'{"nodes": {}, "sources": null}', b'{"nodes": {}, "x": NaN}'):
            bad = {"client_payload": {"manifests": {"dbt_core": base64.b64encode(raw).decode()}}}
            assert cm.from_payload(bad, out, sources) == {}
        with patch.object(cm, "MAX_MANIFEST_BYTES", 5):
            assert cm.from_payload({"client_payload": {"manifests": {"dbt_core": GOOD}}}, out, sources) == {}
        external = room / "external"
        external.write_text("do not overwrite")
        cm.destination(out, "link").symlink_to(external)
        assert cm.from_payload({"client_payload": {"manifests": {"link": GOOD}}}, out, {"link"}) == {}
        assert external.read_text() == "do not overwrite"

        mapping = room / "map.json"
        mapping.write_text(json.dumps(acquired))
        assert drift._parse_manifest_args([], mapping) == acquired
        rejects(lambda: drift._parse_manifest_args(["dbt_core=other"], mapping))
        mapping.write_text('{"x":"one", "x":"two"}')
        rejects(lambda: drift._parse_manifest_args([], mapping))
        mapping.write_text('[]')
        rejects(lambda: drift._parse_manifest_args([], mapping))

        config = room / "context.config.yaml"
        config.write_text('version: "0.3"\nwarehouse: test\nlineage_sources:\n  - {id: core, type: dbt}\n')
        event_path = room / "event.json"
        event_path.write_text(json.dumps({"client_payload": {"manifests": {"core": GOOD}}}))
        output = io.StringIO()
        with redirect_stdout(output):
            assert cm.main(["--config", str(config), "--event-path", str(event_path), "--out-dir", str(out)]) == 0
        assert set(json.loads(output.getvalue())) == {"core"}
        for bad in ('version: "0.2"\nwarehouse: test\nlineage_sources: []\n',
                    'version: "0.3"\nversion: "0.3"\nwarehouse: test\nlineage_sources: []\n',
                    'version: "0.3"\nwarehouse: test\nlineage_sources:\n - {id: core, type: dbt}\n - {id: core, type: dbt}\n'):
            config.write_text(bad)
            with redirect_stdout(io.StringIO()):
                assert cm.main(["--config", str(config), "--out-dir", str(out)]) == 2

        # Real local Git: only a regular manifest blob can be acquired; checkout is
        # disabled so other tracked source contents are never materialized/executed.
        source = room / "source"
        source.mkdir()
        def git(*args):
            return subprocess.run(["git", *args], cwd=source, check=True, capture_output=True)
        git("init", "-b", "main")
        git("config", "user.name", "Synthetic Test")
        git("config", "user.email", "synthetic@example.invalid")
        (source / "manifest.json").write_bytes(RAW)
        (source / "link.json").symlink_to("manifest.json")
        (source / "not-json.json").write_text("not json")
        git("add", ".")
        git("commit", "-m", "synthetic fixture")
        src = {"id": "local", "type": "dbt", "repo": "owner/repo", "ref": "main", "manifest_path": "manifest.json"}
        with patch.object(cm, "_clone_url", return_value=str(source)):
            path = cm.clone_source(src, out)
            assert path and Path(path).read_bytes() == RAW
            for name in ("link.json", "not-json.json", "absent.json", "../external", "/outside"):
                assert cm.clone_source({**src, "manifest_path": name}, out) is None
            with patch.object(cm, "MAX_MANIFEST_BYTES", 4):
                assert cm.clone_source(src, out) is None

        # A failing Git process must not leak its stdout/stderr/argv credential.
        token = "SYNTHETIC_PRIVATE_TOKEN"
        err = io.StringIO()
        failure = subprocess.CalledProcessError(1, ["git"], stderr=token.encode())
        with patch.object(cm.subprocess, "run", side_effect=failure) as mocked, redirect_stderr(err):
            assert cm.clone_source(src, out, token) is None
        call = mocked.call_args
        assert token not in repr(call.args) and token not in err.getvalue()
        assert "--no-checkout" in call.args[0]
        assert call.kwargs["env"]["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
        assert "DBT_REPO_TOKEN" not in call.kwargs["env"]
        with patch.dict(os.environ, {"GIT_CONFIG_COUNT": "10", "GIT_CONFIG_KEY_0": "unsafe"}):
            assert "GIT_CONFIG_KEY_0" not in cm._git_env("")

    for repo in ("owner/repo", "github.com/owner/repo", "https://github.com/owner/repo.git"):
        assert cm._clone_url(repo) == "https://github.com/owner/repo.git"
    for repo in ("https://evil.invalid/o/r", "https://token@github.com/o/r", "owner/../repo", "-x", "file:///tmp/x"):
        rejects(lambda: cm._clone_url(repo))
    for path in ("../x", "/x", "a/../x", "a//x", "a\\x", ".git/config", "x\n"):
        rejects(lambda: cm._manifest_path(path))
    print("test_collect_manifests: OK")


if __name__ == "__main__":
    run()
