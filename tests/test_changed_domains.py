"""Base/head graph routing, cross-domain dependencies and conservative fallback."""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".ci"))
from acf_fixtures import context, domain, metric, method, seed, write, METHOD_BODY
from acf_runtime.loader import load_context
from acf_runtime.impact import path_impact, revisions, snapshot, lineage_impact
import changed_domains as cd


def fixture(root):
    context(root)
    for name in ("billing", "retention", "unrelated"):
        domain(root, name)
    write(root, "domains/sales/metrics/orders.yaml", metric())
    write(root, "domains/billing/metrics/billed.yaml", metric("billed", lineage="inherit",
        expression={"measure": "metric(sales.orders)", "allowed_dimensions": ["channel"]}))
    write(root, "domains/unrelated/metrics/accounts.yaml", metric("accounts",
        lineage=[{"source": "dbt", "models": ["accounts"]}]))
    data = method(); data.update(domain="retention", metrics=["sales.orders"])
    write(root, "methods/repeat.md", data, METHOD_BODY)
    write(root, "evals/seeds/billed.seed.yaml", seed(domain="billing", ir={"metric": "billed"},
          verified_query_file="evals/verified/billed.sql"))
    write(root, "evals/seeds/repeat.seed.yaml", seed(domain="retention", ir={"method": "repeat",
          "metrics": ["sales.orders"], "parameters": {"window": "last_month"}}))
    registry = load_context(root)
    assert not registry.errors, list(map(str, registry.errors))


def git(root, *args):
    command = ["git", "-C", str(root), *args]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def save(root, message):
    git(root, "add", ".")
    git(root, "-c", "user.name=Fictional Test", "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


def run():
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory) / "base"; base.mkdir(); fixture(base)
        head = Path(directory) / "head"; shutil.copytree(base, head)
        route = lambda paths: cd.domains_for_changed(paths, head, base)
        assert route(["domains/sales/metrics/orders.yaml"]) == ["billing", "retention", "sales"]
        assert route(["methods/repeat.md"]) == ["retention"]
        assert route(["evals/verified/billed.sql.age"]) == ["billing"]
        assert route(["evals/verified/billed.sql.sops"]) == ["billing"]
        assert route(["evals/seeds/repeat.seed.yaml"]) == ["retention"]
        assert route(["company/terminology.md"]) == ["billing", "retention", "sales", "unrelated"]
        assert route(["schemas/metric.schema.json"]) == ["billing", "retention", "sales", "unrelated"]
        assert route(["domains/_domain-template/domain.yaml", "README.md"]) == []
        assert route(["entities/customer.yaml"]) == ["billing", "retention", "sales", "unrelated"]
        # Filter-only shared references must propagate just like lineage fragments.
        for target in (base, head):
            write(target, "domains/sales/metrics/_shared.yaml", {"filter_sets": {
                "eligible": {"filters": [{"field": "test", "op": "=", "value": False, "reason": "Exclude tests"}]}}})
            fragmented = metric(); fragmented["expression"].pop("mandatory_filters")
            fragmented["expression"]["include_filters"] = ["eligible"]
            write(target, "domains/sales/metrics/orders.yaml", fragmented)
        assert route(["domains/sales/metrics/_shared.yaml"]) == ["billing", "retention", "sales"]
        # Blocking decisions are impact edges, not lineage inheritance edges.
        for target in (base, head):
            blocker = metric("policy", lineage=[{"source": "dbt", "models": ["policy"]}],
                open_decisions=[{"id": "scope", "question": "Which scope?", "blocks": ["methods/repeat"]}])
            write(target, "domains/unrelated/metrics/policy.yaml", blocker)
        assert route(["domains/unrelated/metrics/policy.yaml"]) == ["retention", "unrelated"]
        assert load_context(head).nodes["method:repeat"].lineage == {("dbt", "orders")}
        result = path_impact(head, ["methods/repeat.md"])
        assert result["fallback"] and "base graph unavailable" in result["reasons"][0]
        registry = load_context(head)
        impact = lineage_impact(registry, {("dbt", "orders")})
        item = next(item for item in impact["objects"] if item["id"] == "seed:repeat.seed.yaml")
        # Method seeds name resolved metrics directly, so their shortest path may
        # bypass the method; the method itself must also appear as affected.
        assert item["dependency_path"] == ["metric:sales.orders", "seed:repeat.seed.yaml"]
        assert next(i for i in impact["objects"] if i["id"] == "method:repeat")["dependency_path"] == ["metric:sales.orders", "method:repeat"]
        # Renamed/deleted objects are still found in the base graph.
        (head / "evals/seeds/repeat.seed.yaml").rename(head / "evals/seeds/new-name.seed.yaml")
        assert route(["evals/seeds/repeat.seed.yaml", "evals/seeds/new-name.seed.yaml"]) == ["retention"]
        # Moving method ownership reaches both old and new domains.
        data = method(); data.update(domain="billing", metrics=["sales.orders"])
        write(head, "methods/repeat.md", data, METHOD_BODY)
        assert route(["methods/repeat.md"]) == ["billing", "retention"]
        # Broken graph after deletion falls back to every available domain.
        (head / "domains/sales/metrics/orders.yaml").unlink()
        result = path_impact(head, ["domains/sales/metrics/orders.yaml"], base_root=base)
        assert result["fallback"] and result["domains"] == ["billing", "retention", "sales", "unrelated"]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory); fixture(root)
        git(root, "init", "--quiet")
        old = save(root, "fictional base context")
        data = metric(definition="Changed fictional order scope")
        write(root, "domains/sales/metrics/orders.yaml", data)
        # An untrusted code file must never be extracted or executed from a revision.
        script = root / "acf_runtime/__init__.py"; script.parent.mkdir()
        script.write_text("raise RuntimeError('untrusted snapshot code ran')")
        new = save(root, "fictional head context")
        before, after, paths = revisions(root, old, new)
        assert "domains/sales/metrics/orders.yaml" in paths
        with snapshot(root, before) as b, snapshot(root, after) as h:
            assert not (h / "acf_runtime").exists()
            assert path_impact(h, ["domains/sales/metrics/orders.yaml"], base_root=b)["domains"] == ["billing", "retention", "sales"]
        result = subprocess.run([sys.executable, str(ROOT / ".ci/changed_domains.py"), "--root", str(root),
                                 "--base", old, "--head", new], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert result.stdout == "domains=billing,retention,sales,unrelated\n", result.stdout
        result = subprocess.run([sys.executable, str(ROOT / ".ci/changed_domains.py"), "--root", str(root),
                                 "--base", "nonexistent"], capture_output=True, text=True)
        assert result.returncode == 0 and "evaluating all" in result.stderr
        # Data snapshots retain unsupported artifacts so base/head validation
        # cannot accidentally bless a legacy or mixed layout by omitting them.
        for name in ("METRICS.LOOKML", "metrics.yml"):
            legacy = root / "domains/sales" / name
            legacy.write_text("legacy artifact")
            bad = save(root, "fictional unsupported layout")
            with snapshot(root, bad) as extracted:
                assert (extracted / "domains/sales" / name).exists()
                assert "layout.legacy" in {d.code for d in load_context(extracted).errors}
            legacy.unlink()
    print("test_changed_domains: OK")


if __name__ == "__main__":
    run()
