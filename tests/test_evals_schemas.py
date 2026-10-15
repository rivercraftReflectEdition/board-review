import importlib.util
import json
from pathlib import Path

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


def test_calculation_mirrors_result_type():
    calc = {"calculator": "calc.divider", "formula": "v = vin * r2 / (r1 + r2)",
            "inputs": {"vin": {"value": 12.0, "unit": "V"}}, "outputs": {"v": {"value": 0.0012, "unit": "V"}},
            "verdict": "fail"}
    assert score.validate(_finding(calculations=[calc]), FINDING) == []
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
