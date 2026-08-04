"""Presence/content test for the dbt-repo sender template — stdlib only, no pytest.

The sender workflow ships as reference material (template/dbt-repo/) and is copied
into generated repos by scaffold.py; customers paste it into their dbt repo. String
checks (not YAML parsing) keep this zero-dep and dodge the YAML-1.1 `on:` key quirk.

Run: python3 tests/test_dbt_repo_template.py   (exit 0 = pass)
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "template" / "dbt-repo"


def run():
    workflow = TEMPLATE_DIR / "notify-context-repo.yml"
    readme = TEMPLATE_DIR / "README.md"
    assert workflow.exists(), f"missing {workflow}"
    assert readme.exists(), f"missing {readme}"

    text = workflow.read_text()
    # The dispatch type the context repo's drift workflow listens for.
    assert "lineage-changed" in text
    # The one customer-created secret, named consistently with the docs.
    assert "CONTEXT_DISPATCH_TOKEN" in text
    # The manifest transport: orphan branch, not the size-capped dispatch payload.
    assert "dbt-manifest" in text
    # Needs push rights in its own repo for the manifest branch.
    assert "permissions:" in text and "contents: write" in text
    # Placeholder-driven: every customer-specific value is an EDIT marker.
    assert "EDIT" in text

    doc = readme.read_text()
    assert "CONTEXT_DISPATCH_TOKEN" in doc
    assert "dbt-manifest" in doc

    print("test_dbt_repo_template: OK")


if __name__ == "__main__":
    run()
