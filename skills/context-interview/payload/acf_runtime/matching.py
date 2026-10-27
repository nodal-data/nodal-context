"""ACF adapter for the format-neutral structural matcher."""
from pathlib import Path
from .loader import Schemas
from eval_harness.matching import match_question


def match_registry(registry, ir, domain, *, candidates=None, exclude=()):
    result = match_question(ir, domain, registry.definitions(), registry.seed_records(),
                            candidates=candidates, exclude=exclude)
    if result["relation"] == "decomposes":
        return {"relation": "decomposes", "parts": [match_registry(
            registry, part, domain, exclude=exclude) for part in ir["parts"]]}
    # Ambiguity precedes matching; selection supplies a complete IR on the next pass.
    if result["relation"] == "ambiguous":
        return result
    directory = registry.root / "schemas"
    if not directory.is_dir():
        directory = Path(__file__).resolve().parents[1] / "schemas"
    errors = Schemas(directory).errors("ir", ir)
    tokens = registry.config.get("time_tokens", {})
    declared = tokens.get("calendar", []) + tokens.get("fiscal", [])
    token = ir.get("time_window") if isinstance(ir, dict) else None
    reasons = (["invalid_question_ir"] if errors else [])
    if isinstance(token, str) and token not in declared:
        reasons.append("unknown_time_token")
    if domain not in registry.domains:
        reasons.append("unknown_domain")
    if reasons:
        result.update(relation="unresolved", seeds=[], unsupported=reasons)
    return result
