import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"


def _load_score():
    spec = importlib.util.spec_from_file_location("evals_score", EVALS / "score.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


score = _load_score()
SCHEMA = score.load_schema()
BLOCKS, MODES = score.vocab(SCHEMA)


def _finding(**kw):
    base = {
        "id": "T1", "title": "test finding", "severity": "major", "block": "buck_regulator",
        "failure_mode": "loop_instability", "claim": "a claim long enough",
        "evidence": [{"kind": "netlist", "ref": "net X"}], "fix": "fix it",
        "verification": {"status": "CONFIRMED"},
    }
    base.update(kw)
    return base


def test_refdes_range_expands_and_pins_add_parts():
    assert score.norm_parts(["R14-R17", "u9"]) == {"R14", "R15", "R16", "R17", "U9"}
    assert score.norm_parts(["R14-17"]) == {"R14", "R15", "R16", "R17"}
    assert score.finding_parts({"parts": ["L3"], "pins": ["U9.26"]}) == {"L3", "U9"}


def test_net_names_normalize_case_and_separators_and_keep_hierarchy():
    assert score.norm_net("/Power/1v8_sw1 filt") == "POWER/1V8-SW1-FILT"
    assert score.norm_net("+3V3") == "3V3"


def test_hierarchical_nets_with_the_same_leaf_are_different_nets():
    exp = {"block": "io_levels_and_domains", "nets": ["/SensorA/I2C_SDA"], "failure_mode": "missing_pullup",
           "keywords": ["pull up|pullup"]}
    f = _finding(block="io_levels_and_domains", failure_mode="missing_pullup", claim="No pull-up on SDA.")
    assert not score.evaluate(exp, dict(f, nets=["/SensorB/I2C_SDA"]), BLOCKS, MODES)[0]
    assert score.evaluate(exp, dict(f, nets=["/sensora/i2c sda"]), BLOCKS, MODES)[0]
    assert score.evaluate(exp, dict(f, nets=["I2C_SDA"]), BLOCKS, MODES)[0]
    assert score.evaluate(dict(exp, nets=["I2C_SDA"]), dict(f, nets=["/SensorB/I2C_SDA"]), BLOCKS, MODES)[0]


def test_block_aliases_and_mode_synonyms():
    assert score.canon_block("Buck", BLOCKS) == "buck_regulator"
    assert score.canon_block("ESD", BLOCKS) == "protection_tvs"
    assert score.canon_mode("limit cycle", MODES) == "loop_instability"
    assert score.canon_mode("back-powering", MODES) == "back_power"
    assert score.canon_mode("lc_resonance", MODES) == "lc_resonance"


def test_keyword_rule_word_start_alternatives_and_compounds():
    text = score.norm_text("The rail oscillates; add a feedforward cap.")
    assert score.keyword_hit("oscillat|unstable", text)
    assert score.keyword_hit("feed forward", text)
    assert not score.keyword_hit("pg", score.norm_text("upgrade the part"))
    assert score.keywords_needed(["a"]) == 1
    assert score.keywords_needed(["a", "b", "c"]) == 2


LOOP = {"block": "buck_regulator", "failure_mode": "loop_instability", "keywords": ["oscillat|unstable|phase margin"]}
OSC = "The loop oscillates at light load."


def test_match_needs_block_location_and_mechanism():
    exp = dict(LOOP, parts=["U2"])
    assert score.evaluate(exp, _finding(parts=["U2"], claim=OSC), BLOCKS, MODES)[0]
    assert not score.evaluate(exp, _finding(parts=["U3"], claim=OSC), BLOCKS, MODES)[0]
    assert not score.evaluate(exp, _finding(parts=["U2"], block="ldo", claim=OSC), BLOCKS, MODES)[0]
    assert not score.evaluate(exp, _finding(parts=["U2"]), BLOCKS, MODES)[0]


def test_keywords_match_across_failure_tags():
    exp = {"block": "straps_and_boot_pins", "alt_blocks": ["ethernet_phy"], "parts": ["R40-R41"],
           "failure_mode": "strap_conflict", "keywords": ["strap", "both|mid level", "latch"]}
    rev = _finding(block="ethernet_phy", parts=["R41"], failure_mode="level_mismatch",
                   title="mode strap has pull-up and pull-down both fitted")
    assert score.evaluate(exp, rev, BLOCKS, MODES)[0]
    rev_one_hit = _finding(block="ethernet_phy", parts=["R41"], failure_mode="level_mismatch",
                           title="mode strap reads low")
    assert not score.evaluate(exp, rev_one_hit, BLOCKS, MODES)[0]


def _example_expected(eid):
    return next(e for e in score.load_json(EVALS / "example" / "expected.json")["findings"] if e["id"] == eid)


def test_tag_alone_does_not_match_a_vague_finding():
    vague = _finding(parts=["U2"], title="This circuit needs review", claim="This circuit needs review.",
                     verification={"status": "PENDING"})
    assert score.validate(vague, SCHEMA) == []
    assert not score.evaluate(_example_expected("E1"), vague, BLOCKS, MODES)[0]


def test_finding_that_asserts_a_pass_does_not_match():
    e1 = _example_expected("E1")
    stable = _finding(parts=["U2"], title="U2 is stable",
                      claim="U2 is stable: the example compensation gives 60 degrees of phase margin.")
    assert not score.evaluate(e1, stable, BLOCKS, MODES)[0]
    calc = {"calculator": "calc.loop", "formula": "PM = 180 + arg(T(fc))", "inputs": {},
            "outputs": {"pm": {"value": 62.0, "unit": "deg"}}, "verdict": "pass"}
    by_calc = _finding(parts=["U2"], title="U2 loop margin with the example compensation",
                       claim="Phase margin 62 degrees with the datasheet example compensation.", calculations=[calc])
    assert not score.evaluate(e1, by_calc, BLOCKS, MODES)[0]
    qualified = _finding(parts=["U2"], title="U2 is stable at full load but oscillates at light load",
                         claim="Outside the example envelope the internal compensation leaves no phase margin.")
    assert score.evaluate(e1, qualified, BLOCKS, MODES)[0]
    corner = _finding(parts=["U2"], title="U2 loop is fine at 25 C, fails at -40 C",
                      claim="Outside the example envelope the phase margin collapses at cold.")
    assert score.evaluate(e1, corner, BLOCKS, MODES)[0]
    assert score.asserts_pass(_finding(title="Check passed; no change needed"))
    assert not score.asserts_pass(_finding(title="Inrush passes through D3 into the 3V3 rail"))
    assert not score.asserts_pass(_finding(title="EN divider has not passed the corner check"))


def test_failing_calculation_reason_counts_as_mechanism():
    e1 = _example_expected("E1")
    calc = {"calculator": "calc.loop", "formula": "PM = 180 + arg(T(fc))", "inputs": {},
            "outputs": {"pm": {"value": 12.0, "unit": "deg"}}, "verdict": "fail",
            "reason": "phase margin 12 degrees with L and COUT outside the example envelope"}
    f = _finding(parts=["U2"], title="U2 loop", claim="See the loop calculation below.", calculations=[calc])
    assert score.evaluate(e1, f, BLOCKS, MODES)[0]
    calc["verdict"] = "info"
    assert not score.evaluate(e1, f, BLOCKS, MODES)[0]


def test_equivalent_block_from_the_table_matches():
    e6 = _example_expected("E6")
    r8 = next(f for f in score.load_json(EVALS / "example" / "review.json")["findings"] if f["id"] == "R8")
    assert r8["block"] == "camera_csi"
    assert score.evaluate(e6, r8, BLOCKS, MODES)[0]
    assert score.evaluate(e6, dict(r8, block="resets_supervisors_watchdogs"), BLOCKS, MODES)[0]
    assert not score.evaluate(e6, dict(r8, block="thermal"), BLOCKS, MODES)[0]
    assert not score.evaluate(_example_expected("E1"), dict(r8, block="camera_csi", parts=["U2"],
                                                           claim=OSC), BLOCKS, MODES)[0]


def test_equivalence_table_uses_schema_vocab_and_cites_checklist_items():
    for mode, (blocks, items) in score.EQUIVALENT_BLOCKS.items():
        assert mode in MODES and blocks <= BLOCKS, mode
        for item in items:
            assert any(f"## {item} " in p.read_text(encoding="utf-8")
                       for p in (ROOT / "skill" / "checklists").glob("*.md")), (mode, item)


def test_malformed_calculations_are_ignored_not_fatal():
    f = _finding(parts=["U2"], claim=OSC, calculations=["calc.loop says fail"])
    assert score.evaluate(dict(LOOP, parts=["U2"]), f, BLOCKS, MODES)[0]


def test_expected_without_location_matches_on_block_and_mechanism():
    exp = {"block": "thermal", "failure_mode": "thermal_overstress", "keywords": ["junction|overheat"]}
    f = _finding(block="thermal", failure_mode="thermal_overstress", claim="Junction reaches 140 C at 85 C ambient.")
    assert score.evaluate(exp, f, BLOCKS, MODES)[0]


def test_one_to_one_pairing_repeats_and_known_good():
    expected = {
        "board": "t",
        "findings": [dict(LOOP, id="E1", parts=["U2", "L2"])],
        "known_good": [{"id": "K1", "block": "clocks_crystals", "parts": ["R5"], "failure_mode": "other",
                        "keywords": ["ground"]}],
    }
    review = [
        _finding(id="A", parts=["U2"], claim=OSC),
        _finding(id="B", parts=["U2", "L2"], claim=OSC),
        _finding(id="C", block="clocks_crystals", parts=["R5"], failure_mode="open_net", title="OSC_OUT to ground"),
        _finding(id="D", block="ldo", parts=["U3"], failure_mode="dropout"),
    ]
    r = score.score_board(expected, review, SCHEMA)
    assert r["matches"] == [{"expected": "E1", "review": "B"}]
    assert r["duplicate_ids"] == []
    assert r["false_positives"][0] == {"id": "A", "title": "test finding", "repeats": "E1"}
    assert r["known_good_hits"] == [{"review": "C", "known_good": "K1"}]
    assert (r["tp"], r["fp"], r["recall"], r["precision"]) == (1, 3, 1.0, pytest.approx(1 / 4))


DROPOUT = {"id": "E1", "title": "x", "block": "ldo", "parts": ["U3"], "failure_mode": "dropout",
           "keywords": ["dropout"]}
HEADROOM = "U3 is in dropout at the 3.0 V input minimum."


def test_pairing_finds_the_maximum_number_of_matches():
    expected = {"board": "t", "findings": [dict(LOOP, id="E1", parts=["U1", "U2"]), dict(LOOP, id="E2", parts=["U1"])]}
    review = [_finding(id="A", parts=["U1"], claim=OSC), _finding(id="B", parts=["U2"], claim=OSC)]
    r = score.score_board(expected, review, SCHEMA)
    assert r["matches"] == [{"expected": "E1", "review": "B"}, {"expected": "E2", "review": "A"}]
    assert (r["tp"], r["fp"]) == (2, 0)


def test_specificity_breaks_ties_between_maximum_pairings():
    expected = {"board": "t", "findings": [dict(LOOP, id="E1", parts=["U2"])]}
    review = [_finding(id="WIDE", parts=["U2", "U3", "U4", "U5"], claim=OSC),
              _finding(id="NARROW", parts=["U2"], claim=OSC)]
    assert score.score_board(expected, review, SCHEMA)["matches"] == [{"expected": "E1", "review": "NARROW"}]


def test_repeats_count_against_precision_unless_parts_and_mode_agree():
    expected = {"board": "t", "findings": [dict(LOOP, id="E1", parts=["U2", "L2"], nets=["3V3"])]}
    review = [
        _finding(id="B", parts=["U2", "L2"], nets=["3V3"], claim=OSC),
        _finding(id="SAME", parts=["L2", "U2"], claim=OSC, check="buck_regulator#BR-2"),
        _finding(id="GENERIC", parts=["U2"], claim=OSC),
        _finding(id="OTHER_MODE", parts=["U2", "L2"], failure_mode="saturation", claim=OSC),
    ]
    r = score.score_board(expected, review, SCHEMA)
    assert r["matches"] == [{"expected": "E1", "review": "B"}]
    assert r["duplicate_ids"] == ["SAME"]
    assert r["false_positives"] == [{"id": "GENERIC", "title": "test finding", "repeats": "E1"},
                                    {"id": "OTHER_MODE", "title": "test finding", "repeats": "E1"}]
    assert (r["tp"], r["fp"], r["precision"]) == (1, 2, pytest.approx(1 / 3))


def test_refuted_findings_excluded_unless_asked():
    expected = {"board": "t", "findings": [DROPOUT]}
    review = [_finding(block="ldo", parts=["U3"], failure_mode="dropout", claim=HEADROOM,
                       verification={"status": "WRONG"})]
    assert score.score_board(expected, review, SCHEMA)["tp"] == 0
    assert score.score_board(expected, review, SCHEMA, include_refuted=True)["tp"] == 1


def test_example_board_scores():
    r = score.score_board(score.load_json(EVALS / "example" / "expected.json"),
                          score.review_list(score.load_json(EVALS / "example" / "review.json")), SCHEMA)
    assert (r["tp"], r["fp"], r["duplicates"], r["refuted_excluded"]) == (4, 3, 0, 1)
    assert {m["id"] for m in r["misses"]} == {"E2", "E5"}
    assert {"expected": "E6", "review": "R8"} in r["matches"]
    assert r["known_good_hits"] == [{"review": "R7", "known_good": "K1"}]
    assert r["recall_by_severity"] == {"blocker": [3, 3], "major": [1, 3]}
    assert r["schema_errors"] == []


def test_manifest_totals_split_and_bug_classes(tmp_path):
    result = score.score_manifest(EVALS / "manifest.json", schema=SCHEMA)
    dev, held = result["overall"]["dev"], result["overall"]["held-out"]
    assert (dev["tp"], dev["expected"], dev["fp"]) == (9, 13, 6)
    assert (held["tp"], held["expected"], held["fp"]) == (1, 2, 1)
    classes = result["detected_by_bug_class"]["dev"]
    assert classes["bead_cap_resonance_near_fsw"] == [0, 1]
    assert classes["upstream_cannot_sink"] == [0, 1]
    assert classes["wrong_divider_value"] == [1, 1]
    assert result["unknown_bug_classes"] == []
    clean = next(b for b in result["boards"] if b["board"] == "seeded_example_clean")
    assert (clean["expected"], clean["fp"], clean["precision"]) == (0, 2, 0.0)


def test_reviews_dir_overrides_and_missing_files_are_skipped(tmp_path):
    (tmp_path / "boards").mkdir()
    manifest = {"boards": [
        {"name": "a", "split": "dev", "expected": "a.json"},
        {"name": "b", "split": "held-out", "expected": "missing.json"},
    ]}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "a.json").write_text(json.dumps({"board": "a", "findings": [DROPOUT]}))
    (tmp_path / "boards" / "a.json").write_text(json.dumps(
        [_finding(block="ldo", parts=["U3"], failure_mode="dropout", claim=HEADROOM)]))
    result = score.score_manifest(tmp_path / "manifest.json", tmp_path / "boards", schema=SCHEMA)
    assert result["overall"]["dev"]["recall"] == 1.0
    assert result["skipped"] == [{"board": "b", "split": "held-out", "reason": "expected file not found (missing.json)"}]


def test_bad_split_rejected(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"boards": [{"name": "a", "split": "test", "expected": None}]}))
    with pytest.raises(ValueError):
        score.score_manifest(tmp_path / "manifest.json", schema=SCHEMA)


def test_heldout_details_hidden_unless_revealed():
    result = score.score_manifest(EVALS / "manifest.json", schema=SCHEMA)
    hidden = score.format_report(result)
    shown = score.format_report(result, reveal_heldout=True)
    assert "MISS H2" not in hidden and "details hidden for a held-out board" in hidden
    assert "MISS H2" in shown


def test_heldout_details_hidden_in_json_unless_revealed(capsys):
    def heldout(*flags):
        assert score.main(["--manifest", str(EVALS / "manifest.json"), "--json", *flags]) == 0
        return next(b for b in json.loads(capsys.readouterr().out)["boards"] if b["split"] == "held-out")
    hidden = heldout()
    assert (hidden["tp"], hidden["expected"], hidden["fp"]) == (1, 2, 1)
    assert "H1" not in json.dumps(hidden) and "H2" not in json.dumps(hidden) and "Q2" not in json.dumps(hidden)
    assert hidden["details_hidden"] is True
    assert heldout("--reveal-heldout")["misses"][0]["id"] == "H2"


def test_cli_single_board(capsys):
    rc = score.main(["--expected", str(EVALS / "example" / "expected.json"),
                     "--review", str(EVALS / "example" / "review.json"), "--json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["tp"] == 4


def test_expected_items_need_keywords():
    expected = {"board": "t", "findings": [{"id": "E1", "title": "x", "block": "ldo", "failure_mode": "dropout"}]}
    r = score.score_board(expected, [], SCHEMA)
    assert any("missing keywords" in e for e in r["expected_errors"])
