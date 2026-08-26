"""Project-local Nodal configuration and safe MCP merge tests."""
import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "skills/setup-nodal/scripts/nodal_config.py"
SPEC = importlib.util.spec_from_file_location("nodal_config", HELPER)
nodal_config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(nodal_config)


def sample():
    timestamp = "2026-08-25T12:00:00Z"
    return {
        "version": 1,
        "warehouse": {
            "platform": "snowflake",
            "mcp_server": "snowflake",
            "capabilities": {
                "read_query": {"status": "ok", "verified_at": timestamp},
                "metadata": {"status": "ok", "verified_at": timestamp},
                "query_history": {"status": "full", "verified_at": timestamp},
            },
        },
        "context_sources": [
            {
                "name": "analytics-context",
                "kind": "acf",
                "access": "local",
                "location": "../analytics-context",
                "binding": None,
                "repo": None,
                "authority": "confirmed",
                "status": "ok",
                "verified_at": timestamp,
                "enabled": True,
            },
            {
                "name": "business-wiki",
                "kind": "documentation",
                "access": "mcp",
                "location": None,
                "binding": "notion",
                "repo": None,
                "authority": "documented",
                "status": "ok",
                "verified_at": timestamp,
                "enabled": True,
            },
        ],
        "browser": {"binding": "chrome-devtools"},
    }


def run():
    nodal_config.validate_config(sample())
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "project"
        child = root / "a/b"
        child.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        input_path = Path(td) / "input.json"
        input_path.write_text(json.dumps(sample()))
        destination = nodal_config.write_config(root, input_path)
        assert destination == root.resolve() / ".nodal.local.json"
        assert nodal_config.discover_config(child) == destination
        assert list(json.loads(destination.read_text())) == sorted(sample())

        malformed = Path(td) / "malformed.json"
        malformed.write_text("{")
        try:
            nodal_config.load_json(malformed)
        except nodal_config.ConfigError as exc:
            assert "malformed JSON" in str(exc)
        else:
            raise AssertionError("malformed JSON accepted")

        destination.write_text("{")
        try:
            nodal_config.write_config(root, input_path)
        except nodal_config.ConfigError as exc:
            assert "malformed JSON" in str(exc)
        else:
            raise AssertionError("malformed existing config overwritten")
        destination.write_text(json.dumps(sample()))

        secret = sample()
        secret["warehouse"]["api_token"] = "do-not-store"
        try:
            nodal_config.validate_config(secret)
        except nodal_config.ConfigError as exc:
            assert "secret-like field" in str(exc)
        else:
            raise AssertionError("secret-like field accepted")

        duplicate = sample()
        duplicate["context_sources"].append(dict(duplicate["context_sources"][0]))
        try:
            nodal_config.validate_config(duplicate)
        except nodal_config.ConfigError as exc:
            assert "must be unique" in str(exc)
        else:
            raise AssertionError("duplicate context source name accepted")

        invalid_access = sample()
        invalid_access["context_sources"][0]["binding"] = "notion"
        try:
            nodal_config.validate_config(invalid_access)
        except nodal_config.ConfigError as exc:
            assert "must be null for local access" in str(exc)
        else:
            raise AssertionError("local source with MCP binding accepted")

        mcp = root / ".mcp.json"
        try:
            nodal_config.merge_mcp(root, "chrome-devtools", consent=False)
        except nodal_config.ConfigError as exc:
            assert "consent" in str(exc)
        else:
            raise AssertionError("MCP merge without consent")
        nodal_config.merge_mcp(root, "chrome-devtools", consent=True)
        first = mcp.read_bytes()
        try:
            nodal_config.merge_mcp(root, "chrome-devtools", consent=True)
        except nodal_config.ConfigError as exc:
            assert "refusing to overwrite" in str(exc)
        else:
            raise AssertionError("existing binding overwritten")
        assert mcp.read_bytes() == first

        malformed_root = Path(td) / "malformed-root"
        malformed_root.mkdir()
        (malformed_root / ".mcp.json").write_text("not-json")
        try:
            nodal_config.merge_mcp(malformed_root, "chrome-devtools", consent=True)
        except nodal_config.ConfigError as exc:
            assert "malformed JSON" in str(exc)
        else:
            raise AssertionError("malformed .mcp.json accepted")

    print("test_nodal_config: OK")


if __name__ == "__main__":
    run()
