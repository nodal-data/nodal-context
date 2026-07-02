"""Anthropic BYO-key wrapper — generate (answer a seed) and judge (grade the answer).

Mirrors the BYO-key pattern in .ci/suggest.py: gate on ANTHROPIC_API_KEY, fixed model,
structured output. No warehouse: `generate` returns the SQL the model *would* run; `judge`
grades that SQL's shape against the seed's `expected`. Tests monkeypatch `generate` /
`judge` / `available`, so the anthropic SDK is imported lazily and only on a real call.
"""
import json
import os

MODEL = "claude-opus-4-8"
MAX_TOKENS = 4096
MAX_CONTEXT_CHARS = 24000   # bound the injected context so a huge domain can't blow up the call


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _structured_call(system, user, schema, model):
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": user}],
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


# ----- generate ---------------------------------------------------------------

_GEN_SCHEMA = {
    "type": "object",
    "properties": {
        "sql": {"type": "string"},
        "assumptions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["sql", "assumptions"],
    "additionalProperties": False,
}
_GEN_SYSTEM = (
    "You are a senior analytics engineer. Given a business question, produce the "
    "read-only SQL (SELECT only — never DDL/DML) you would run to answer it. If governed "
    "analytics context is provided, follow its definitions, routing (IF/DO NOT) triggers, "
    "caveats, and entity disambiguations exactly. Return JSON with `sql` and a short list "
    "of `assumptions`."
)


def generate(question, context_text=None, model=MODEL) -> dict:
    if context_text:
        ctx = context_text[:MAX_CONTEXT_CHARS]
        user = (f"Question: {question}\n\nGoverned analytics context for this domain — "
                f"follow it exactly:\n\n{ctx}\n\nReturn the SQL you would run and your "
                f"assumptions.")
    else:
        user = (f"Question: {question}\n\nReturn the SQL you would run and your "
                f"assumptions.")
    return _structured_call(_GEN_SYSTEM, user, _GEN_SCHEMA, model)


# ----- judge ------------------------------------------------------------------

_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["passed", "reason"],
    "additionalProperties": False,
}
_JUDGE_SYSTEM = (
    "You are a strict reviewer of analytics SQL. Judge ONLY whether the query satisfies "
    "the stated requirements — not whether it would run. Be conservative: if a required "
    "behavior is absent or a forbidden behavior is present, it fails. Return JSON with "
    "`passed` (bool) and a one-line `reason`."
)


def judge(sql, expected, model=MODEL) -> dict:
    """Return {passed: bool, reason: str} for one generated answer vs its `expected`."""
    kind = (expected or {}).get("kind", "")
    if kind == "semantic_entity":
        entity = expected.get("entity", "")
        user = (f"SQL:\n```sql\n{sql}\n```\n\nDoes this query resolve the business term "
                f"to the governed entity `{entity}` (correct table/grain)? Pass only if it "
                f"clearly does.")
    else:  # sql_shape (and any kind that carries must_include/must_exclude)
        inc = expected.get("must_include", []) or []
        exc = expected.get("must_exclude", []) or []
        lines = [f"SQL:\n```sql\n{sql}\n```", ""]
        if inc:
            lines.append("MUST satisfy all of:")
            lines += [f"  - {i}" for i in inc]
        if exc:
            lines.append("MUST NOT do any of:")
            lines += [f"  - {e}" for e in exc]
        lines.append("\nPass only if every MUST is satisfied and no MUST-NOT is violated. "
                     "In `reason`, name the first requirement that fails (or confirm all met).")
        user = "\n".join(lines)
    return _structured_call(_JUDGE_SYSTEM, user, _JUDGE_SCHEMA, model)
