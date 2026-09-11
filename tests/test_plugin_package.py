"""Static native-plugin and marketplace contract tests."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(relative):
    return json.loads((ROOT / relative).read_text())


def run():
    portable = load("plugin.json")
    claude = load(".claude-plugin/plugin.json")
    codex = load(".codex-plugin/plugin.json")
    for manifest in (claude, codex):
        assert manifest["name"] == "nodal-analytics"
        assert manifest["version"] == "1.5.4"
        assert manifest["license"] == "Apache-2.0"
        assert manifest["skills"] == "./skills/"
        assert "mcpServers" not in manifest
    assert portable["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert portable["name"] == claude["name"] == codex["name"]
    assert portable["version"] == claude["version"] == codex["version"]
    assert portable["license"] == "Apache-2.0"
    assert "mcpServers" not in portable
    openai = portable["extensions"]["com.openai"]["interface"]
    assert openai == codex["interface"]
    assert len(openai["defaultPrompt"]) <= 3
    assert openai["privacyPolicyURL"].startswith("https://")
    assert openai["termsOfServiceURL"].startswith("https://")
    for key in ("composerIcon", "logo"):
        assert openai[key].startswith("./assets/")
        assert (ROOT / openai[key]).is_file()
    for relative in ("docs/privacy.md", "docs/terms.md", "docs/support.md"):
        assert (ROOT / relative).is_file()
    reviewer_cases = (ROOT / "submission/openai/test-cases.md").read_text()
    assert reviewer_cases.count("### ") == 8
    assert (ROOT / "scripts/build_openai_submission.py").is_file()
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
    agent_guide = (ROOT / "docs/agent-guide.md").read_text()
    assert "codex plugin marketplace add nodal-data/nodal-context" in agent_guide
    assert "codex plugin add nodal-analytics@nodal" in agent_guide
    assert "claude plugin marketplace add nodal-data/nodal-context" in agent_guide
    assert "claude plugin install nodal-analytics@nodal" in agent_guide
    assert "npx skills@latest add nodal-data/nodal-context" in agent_guide
    assert "Install exactly one distribution" in agent_guide
    assert "start a new agent task" in agent_guide
    readme = (ROOT / "README.md").read_text()
    assert (
        "https://github.com/nodal-data/nodal-context/"
        "blob/main/docs/agent-guide.md"
    ) in readme
    print("test_plugin_package: OK")


if __name__ == "__main__":
    run()
