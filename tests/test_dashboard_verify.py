"""Structural contracts for shipped dashboard-verification playbooks."""
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/dashboard-verify"


def run():
    skill = (SKILL / "SKILL.md").read_text()
    contract = (SKILL / "references/browser-contract.md").read_text()
    sigma_path = SKILL / "references/playbooks/sigma.md"
    sigma = sigma_path.read_text()

    assert "`plotly.md` and `sigma.md`" in skill
    assert sigma_path.is_file()

    yaml_blocks = re.findall(r"```yaml\n(.*?)\n```", sigma, flags=re.DOTALL)
    replay_docs = []
    for block in yaml_blocks:
        parsed = yaml.safe_load(block)
        if isinstance(parsed, dict) and "replay" in parsed:
            replay_docs.append(parsed)
    assert len(replay_docs) == 1

    replay = replay_docs[0]["replay"]
    assert replay["tool"] == "sigma"
    assert list(replay["completion_condition"]) == ["url_match"]
    assert "/workbook/" in replay["completion_condition"]["url_match"]

    steps = replay["steps"]
    assert [step["step"] for step in steps] == list(range(1, len(steps) + 1))
    allowed_actions = {
        "navigate",
        "wait-for-condition",
        "capture-network",
        "query-dom",
        "evaluate-js",
        "click",
        "export",
        "screenshot",
    }
    for step in steps:
        assert step["action"] in allowed_actions
        assert f"| {step['action']} |" in contract or step["action"] in {
            "query-dom", "evaluate-js", "click", "export"
        }
        script_ref = step.get("args", {}).get("script_ref")
        if script_ref:
            filename, anchor = script_ref.split("#", 1)
            assert filename == sigma_path.name
            assert f"{{#{anchor}}}" in sigma

    print("test_dashboard_verify: OK")


if __name__ == "__main__":
    run()
