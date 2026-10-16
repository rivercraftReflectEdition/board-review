import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("evals_score", ROOT / "evals" / "score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)
DIGEST = json.loads((ROOT / "skill" / "schemas" / "datasheet_digest.schema.json").read_text(encoding="utf-8"))


def _row(**kw):
    row = {"parameter": "RUN rising threshold", "min": 1.18, "max": 1.26, "unit": "V", "page": 3}
    row.update(kw)
    return row


def _errors(row):
    return score.validate(row, DIGEST["$defs"]["spec"], DIGEST)


def test_guarantee_and_its_basis_are_separate_fields():
    assert _errors(_row(guaranteed=True, basis="production_tested")) == []
    assert _errors(_row(guaranteed=True, basis="design")) == []
    assert _errors(_row(guaranteed=False, basis="typical")) == []
    for basis in ("statistical", "mixed", "unspecified"):
        assert _errors(_row(guaranteed=True, basis=basis)) == [], basis
    assert any("not in" in e for e in _errors(_row(basis="guaranteed_by_design")))


def test_relative_limit_names_its_reference_pins():
    row = _row(parameter="OUT voltage", min=-0.3, unit="V",
               relative_limits=[{"bound": "max", "expression": "min(VIN + 0.3, 3.6)", "references": ["VIN"]}])
    del row["max"]
    assert _errors(row) == []
    row["relative_limits"][0]["references"] = []
    assert any("fewer than 1" in e for e in _errors(row))


def _example(**kw):
    ex = {"source": "Figure 30", "vin_v": {"min": 1.8, "max": 5.5}, "vout_v": 1.2,
          "compensation": {"mode": "internal"}, "page": 22}
    ex.update(kw)
    return score.validate(ex, DIGEST["$defs"]["example"], DIGEST)


def test_linear_example_needs_no_fsw_and_switching_does():
    assert _example(topology="linear", output_setting="fixed") == []
    assert any("missing fsw_hz" in e for e in _example())
    assert any("missing fsw_hz" in e for e in _example(topology="switching"))
    assert _example(fsw_hz=2.1e6, output_setting="adjustable",
                    compensation={"mode": "internal", "feedback_shaping": "Cff 22 pF across R1"}) == []


def test_source_unavailable_record_needs_no_pages_or_pins():
    rec = {"mpn": "EXAMPLE5678", "status": "source_unavailable",
           "unavailable": {"reason": "user_said_unavailable", "consequence": "LDO-1 and LDO-2 stay unknown"}}
    assert score.validate(rec, DIGEST) == []
    del rec["unavailable"]
    assert any("missing unavailable" in e for e in score.validate(rec, DIGEST))
    draft = {"mpn": "EXAMPLE5678", "status": "draft"}
    assert any("missing pins" in e for e in score.validate(draft, DIGEST))


def test_conflict_keeps_both_rows():
    conflict = {"item": "pin 4 name", "used": "pin table p.3 over the abs max table",
                "rows": [{"text": "SYNC", "page": 10}, {"text": "MODE", "page": 3}]}
    assert score.validate(conflict, DIGEST["$defs"]["conflict"], DIGEST) == []
    conflict["rows"].pop()
    assert any("fewer than 2" in e for e in score.validate(conflict, DIGEST["$defs"]["conflict"], DIGEST))
