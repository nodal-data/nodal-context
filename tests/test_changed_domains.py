"""Behavior test for .ci/changed_domains.py mapping logic — no git, deterministic.

Builds a tiny context-repo layout in a temp dir and checks the changed-path -> domain
mapping, including the cross-cutting fail-safe. Seed->domain resolution needs PyYAML;
that one assertion self-skips if it's not installed.

Run: python3 tests/test_changed_domains.py   (exit 0 = pass)
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".ci"))
import changed_domains as cd  # noqa: E402


def _make_repo(td):
    root = Path(td)
    for name in ("orders", "billing", "_domain-template"):
        (root / "domains" / name).mkdir(parents=True)
    (root / "evals" / "seeds").mkdir(parents=True)
    (root / "entities").mkdir(parents=True)
    (root / "evals" / "seeds" / "x.seed.yaml").write_text(
        "question: q\ndomain: billing\nintent: i\n"
        "expected: {kind: sql_shape}\nprovenance: interview\nstatus: confirmed\n"
    )
    return root


def run():
    with tempfile.TemporaryDirectory() as td:
        root = _make_repo(td)
        r = lambda files: cd.domains_for_changed(files, str(root))

        # all domains discovered, template dir excluded
        assert cd.list_all_domains(str(root)) == ["billing", "orders"]

        # domain-scoped change -> just that domain
        assert r(["domains/orders/domain.yaml"]) == ["orders"]
        assert r(["domains/orders/domain.yaml", "domains/billing/metrics.yaml"]) == \
            ["billing", "orders"]

        # changes under the _domain-template are ignored
        assert r(["domains/_domain-template/domain.yaml"]) == []

        # top-level shared entities -> CROSS-CUTTING -> all domains
        assert r(["entities/customer.yaml"]) == ["billing", "orders"]

        # seed -> resolves to its own domain (needs PyYAML)
        try:
            import yaml  # noqa: F401
            assert r(["evals/seeds/x.seed.yaml"]) == ["billing"], \
                "seed should resolve to its domain field"
        except ImportError:
            print("test_changed_domains: PyYAML missing; seed-resolution assertion skipped")

        # a seed we can't resolve (missing file) -> cross-cutting fail-safe -> all domains
        assert r(["evals/seeds/ghost.seed.yaml"]) == ["billing", "orders"]

        # the --changed-files path of main() emits the GITHUB_OUTPUT line
        rc = cd.main(["--root", str(root), "--changed-files", "domains/orders/domain.yaml"])
        assert rc == 0

    print("test_changed_domains: OK")


if __name__ == "__main__":
    run()
