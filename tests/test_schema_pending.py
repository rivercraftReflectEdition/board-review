"""The finding and check schemas must carry what calculators emit: null for a non-finite value, and context."""

import json
from pathlib import Path

import pytest

from boardreview.calc.base import CONTEXTS
from schema_pending import has_context, nullable_value

SCHEMAS = Path(__file__).resolve().parent.parent / "skill" / "schemas"
LOADED = {n: json.loads((SCHEMAS / f"{n}.schema.json").read_text(encoding="utf-8")) for n in ("finding", "check_result")}


@pytest.mark.xfail(not all(nullable_value(s) for s in LOADED.values()), strict=False,
                   reason="skill/schemas quantity.value is number only; Quantity.to_dict writes null for inf and NaN")
def test_quantity_value_may_be_null():
    assert all(nullable_value(s) for s in LOADED.values())


@pytest.mark.xfail(not all(has_context(s) for s in LOADED.values()), strict=False,
                   reason="skill/schemas calculation has no context; Result.to_dict writes it when the inputs are marked")
def test_calculation_lists_the_input_context():
    for s in LOADED.values():
        assert set(s["$defs"]["calculation"]["properties"]["context"]["enum"]) == set(CONTEXTS)
