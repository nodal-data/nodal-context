#!/usr/bin/env python3
"""Prepare synthetic dbt evidence and measure operator-exported retrieval traces.

No agent, MCP server, warehouse, or network is launched by this script.
"""

import argparse
import hashlib
import json
import statistics
from pathlib import Path

import yaml


CONFIGURATIONS = {"baseline", "skill-only", "server-only", "combined"}
REVIEW_FIELDS = {"constraints_retained", "approval_preserved", "evidence_complete"}


def fixture_files():
    """Return a deterministic project; expectations are not in agent evidence."""
    models = [
        {
            "name": "fct_orders",
            "description": "Canonical real-customer order fact; first-day flags may repeat.",
            "data_tests": [{"expression_is_true": {
                "arguments": {"expression": "order_date >= customer_created_date"}}}],
            "columns": [
                {"name": "order_id", "data_tests": ["unique", "not_null"]},
                {"name": "customer_id", "data_tests": ["not_null", {"relationships": {
                    "arguments": {"to": "ref('dim_customers')", "field": "app_db_customer_id"}}}]},
                {"name": "order_date"}, {"name": "customer_created_date"},
                {"name": "is_first_order"},
            ],
        },
        {
            "name": "dim_customers",
            "description": "Real customers only; excludes test and internal accounts.",
            "columns": [{"name": "app_db_customer_id", "data_tests": ["unique", "not_null"]}],
        },
    ]
    files = {
        "dbt_project.yml": (
            "name: retrieval_fixture\nversion: '1.0'\nconfig-version: 2\n"
            "profile: retrieval_fixture\n"),
        "macros/expression_is_true.sql": (
            "{% test expression_is_true(model, expression) %}\n"
            "select * from {{ model }} where not ({{ expression }})\n"
            "{% endtest %}\n"),
        "models/fct_orders.sql": (
            "with orders as (select * from {{ source('raw', 'orders') }}),\n"
            "first_orders as (select customer_id, min(order_date) as first_date "
            "from orders group by customer_id)\n"
            "select o.*, c.created_date as customer_created_date,\n"
            "o.order_date = f.first_date as is_first_order\n"
            "from orders o join {{ ref('dim_customers') }} c\n"
            "on o.customer_id = c.app_db_customer_id\n"
            "join first_orders f on o.customer_id = f.customer_id\n"
        ),
        "models/dim_customers.sql": (
            "select app_db_customer_id, created_date from {{ source('raw', 'customers') }}\n"
            "where account_type = 'customer'\n"
        ),
    }
    for index in range(30):
        name = f"supplier_{index:02d}"
        models.append({"name": name, "description": f"Unrelated supplier report {index}.",
                       "columns": [{"name": "supplier_id", "data_tests": ["not_null"]}]})
        files[f"models/{name}.sql"] = f"select supplier_id from {{{{ source('raw', '{name}') }}}}\n"
    files["models/_marts.yml"] = yaml.safe_dump({"version": 2, "models": models}, sort_keys=False)
    files["models/_sources.yml"] = yaml.safe_dump({
        "version": 2, "sources": [{"name": "raw", "tables": [
            {"name": name} for name in ["orders", "customers"] +
            [f"supplier_{index:02d}" for index in range(30)]
        ]}]}, sort_keys=False)
    files["context.md"] = (
        "Synthetic planning fixture, not production approval evidence.\n"
        "Question: How many new customers did we gain in September 2026?\n"
        "Metric customers.new_customers: distinct canonical customers with their\n"
        "first-ever order in [2026-09-01, 2026-10-01), UTC, all channels.\n"
        "Mandatory filter: is_first_order = true. Same-day flags can repeat.\n"
        "Lineage: model.retrieval_fixture.fct_orders. No analytical plan approved.\n"
        "For this synthetic exercise, authority evidence is valid for context\n"
        "revision ctx17 and source revision fixture42; no open decisions.\n"
        "This is a fixture assertion only, never a live authority receipt.\n"
    )
    return files


def prepare(destination):
    """Create a new directory only; never overwrite or delete caller data."""
    destination.mkdir(parents=True, exist_ok=False)
    files = fixture_files()
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    for relative, content in files.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return {"directory": str(destination), "fixture_sha256": digest, "model_count": 32}


def summarize(run):
    """Measure full exported response strings, never infer semantic correctness."""
    if not isinstance(run, dict):
        raise ValueError("each run must be an object")
    if run.get("configuration") not in CONFIGURATIONS:
        raise ValueError("unknown configuration")
    for field in ("host", "model", "settings_id", "fixture_sha256", "run_id"):
        if not isinstance(run.get(field), str) or not run[field]:
            raise ValueError(f"missing {field}")
    events = run.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("events must be a nonempty list")
    counts = {"raw_bytes": 0, "discovery_bytes": 0, "evidence_bytes": 0,
              "overview_calls": 0, "business_execution_calls": 0,
              "unrelated_model_bodies": 0}
    tokens = {"discovery_tokens": 0, "evidence_tokens": 0}
    exact_tokens = isinstance(run.get("tokenizer"), str) and bool(run["tokenizer"].strip())
    retrieval_events = 0
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("each event must be an object")
        if event.get("kind") not in {"discovery", "evidence", "execution"}:
            raise ValueError("unknown event kind")
        for field in ("raw_response", "emitted_response"):
            if not isinstance(event.get(field), str):
                raise ValueError(f"event requires complete {field} string")
        if event.get("capture_complete") is not True:
            raise ValueError("incomplete capture cannot support volume comparison")
        for field in ("overview", "business_execution"):
            if type(event.get(field)) is not bool:
                raise ValueError(f"event requires boolean {field}")
        bodies = event.get("model_bodies")
        if not isinstance(bodies, list) or any(not isinstance(x, str) for x in bodies):
            raise ValueError("model_bodies must list IDs of full bodies, not index hits")
        counts["raw_bytes"] += len(event["raw_response"].encode("utf-8"))
        kind = event["kind"]
        if kind in {"discovery", "evidence"}:
            retrieval_events += 1
            counts[f"{kind}_bytes"] += len(event["emitted_response"].encode("utf-8"))
            count = event.get("emitted_tokens")
            if type(count) is not int or count < 0:
                exact_tokens = False
            else:
                tokens[f"{kind}_tokens"] += count
        counts["overview_calls"] += event["overview"]
        counts["business_execution_calls"] += event["business_execution"]
        relevant = {"model.retrieval_fixture.fct_orders", "model.retrieval_fixture.dim_customers"}
        counts["unrelated_model_bodies"] += sum(x not in relevant for x in bodies)
    review = run.get("review", {})
    if not isinstance(review, dict):
        raise ValueError("review must be an object")
    if any(type(review.get(field)) is not bool for field in REVIEW_FIELDS):
        raise ValueError("independent review must record each required boolean finding")
    if not isinstance(review.get("evidence"), str) or not review["evidence"].strip():
        raise ValueError("review requires evidence/citations, not just pass flags")
    failures = sorted(field for field in REVIEW_FIELDS if not review[field])
    if counts["business_execution_calls"]:
        failures.append("business execution before fixture plan approval")
    if run["configuration"] == "combined":
        if counts["overview_calls"] or counts["unrelated_model_bodies"]:
            failures.append("combined path exposed broad/unrelated evidence")
    exact_tokens = exact_tokens and retrieval_events > 0
    return {"run_id": run["run_id"], "configuration": run["configuration"],
            **counts, **(tokens if exact_tokens else {k: None for k in tokens}),
            "tokenizer": run.get("tokenizer") if exact_tokens else None,
            "review_evidence": review["evidence"], "failures": failures}


def compare(runs):
    """Compare matched captures; absent server arms remain explicitly absent."""
    if not isinstance(runs, list) or not runs:
        raise ValueError("a nonempty array of runs is required")
    summaries = [summarize(run) for run in runs]
    keys = {(r["host"], r["model"], r["settings_id"], r["fixture_sha256"]) for r in runs}
    if len(keys) != 1:
        raise ValueError("comparison requires identical fixture, host, model and settings")
    if len({r["run_id"] for r in runs}) != len(runs):
        raise ValueError("run IDs must be unique")
    medians = {}
    tokenizers = {r["tokenizer"] for r in summaries}
    token_reason = (
        "missing complete retrieval token measurements" if None in tokenizers else
        "different tokenizers" if len(tokenizers) != 1 else None)
    for config in sorted(CONFIGURATIONS):
        subset = [r for r in summaries if r["configuration"] == config]
        if subset:
            fields = ("raw_bytes", "discovery_bytes", "evidence_bytes",
                      "overview_calls", "unrelated_model_bodies")
            medians[config] = {k: statistics.median(r[k] for r in subset) for k in fields}
            medians[config]["run_count"] = len(subset)
            if token_reason is None:
                medians[config].update({k: statistics.median(r[k] for r in subset)
                                       for k in ("discovery_tokens", "evidence_tokens")})
                medians[config]["retrieval_tokens"] = statistics.median(
                    r["discovery_tokens"] + r["evidence_tokens"] for r in subset)
    acceptance = {"status": "not_evaluated", "reason": "baseline and combined arms required"}
    if {"baseline", "combined"} <= medians.keys():
        if any(r["failures"] for r in summaries):
            acceptance = {"status": "fail", "reason": "one or more runs failed review or execution checks"}
        elif token_reason:
            acceptance = {"status": "not_evaluated", "reason": token_reason}
        else:
            reduced = medians["combined"]["retrieval_tokens"] < medians["baseline"]["retrieval_tokens"]
            acceptance = {"status": "pass" if reduced else "fail",
                          "reason": "combined median total retrieval tokens must be strictly lower than baseline"}
    return {"measurement": "UTF-8 bytes of full captured response strings; tokens only when supplied with tokenizer",
            "review": "operator adjudication; not independent approval attestation",
            "token_comparison": {"status": "incomparable" if token_reason else "comparable",
                                 "reason": token_reason,
                                 "tokenizer": None if token_reason else summaries[0]["tokenizer"]},
            "combined_acceptance": acceptance,
            "runs": summaries, "medians": medians,
            "missing_configurations": sorted(CONFIGURATIONS - medians.keys())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare").add_argument("directory", type=Path)
    sub.add_parser("report").add_argument("capture", type=Path)
    args = parser.parse_args()
    try:
        result = prepare(args.directory) if args.command == "prepare" else compare(
            json.loads(args.capture.read_text(encoding="utf-8")))
        print(json.dumps(result, indent=2))
        if any(r["failures"] for r in result.get("runs", [])):
            return 1
        if "combined" in result.get("medians", {}):
            return {"pass": 0, "fail": 1, "not_evaluated": 2}[result["combined_acceptance"]["status"]]
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"retrieval_probe: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
