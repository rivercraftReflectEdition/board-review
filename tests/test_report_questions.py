"""Report shape when most findings are open questions and most checks could not run."""

import json
import re
from pathlib import Path

import pytest

from boardreview.__main__ import main
from boardreview.report import review as rv
from test_report import data_of, ids_of, visible_text

BOARD = Path(__file__).parent / "fixtures" / "report"


def _finding(fid, status, **kw):
    f = {"id": fid, "title": f"{fid} title says what breaks", "severity": "major", "block": "buck_regulator",
         "failure_mode": "loop_instability", "parts": ["U2"], "claim": "A synthetic claim long enough.",
         "evidence": [{"kind": "netlist", "ref": "U2.4"}], "fix": "A fix.", "verification": {"status": status}}
    f.update(kw)
    return f


def _question(fid, missing, consequence, settle):
    return _finding(fid, "UNVERIFIABLE", not_published=[{"item": missing, "searched": "supplied PDFs",
                                                         "consequence": consequence, "action": settle}],
                    bench_test=f"Bench: {settle}")


def _check(cid, verdict, reason="", **kw):
    c = {"id": cid, "block": "buck_regulator", "instance": "U2", "item": "BR-1", "verdict": verdict}
    if reason:
        c["reason"] = reason
    c.update(kw)
    return c


@pytest.fixture(scope="module")
def mostly_open(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("questions")
    facts = tmp / "facts"
    assert main(["prep", str(BOARD / "board.kicad.xml"), "--out", str(facts)]) == 0
    findings = [_finding("F-001", "CONFIRMED", title="R23 fitted on the PCB joins two rails"),
                _question("F-002", "U6 switching frequency", "vendor_question", "Get the SYN-BUCK datasheet"),
                _question("F-003", "bead impedance at DC bias", "bench_test", "Measure ripple on 3V3A"),
                _question("F-004", "LDO output capacitor ESR range", "model", "Fit a model from the vendor curve")]
    checks = [_check("a.BR-1", "unknown", "Datasheet not supplied for U6; no digest."),
              _check("b.BR-1", "unknown", "No datasheet available for SYN-BUCK."),
              _check("c.BR-1", "unknown", "Bead model unavailable: no impedance curve at bias."),
              _check("d.BR-1", "unknown", "Load step size not known.", bench_test="Step the load 0.1 to 1 A."),
              _check("e.BR-1", "unknown", "Mystery."),
              _check("f.BR-1", "pass", summary="Fine."),
              _check("g.BR-1", "fail", finding="F-001")]
    (tmp / "findings.json").write_text(json.dumps({"board": "Open board", "findings": findings}), encoding="utf-8")
    (tmp / "checks.json").write_text(json.dumps({"checks": checks}), encoding="utf-8")
    bench = [{"id": "b1", "title": "Measure ripple on 3V3A", "findings": ["F-003"]}]
    (tmp / "bench.json").write_text(json.dumps(bench), encoding="utf-8")
    out = tmp / "report"
    assert main(["report", "--findings", str(tmp / "findings.json"), "--facts", str(facts), "--bench",
                 str(tmp / "bench.json"), "--out", str(out)]) == 0
    return out


def test_verdict_counts_confirmed_problems_and_open_questions_apart(mostly_open):
    text = (mostly_open / "report.html").read_text(encoding="utf-8")
    seen = visible_text(text)
    assert "1 confirmed problem, 3 open questions" in seen
    assert "Builds, with one major finding to fix or accept." in seen
    assert data_of(text)["findings"] == ["F-001"]
    md = (mostly_open / "report.md").read_text(encoding="utf-8")
    assert "1 confirmed problem, 3 open questions" in md


def test_open_questions_are_apart_from_problems_and_carry_no_severity_chip(mostly_open):
    text = (mostly_open / "report.html").read_text(encoding="utf-8")
    problems = text.split('id="br-list"')[1].split("</section>")[0]
    assert 'id="F-001"' in problems and 'id="F-002"' not in problems
    questions = text.split('id="br-questions"')[1].split("</section>")[0]
    for fid in ("F-002", "F-003", "F-004"):
        row = questions.split(f'id="{fid}"')[1].split("</article>")[0]
        assert 'class="chip major"' not in row and "Open question" in row
        assert 'type="checkbox"' not in row
    q3 = visible_text(questions.split('id="F-003"')[1].split("</article>")[0])
    assert "Missing: bead impedance at DC bias" in q3
    assert "Settles it: Bench: Measure ripple on 3V3A" in q3
    assert "Bench step 1." in q3
    q2 = visible_text(questions.split('id="F-002"')[1].split("</article>")[0])
    assert "Document: Get the SYN-BUCK datasheet" in q2
    assert "F-002" in ids_of(text)


def test_unknown_checks_are_summarized_by_reason_and_folded(mostly_open):
    text = (mostly_open / "report.html").read_text(encoding="utf-8")
    fold = re.search(r'<details class="fold" id="br-unknown">(.*?)</details>', text, re.S).group(1)
    summary = re.search(r"<summary>(.*?)</summary>", fold, re.S).group(1)
    assert "5 of 7" in summary
    assert "2 no datasheet" in summary and "1 no model" in summary and "1 needs bench" in summary
    assert "1 other" in summary
    assert "a.BR-1" in fold and "Mystery." in fold
    md = (mostly_open / "report.md").read_text(encoding="utf-8")
    assert "### Checks that could not run" in md and "| No datasheet | 2 |" in md


def test_unknown_reason_categories():
    assert rv.unknown_reason({"reason": "SYN-BUCK datasheet unavailable"}) == "no_datasheet"
    assert rv.unknown_reason({"reason": "x", "not_published": [{"item": "a", "consequence": "model"}]}) == "no_model"
    assert rv.unknown_reason({"reason": "Measure it", "bench_test": "scope"}) == "needs_bench"
    assert rv.unknown_reason({"reason": "Value not published", "not_published": [
        {"item": "a", "consequence": "bench_test"}]}) == "needs_bench"
    assert rv.unknown_reason({"reason": "Mystery."}) == "other"
    erc = {"reason": "Compiler messages and ERC are unavailable.", "bench_test": "Run ERC.", "not_published": [
        {"item": "ERC report", "searched": "supplied files; unavailable sources listed per MPN in digests",
         "consequence": "bench_test"}]}
    assert rv.unknown_reason(erc) == "needs_bench"
    assert rv.unknown_reason({"reason": "Load and source impedance are unavailable.", "bench_test": "x"}) == "needs_bench"
