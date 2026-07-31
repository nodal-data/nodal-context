"""Behavior test for .ci/validate.py.

Needs jsonschema + pyyaml + referencing (the validator's real deps); self-skips with
exit 0 if they aren't installed, so a minimal env doesn't spuriously fail. CI installs
them (`pip install jsonschema pyyaml`).

Run: python3 tests/test_validate.py   (exit 0 = pass/skip)
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".ci"))
import validate  # noqa: E402


def run():
    try:
        import jsonschema, yaml, referencing  # noqa: F401
    except ImportError:
        print("test_validate: deps not installed; skipped")
        return

    os.chdir(ROOT)  # make discovery + default schemas/ resolution deterministic

    # --- auto-discover this repo: examples strict + template structural => clean ---
    assert validate.main([]) == 0, "expected this repo to validate clean"

    # --- one example as an explicit strict root => clean ---
    assert validate.main(["examples/example-fintech-company", "--schemas", "schemas"]) == 0

    # --- strict failure: a bad enum value in a copied example domain.yaml ---
    with tempfile.TemporaryDirectory() as td:
        ctx = Path(td) / "ctx"
        shutil.copytree(ROOT / "examples" / "example-fintech-company", ctx)
        dom = ctx / "domains" / "lending-performance" / "domain.yaml"
        dom.write_text(dom.read_text().replace("status: confirmed", "status: nope"))
        assert validate.main([str(ctx), "--schemas", "schemas"]) == 1, \
            "expected strict validation to fail on a bad status enum"

    # --- lineage warning: local repo path warns but does not fail ---
    with tempfile.TemporaryDirectory() as td:
        ctx = Path(td) / "ctx"
        shutil.copytree(ROOT / "examples" / "example-fintech-company", ctx)
        cfg = ctx / "context.config.yaml"
        cfg.write_text(cfg.read_text().replace(
            "repo: github.com/", "repo: local:/Users/someone/", 1))
        import yaml as y
        warns = validate.lineage_repo_warnings(validate.discover_docs(ctx), y)
        assert warns and "local repo path" in warns[0], \
            f"expected a local-repo-path warning, got {warns}"
        assert validate.main([str(ctx), "--schemas", "schemas"]) == 0, \
            "a local repo path must warn, not fail"

    # --- entity placement: per-domain-only entities warn but do not fail ---
    ENTITY_DOC = ("entities:\n"
                  "  - name: customer\n"
                  "    description: Paying customer.\n"
                  "    status: confirmed\n")
    with tempfile.TemporaryDirectory() as td:
        ctx = Path(td) / "ctx"
        shutil.copytree(ROOT / "examples" / "example-fintech-company", ctx)
        dom = ctx / "domains" / "lending-performance"
        (dom / "entities.yaml").write_text(ENTITY_DOC)
        import yaml as y
        warns = validate.entity_placement_warnings(validate.discover_docs(ctx), y, ctx)
        assert warns and "entities/<group>.yaml" in warns[0], \
            f"expected a promotion warning, got {warns}"
        assert validate.main([str(ctx), "--schemas", "schemas"]) == 0, \
            "per-domain-only entities must warn, not fail"

        # a real top-level entities file silences the promotion warning
        (ctx / "entities").mkdir(exist_ok=True)
        (ctx / "entities" / "customers.yaml").write_text(ENTITY_DOC)
        warns = validate.entity_placement_warnings(validate.discover_docs(ctx), y, ctx)
        assert not warns, f"expected no warning once entities/ is real, got {warns}"

        # the same entity name in two domains is cross-domain by definition
        second = ctx / "domains" / "collections"
        second.mkdir()
        (second / "entities.yaml").write_text(ENTITY_DOC)
        warns = validate.entity_placement_warnings(validate.discover_docs(ctx), y, ctx)
        assert any("cross-domain by definition" in w for w in warns), \
            f"expected a duplicate-name warning, got {warns}"

    # --- canonical filenames: a .yml near-miss warns but does not fail ---
    with tempfile.TemporaryDirectory() as td:
        ctx = Path(td) / "ctx"
        shutil.copytree(ROOT / "examples" / "example-fintech-company", ctx)
        (ctx / "domains" / "lending-performance" / "metrics.yml").write_text(
            "metrics: []\n")
        warns = validate.canonical_name_warnings(ctx)
        assert warns and "rename to .yaml" in warns[0], \
            f"expected a near-miss filename warning, got {warns}"
        assert validate.main([str(ctx), "--schemas", "schemas"]) == 0, \
            "a .yml near-miss must warn, not fail"

    # --- structural failure: unknown field in a copied template doc ---
    with tempfile.TemporaryDirectory() as td:
        tpl = Path(td) / "template"
        shutil.copytree(ROOT / "template", tpl)
        d = tpl / "domains" / "_domain-template" / "domain.yaml"
        d.write_text(d.read_text() + "\nbogus_unknown_field: 1\n")
        # discover_docs + check_structure directly (structural mode is what auto-discover
        # applies to template/)
        import yaml as y
        raw = {k: __import__("json").load(open(ROOT / "schemas" / v))
               for k, v in validate.SCHEMA_FILE.items()}
        errs = validate.check_structure(validate.discover_docs(tpl), raw, y)
        assert any("bogus_unknown_field" in e for e in errs), \
            f"expected structural check to flag the stray field, got {errs}"

    print("test_validate: OK")


if __name__ == "__main__":
    run()
