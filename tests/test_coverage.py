"""Coverage separates definition, slice, demand and verification evidence."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_runtime import load_context
from acf_runtime.loader import Schemas
from acf_runtime.observed import read_queue, retain_variant
from eval_harness.coverage import build_report
from acf_fixtures import context, metric, seed, write


def run():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td); context(root)
        write(root, "domains/sales/metrics/orders.yaml", metric())
        write(root, "evals/seeds/orders.seed.yaml", seed())
        registry = load_context(root, schemas=ROOT / "schemas")
        seeds = registry.seed_records(); definitions = registry.definitions()
        report = build_report(definitions, seeds, time_tokens=["last_month", "last_quarter"])
        assert report["demand_available"] is False and report["queue_depth"] is None
        target = report["targets"]["metric:sales.orders"]
        assert target["definition"] == "defined"
        assert target["slicing"][0]["slice_covered"]
        assert not target["slicing"][0]["verification_covered"]
        all_report = build_report(definitions, seeds, time_tokens=["last_month", "last_quarter"], all_cells=True)
        assert len(all_report["targets"]["metric:sales.orders"]["slicing"]) == 6  # aggregate + two singleton dims x two tokens
        queue = [{"id": "q1", "count": 5, "status": "pending", "domain": "sales", "ir": {"metric": "orders", "dimensions": ["date"], "time_window": "last_quarter"}},
                 {"id": "q2", "count": 3, "status": "linked", "domain": "sales", "ir": {"metric": "orders", "dimensions": ["date"], "time_window": "last_quarter"}},
                 {"id": "q3", "count": 12, "status": "pending", "relation": "ambiguous", "domain": "sales", "ir": {"metric": None}}]
        report = build_report(definitions, seeds, queue)
        assert report["queue_depth"] == 2
        assert len(report["uncovered"]) == 1 and report["uncovered"][0]["demand"] == 8
        assert report["unresolved_demand"][0]["count"] == 12
        unknown_time = {**queue[0], "id": "bad-window", "relation": "equivalent",
                        "ir": {**queue[0]["ir"], "time_window": "unconfigured_period"}}
        bad_seed = deepcopy(seeds[0]); bad_seed["ir"]["time_window"] = "unconfigured_period"
        bad_report = build_report(definitions, [bad_seed], [unknown_time],
                                  time_tokens=["unconfigured_period"], all_cells=True)
        assert not bad_report["targets"]["metric:sales.orders"]["slicing"]
        assert bad_report["orphan_seeds"][0]["reasons"] == ["unknown_time_token"]
        assert bad_report["unresolved_demand"][0]["relation"] == "unresolved"
        assert bad_report["unresolved_demand"][0]["reasons"] == ["unknown_time_token"]
        evidence = {seeds[0]["id"]: {"state": "unchecked_without_key", "verified": False}}
        report = build_report(definitions, seeds, verification=evidence)
        assert not report["stale_seeds"]  # a missing key does not revoke a definition
        evidence[seeds[0]["id"]] = {"state": "notebook_confirmed_snapshot", "verified": True}
        report = build_report(definitions, seeds, verification=evidence)
        assert report["targets"]["metric:sales.orders"]["slicing"][0]["verification_covered"]
        stale = deepcopy(seeds); stale[0]["ir"]["dimensions"] = ["missing"]
        assert build_report(definitions, stale)["stale_seeds"]
        stale[0]["ir"]["metric"] = "deleted"
        assert build_report(definitions, stale)["orphan_seeds"]
        negative = deepcopy(seeds[0]); negative["id"] = "negative"; negative["expected"] = {"kind": "negative", "reason": "lack_data"}; negative.pop("ir")
        report = build_report(definitions, [negative])
        assert report["negative_seeds"] == {"lack_data": 1} and not report["orphan_seeds"]
        assert read_queue(root, Schemas(ROOT / "schemas")) is None
        qpath = root / "evals/observed/queue.jsonl"; qpath.parent.mkdir(parents=True)
        qpath.write_text('{bad json}\n')
        try:
            read_queue(root, Schemas(ROOT / "schemas"))
        except ValueError as exc:
            assert ':1:' in str(exc)
        else:
            raise AssertionError('invalid queue was ignored')
        # Duplicate/near-duplicate retention never changes semantic matching.
        base = seed()
        duplicate = {"text": base["question"].upper(), "observed_at": "2026-10-10T10:00:00Z", "provenance": "observed"}
        updated, outcome, overflow = retain_variant(base, duplicate, maximum=2)
        assert outcome == "duplicate_dropped" and updated == base and overflow == [duplicate]
        one = {**duplicate, "text": "How many purchases in each channel?", "observed_at": "2026-10-01T10:00:00Z"}
        two = {**duplicate, "text": "Show the channel order breakdown", "observed_at": "2026-10-02T10:00:00Z"}
        three = {**duplicate, "text": "Can you count the orders per channel please?"}
        first, _, _ = retain_variant(base, one, maximum=2)
        second, _, _ = retain_variant(first, two, maximum=2)
        third, outcome, overflow = retain_variant(second, three, maximum=2)
        assert outcome == "replaced_oldest" and overflow == [one]
        assert third["variants"] == [two, three] and len(second["variants"]) == 2
        # Coverage CLI reads without writing any artifact and reports a missing query.
        spec = importlib.util.spec_from_file_location("coverage_cli", ROOT / ".ci/coverage.py")
        cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
        evidence = cli.evidence(root, {**seeds[0], "verified_query_file": "evals/verified/orders.sql"}, registry.config)
        assert evidence["query"] == "missing" and not evidence["verified"]
    print("test_coverage: OK")


if __name__ == "__main__":
    run()
