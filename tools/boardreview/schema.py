"""Check JSON files against the skill schemas (finding, checks, digest, board model) without extra packages."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

SCHEMAS = Path(__file__).resolve().parents[2] / "skill" / "schemas"
NAMES = {"finding": "finding.schema.json", "digest": "datasheet_digest.schema.json",
         "board_model": "board_model.schema.json", "checks": "check_result.schema.json"}
LISTS = {"finding": "findings", "checks": "checks"}


def load(name: str = "finding") -> dict:
    """Schema by short name or path."""
    path = SCHEMAS / NAMES[name] if name in NAMES else Path(name)
    return json.loads(path.read_text(encoding="utf-8"))


def _type_ok(inst, types) -> bool:
    for t in types if isinstance(types, list) else [types]:
        if t in ("number", "integer"):
            if isinstance(inst, bool):
                continue
            if t == "integer" and isinstance(inst, int):
                return True
            if t == "number" and isinstance(inst, (int, float)):
                return True
        elif isinstance(inst, {"object": dict, "array": list, "string": str,
                               "boolean": bool, "null": type(None)}[t]):
            return True
    return False


def validate(inst, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    """Check an instance against the JSON Schema subset the skill schemas use."""
    root = root if root is not None else schema
    errs: list[str] = []
    if "$ref" in schema:
        node = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = node[part]
        errs += validate(inst, node, root, path)
    if "type" in schema and not _type_ok(inst, schema["type"]):
        return errs + [f"{path}: expected {schema['type']}"]
    if "enum" in schema and inst not in schema["enum"]:
        errs.append(f"{path}: {inst!r} not in {schema['enum']}")
    if "const" in schema and inst != schema["const"]:
        errs.append(f"{path}: {inst!r} is not {schema['const']!r}")
    if isinstance(inst, str):
        if len(inst) < schema.get("minLength", 0):
            errs.append(f"{path}: shorter than {schema['minLength']}")
        if len(inst) > schema.get("maxLength", math.inf):
            errs.append(f"{path}: longer than {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], inst):
            errs.append(f"{path}: {inst!r} does not match {schema['pattern']}")
    if isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if inst < schema.get("minimum", -math.inf):
            errs.append(f"{path}: below {schema['minimum']}")
    if isinstance(inst, dict):
        errs += [f"{path}: missing {k}" for k in schema.get("required", []) if k not in inst]
        props, extra = schema.get("properties", {}), schema.get("additionalProperties", True)
        for k, v in inst.items():
            if k in props:
                errs += validate(v, props[k], root, f"{path}.{k}")
            elif extra is False:
                errs.append(f"{path}: unexpected key {k}")
            elif isinstance(extra, dict):
                errs += validate(v, extra, root, f"{path}.{k}")
    if isinstance(inst, list):
        if len(inst) < schema.get("minItems", 0):
            errs.append(f"{path}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, v in enumerate(inst):
                errs += validate(v, schema["items"], root, f"{path}[{i}]")
    for sub in schema.get("allOf", []):
        errs += validate(inst, sub, root, path)
    if "if" in schema:
        branch = "then" if not validate(inst, schema["if"], root, path) else "else"
        if branch in schema:
            errs += validate(inst, schema[branch], root, path)
    return errs


def items_of(data, name: str) -> list | None:
    """The list a findings or checks file holds: the file itself, or its 'findings' or 'checks' key."""
    items = data.get(LISTS[name]) if isinstance(data, dict) else data
    return items if isinstance(items, list) else None


def check_file(path: str | Path, name: str = "finding") -> list[str]:
    """Errors for a JSON file; findings and checks may be a list or {"findings"|"checks": [...]}, prefixed by id."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"not valid JSON: {exc}"]
    schema = load(name)
    if name not in LISTS:
        return validate(data, schema)
    items = items_of(data, name)
    if items is None:
        return [f"$: expected a list of {LISTS[name]} or an object with a {LISTS[name]} list"]
    errs = [f"{f.get('id', i) if isinstance(f, dict) else i}: {e}" for i, f in enumerate(items)
            for e in validate(f, schema)]
    if name == "checks":
        ids = [c.get("id") for c in items if isinstance(c, dict)]
        errs += [f"check id {i} is used twice" for i in sorted({i for i in ids if i and ids.count(i) > 1})]
    return errs
