"""Static native-plugin and marketplace contract tests."""
import json
import importlib.util
from pathlib import Path
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def load(relative):
    return json.loads((ROOT / relative).read_text())


def run():
    portable = load("plugin.json")
    claude = load(".claude-plugin/plugin.json")
    codex = load(".codex-plugin/plugin.json")
    for manifest in (claude, codex):
        assert manifest["name"] == "nodal-analytics"
        assert manifest["version"] == "1.7.3"
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
    assert len(openai["shortDescription"]) <= 30
    assert openai["supportURL"].startswith("https://")
    assert portable["extensions"]["com.openai"]["requires_local_executor"] is True
    assert codex["requires_local_executor"] is True
    for manifest in (portable, codex):
        onboarding = manifest["extensions"]["com.openai"]["onboardingSkill"]
        assert onboarding == "./skills/setup-nodal/SKILL.md"
        assert (ROOT / onboarding).is_file()
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
    spec = importlib.util.spec_from_file_location("submission_builder", ROOT / "scripts/build_openai_submission.py")
    builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        fake_root = temporary / "source"; fake_root.mkdir()
        for path in builder.INCLUDED:
            target = fake_root / path
            if path.suffix or path.name in {"LICENSE", "README.md"}:
                target.write_text("fixture")
            else:
                target.mkdir()
        for relative in ("skills/.DS_Store", "skills/__pycache__/cache.pyc", "skills/.pytest_cache/private",
                         "assets/__MACOSX/resource", "assets/Thumbs.db", "specs/private.md", ".env"):
            target = fake_root / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_text("excluded fixture")
        (fake_root / "skills/real.md").write_text("authored fixture")
        builder.ROOT = fake_root
        staging = temporary / "staged"; staging.mkdir()
        builder.copy_payload(staging)
        archive = temporary / "plugin.zip"; builder.write_archive(staging, archive)
        with zipfile.ZipFile(archive) as zipped:
            names = zipped.namelist()
            assert "skills/real.md" in names
            assert not any(builder.should_skip(Path(name)) for name in names)
            assert not any(name.startswith("specs/") or name == ".env" for name in names)
    print("test_plugin_package: OK")


if __name__ == "__main__":
    run()
