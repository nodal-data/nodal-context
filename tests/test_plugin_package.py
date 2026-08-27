"""Static native-plugin and marketplace contract tests."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(relative):
    return json.loads((ROOT / relative).read_text())


def run():
    claude = load(".claude-plugin/plugin.json")
    codex = load(".codex-plugin/plugin.json")
    for manifest in (claude, codex):
        assert manifest["name"] == "nodal-analytics"
        assert manifest["version"] == "1.2.0"
        assert manifest["license"] == "Apache-2.0"
        assert manifest["skills"] == "./skills/"
        assert "mcpServers" not in manifest
    assert not (ROOT / ".mcp.json").exists()

    for relative in (".claude-plugin/marketplace.json", ".agents/plugins/marketplace.json"):
        market = load(relative)
        entry = market["plugins"][0]
        assert market["name"] == "nodal"
        assert entry["name"] == "nodal-analytics"
        if "version" in entry:
            assert entry["version"] == claude["version"] == codex["version"]

    codex_entry = load(".agents/plugins/marketplace.json")["plugins"][0]
    assert codex_entry["source"] == {"source": "local", "path": "./"}
    assert codex_entry["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_USE",
    }
    assert (ROOT / ".claude/skills/setup-nodal").resolve() == ROOT / "skills/setup-nodal"
    expected_skills = {
        "analytics-plan",
        "analyst-handoff",
        "challenge-result",
        "context-interview",
        "dashboard-verify",
        "setup-nodal",
        "verify-result",
    }
    assert {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")} == expected_skills
    for name in expected_skills:
        assert (ROOT / ".claude/skills" / name).resolve() == ROOT / "skills" / name
    assert not (ROOT / ".agents/skills").exists()
    assert not (ROOT / "template/.claude/skills/data-question").exists()
    setup = (ROOT / "skills/setup-nodal/SKILL.md").read_text()
    assert "disable-model-invocation: true" in setup.split("---", 2)[1]
    assert "allow_implicit_invocation: false" in (
        ROOT / "skills/setup-nodal/agents/openai.yaml"
    ).read_text()
    assert ".nodal.local.json" in (ROOT / ".gitignore").read_text()
    assert ".nodal.local.json" in (ROOT / "template/.gitignore").read_text()
    print("test_plugin_package: OK")


if __name__ == "__main__":
    run()
