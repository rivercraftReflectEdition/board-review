import importlib.util
import json
from dataclasses import fields
from pathlib import Path

import pytest

from boardreview.calc.base import Quantity, Result
from boardreview.calc.divider import enable_thresholds
from schema_pending import pending

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "skill" / "schemas"
EVALS = ROOT / "evals"

spec = importlib.util.spec_from_file_location("evals_score", EVALS / "score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)

FINDING = json.loads((SCHEMAS / "finding.schema.json").read_text(encoding="utf-8"))
DIGEST = json.loads((SCHEMAS / "datasheet_digest.schema.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((EVALS / "expected.schema.json").read_text(encoding="utf-8"))


def _finding(**kw):
    f = {
        "id": "F-001", "title": "R11 value stops U1", "severity": "blocker", "block": "enable_uvlo_sequencing",
        "failure_mode": "wrong_value", "claim": "R11 is 10 ohm, the converter never enables.",
        "evidence": [{"kind": "bom", "ref": "R11"}], "fix": "R11 to 10k",
        "verification": {"status": "CONFIRMED"},
    }
    f.update(kw)
    return f


def test_valid_finding_passes():
    assert score.validate(_finding(), FINDING) == []


def test_missing_field_and_bad_enum_are_caught():
    f = _finding(block="power")
    del f["fix"]
    errs = score.validate(f, FINDING)
    assert any("missing fix" in e for e in errs)
    assert any("'power' not in" in e for e in errs)


def test_not_published_requires_bench_test():
    f = _finding(not_published=[{"item": "internal compensation", "consequence": "footprint"}])
    assert any("missing bench_test" in e for e in score.validate(f, FINDING))
    f["bench_test"] = "Bode at 5 mV injection"
    assert score.validate(f, FINDING) == []


def test_unverifiable_requires_bench_test():
    f = _finding(verification={"status": "UNVERIFIABLE"})
    assert any("missing bench_test" in e for e in score.validate(f, FINDING))
    assert score.validate(_finding(not_published=[]), FINDING) == []


def _quantity(q: Quantity) -> dict:
    return {"value": q.value, "unit": q.unit} | ({"note": q.note} if q.note else {})


def _calculation(result: Result, calculator: str) -> dict:
    return {
        "calculator": calculator, "formula": result.formula,
        "inputs": {k: _quantity(q) for k, q in result.inputs.items()},
        "outputs": {k: _quantity(q) for k, q in result.outputs.items()},
        "verdict": result.verdict.value, "reason": result.reason,
        "assumptions": list(result.assumptions), "refs": list(result.refs),
    }


def test_result_fields_map_onto_the_calculation_schema():
    calc_def = pending(FINDING)["$defs"]["calculation"]["properties"]
    assert {f.name for f in fields(Result)} - {"name"} <= set(calc_def)
    assert {f.name for f in fields(Quantity)} <= set(FINDING["$defs"]["quantity"]["properties"])


def test_real_result_serializes_to_a_valid_calculation():
    r = enable_thresholds(1.15, 1.20, 1.25, 1.05, 1.10, 1.15, 100e3, 10.0, r_tol=0.01, i_leak_a=1e-6,
                          vin_min_v=10.8, refs=("synthetic U1 datasheet rev A p.5",))
    name = f"{enable_thresholds.__module__.removeprefix('boardreview.')}.{enable_thresholds.__name__}"
    calc = json.loads(json.dumps(_calculation(r, name)))
    assert calc["calculator"] == "calc.divider.enable_thresholds" and _resolve(name) is enable_thresholds
    assert score.validate(_finding(calculations=[calc]), FINDING) == []
    ins, outs = calc["inputs"], calc["outputs"]
    assert (ins["r_top"], ins["r_bot"]) == ({"value": 100e3, "unit": "ohm"}, {"value": 10.0, "unit": "ohm"})
    assert ins["v_rise"] == {"value": 1.20, "unit": "V", "note": "1.15 to 1.25"}
    assert (ins["r_tol"]["value"], ins["i_leak"]["value"], ins["vin_min"]["value"]) == (0.01, 1e-6, 10.8)
    # 1.20 V * (1 + 100k / 10) and 1.10 V * (1 + 100k / 10).
    assert outs["enable_nom"] == {"value": pytest.approx(12001.2, abs=1e-9), "unit": "V"}
    assert outs["disable_nom"]["value"] == pytest.approx(11001.1, abs=1e-9)
    # 1.25 V * (1 + 101k / 9.9) + 1 uA * 101k = 1262623.75 / 99 + 0.101.
    assert outs["enable_max"]["value"] == pytest.approx(12753.876253, abs=1e-6)
    # 1.15 V * (1 + 99k / 10.1) - 1 uA * 99k = 1138616.15 / 101 - 0.099.
    assert outs["enable_min"]["value"] == pytest.approx(11273.328228, abs=1e-6)
    assert calc["verdict"] == "fail" and "12753.876 V" in calc["reason"]
    assert calc["refs"][-1] == "synthetic U1 datasheet rev A p.5"
    calc["verdict"] = "bad"
    assert score.validate(_finding(calculations=[calc]), FINDING)


def test_block_and_failure_vocab_matches_checklists():
    blocks, modes = score.vocab(FINDING)
    files = {p.stem for p in (ROOT / "skill" / "checklists").glob("*.md")}
    assert blocks - {"other"} == files
    assert {"loop_instability", "reverse_current", "lc_resonance", "strap_conflict"} <= modes


def test_bug_classes_use_schema_vocab_and_real_checklist_items():
    blocks, modes = score.vocab(FINDING)
    classes = json.loads((EVALS / "bug_classes.json").read_text(encoding="utf-8"))["classes"]
    assert len(classes) == 7
    for c in classes:
        assert c["block"] in blocks and c["failure_mode"] in modes
        for ref in c["checks"]:
            name, item = ref.split("#")
            text = (ROOT / "skill" / "checklists" / f"{name}.md").read_text(encoding="utf-8")
            assert f"## {item} " in text, ref


def test_example_expected_files_valid():
    for p in EVALS.glob("*/expected.json"):
        assert score.validate(json.loads(p.read_text(encoding="utf-8")), EXPECTED) == [], p


def test_example_reviews_valid():
    for p in list(EVALS.glob("*/review.json")) + list(EVALS.glob("*/clean_review.json")):
        for f in score.review_list(json.loads(p.read_text(encoding="utf-8"))):
            assert score.validate(f, FINDING) == [], (p, f["id"])


def _resolve(name: str):
    parts = f"boardreview.{name}".split(".")
    for i in range(len(parts), 1, -1):
        try:
            obj = importlib.import_module(".".join(parts[:i]))
        except ModuleNotFoundError:
            continue
        for attr in parts[i:]:
            obj = getattr(obj, attr)
        return obj
    raise ModuleNotFoundError(name)


def test_calculators_cited_in_example_reviews_resolve():
    cited = set()
    for p in list(EVALS.glob("*/review.json")) + list(EVALS.glob("*/clean_review.json")):
        for f in score.review_list(json.loads(p.read_text(encoding="utf-8"))):
            cited |= {c["calculator"] for c in f.get("calculations", [])}
            cited |= {e["ref"] for e in f["evidence"] if e["kind"] == "calculator"}
    assert "calc.protection.tvs_standoff" in cited
    for name in sorted(cited):
        try:
            _resolve(name)
        except (ImportError, AttributeError) as exc:
            pytest.fail(f"{name}: {exc}")


def _digest():
    return {
        "mpn": "EXAMPLE1234", "manufacturer": "Example Semi",
        "document": {"number": "DS-1", "revision": "B"},
        "read_from": {"method": "page_images", "pages_read": [1, 3, 16]},
        "pins": [{"pin": "1", "name": "ITH", "type": "analog", "page": 3}],
        "abs_max": [{"parameter": "VIN", "max": 6.0, "unit": "V", "page": 2}],
        "recommended_operating": [{"parameter": "VIN", "min": 3.6, "max": 5.5, "unit": "V", "page": 2}],
        "electrical": [{"parameter": "RUN rising threshold", "min": 1.18, "max": 1.26, "unit": "V", "page": 3}],
        "equations": [{"name": "vout", "expression": "vout = 0.6 * (1 + r1 / r2)", "page": 15}],
        "layout_rules": [{"rule": "Keep FB trace away from SW", "page": 21}],
        "errata": [],
        "example_envelope": [{"source": "Typical application 1", "vin_v": {"min": 3.6, "max": 5.5},
                              "vout_v": 3.3, "fsw_hz": 2.0e6, "l_h": 1.0e-6,
                              "compensation": {"mode": "internal"}, "page": 26}],
        "not_published": [{"item": "internal compensation values", "consequence": "footprint"}],
    }


def test_digest_schema_accepts_minimal_digest_and_requires_page_images():
    assert score.validate(_digest(), DIGEST) == []
    d = _digest()
    d["read_from"]["method"] = "pdftotext"
    assert score.validate(d, DIGEST)


def test_digest_entries_need_pages():
    d = _digest()
    del d["abs_max"][0]["page"]
    assert any("missing page" in e for e in score.validate(d, DIGEST))
