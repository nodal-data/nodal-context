"""Behavior test for scripts/compile_skill.py — ACF repo -> agent data skill.

Needs PyYAML; self-skips with exit 0 if it's absent (CI installs it).

Run: python3 tests/test_compile_skill.py   (exit 0 = pass/skip)
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

HEALTHCARE = ROOT / "examples" / "example-healthcare-company"


def run_tests():
    try:
        import yaml  # noqa: F401
    except ImportError:
        print("test_compile_skill: PyYAML missing; skipped")
        return

    import compile_skill
    from eval_harness import adapters

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        # --- compile the worked example ------------------------------------------
        skill_dir, stats = compile_skill.compile_skill(
            HEALTHCARE, td / "out", None, include_drafts=False)
        assert stats["domains"] == ["session-financials"], stats
        skill_md = (skill_dir / "SKILL.md").read_text()
        # frontmatter: name slugged from the overview title, description triggers
        assert skill_md.startswith("---\nname: example-healthcare-company-data-analyst\n")
        assert "session-financials" in skill_md            # nav table + description
        assert "Compiled snapshot — not the source of truth" in skill_md
        assert "How to answer with this skill" in skill_md
        assert "delivers ABA / behavioral health care" in skill_md   # overview inlined
        ref = (skill_dir / "references" / "session-financials.md").read_text()
        assert "Payer X" in ref and "45-day" in ref        # reference.md verbatim
        assert "FCT_SESSION_FINANCIALS" in ref             # canonical table header
        assert "Grain:" in ref and "note" in ref

        # --- round-trip: the harness's skill adapter reads the compiled output ----
        # with the SAME domain names as the ACF source, so ACF seeds grade it as-is.
        acf_ncr = adapters.get_builder("acf")(HEALTHCARE)
        skill_ncr = adapters.get_builder("skill")(skill_dir)
        assert skill_ncr.domains() == acf_ncr.domains() == ["session-financials"]
        ctx = skill_ncr.context_for("session-financials")
        assert "Payer X" in ctx and "45-day" in ctx and "exclude" in ctx.lower()

        # --- drafts excluded by default, kept (marked) with include_drafts --------
        repo = td / "acme-context"
        (repo / "company").mkdir(parents=True)
        (repo / "entities").mkdir()
        (repo / "domains" / "billing").mkdir(parents=True)
        (repo / "company" / "overview.md").write_text("# Acme Corp — Overview\nSells widgets.")
        (repo / "company" / "terminology.md").write_text("# Terminology\nARR: annual run rate.")
        (repo / "entities" / "payers.yaml").write_text(
            "entities:\n"
            "  - name: payer\n    description: Who reimburses.\n    status: confirmed\n"
            "    important: State-specific; never aggregate across states.\n"
            "    mappings: {BCBS: Blue Cross}\n"
            "  - name: plan_tier\n    description: TBD.\n    status: draft\n")
        (repo / "domains" / "billing" / "domain.yaml").write_text(
            "name: billing\nsummary: Invoices and collections.\nstatus: confirmed\n"
            "grain: one row per invoice\ntables: {canonical: FCT_INVOICES}\n")
        (repo / "domains" / "billing" / "reference.md").write_text(
            "# Billing Reference\n- IF question is about refunds → DO NOT use FCT_INVOICES.")
        (repo / "domains" / "billing" / "metrics.yaml").write_text(
            "metrics:\n"
            "  - name: collection_rate\n    definition: Collected over billed.\n"
            "    status: confirmed\n    caveats: [exclude invoices <30 days old]\n"
            "  - name: dso\n    definition: TBD.\n    status: draft\n")
        skill_dir, stats = compile_skill.compile_skill(repo, td / "out2", None, False)
        assert stats["domains"] == ["billing"] and stats["drafts_excluded"] == 2
        ents = (skill_dir / "references" / "entities.md").read_text()
        assert "never aggregate across states" in ents and "plan_tier" not in ents
        billing = (skill_dir / "references" / "billing.md").read_text()
        assert "collection_rate" in billing and "exclude invoices <30 days old" in billing
        assert "dso" not in billing
        assert "2 draft" in (skill_dir / "SKILL.md").read_text()   # stamp names the gap
        skill_dir, stats = compile_skill.compile_skill(repo, td / "out3", None, True)
        assert stats["drafts_excluded"] == 0
        assert "dso" in (skill_dir / "references" / "billing.md").read_text()
        assert "draft — unconfirmed" in (skill_dir / "references" / "billing.md").read_text()

        # --- zip packaging feeds the skill adapter directly -----------------------
        zpath = compile_skill.package_zip(skill_dir)
        ncr = adapters.get_builder("skill")(zpath)
        assert ncr.domains() == ["billing"]
        zctx = ncr.context_for("billing")
        assert "refunds" in zctx                       # per-domain reference travels
        assert "never aggregate across states" in zctx  # entities.md shared into domain
        assert "annual run rate" in zctx                # SKILL.md terminology shared

        # --- CLI: name override + refusal outside an ACF repo ---------------------
        rc = compile_skill.main([str(repo), "--out", str(td / "out4"), "--name", "Acme Inc"])
        assert rc == 0
        assert (td / "out4" / "acme-inc-data-analyst" / "SKILL.md").exists()
        try:
            compile_skill.main([str(td / "not-a-repo")])
            assert False, "expected SystemExit for a non-ACF directory"
        except SystemExit as e:
            assert "domains/" in str(e.code)

    print("test_compile_skill: OK")


if __name__ == "__main__":
    run_tests()
