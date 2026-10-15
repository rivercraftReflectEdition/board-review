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
    assert any("not in" in e for e in _errors(_row(basis="guaranteed_by_design")))
