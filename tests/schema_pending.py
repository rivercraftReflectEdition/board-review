"""Schema changes the tools already emit and skill/schemas does not carry yet: null quantity values and context."""

import copy

CONTEXTS = ["nominal", "worst_case", "example", "ideal"]


def nullable_value(schema: dict) -> bool:
    t = schema["$defs"]["quantity"]["properties"]["value"].get("type")
    return isinstance(t, list) and "null" in t


def has_context(schema: dict) -> bool:
    return "context" in schema["$defs"]["calculation"]["properties"]


def pending(schema: dict) -> dict:
    """The schema with the two changes applied when it lacks them, for validating calculator output today."""
    out = copy.deepcopy(schema)
    if not nullable_value(out):
        out["$defs"]["quantity"]["properties"]["value"]["type"] = ["number", "null"]
    if not has_context(out):
        out["$defs"]["calculation"]["properties"]["context"] = {"enum": CONTEXTS}
    return out
