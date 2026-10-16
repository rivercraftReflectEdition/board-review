import importlib.util
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path

import pytest

from boardreview.__main__ import main
from boardreview.report import plain

ROOT = Path(__file__).resolve().parent.parent
BOARD = Path(__file__).parent / "fixtures" / "report"
SECTIONS = ("br-list", "br-bench", "br-changes", "br-power", "br-unpublished", "br-firmware", "br-known-good",
            "br-coverage", "br-refuted", "br-outputs")

spec = importlib.util.spec_from_file_location("evals_score", ROOT / "evals" / "score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)
FINDING = json.loads((ROOT / "skill" / "schemas" / "finding.schema.json").read_text(encoding="utf-8"))
CHECK = json.loads((ROOT / "skill" / "schemas" / "check_result.schema.json").read_text(encoding="utf-8"))


class Ids(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: list[str] = []
        self.tags = 0

    def handle_starttag(self, tag, attrs):
        self.tags += 1
        self.ids += [v for k, v in attrs if k == "id"]


VOID = {"br", "img", "input", "meta", "link", "hr", "wbr"}


def visible_text(text: str) -> str:
    """Text a reader sees without opening anything: a closed details shows only its summary."""
    out: list[str] = []
    stack: list[tuple[str, bool, bool]] = []
    for m in re.finditer(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)([^>]*)>|([^<]+)", text):
        close, tag, attrs, data = m.groups()
        hidden = stack[-1][1] if stack else False
        if data is not None:
            if not hidden:
                out.append(data)
            continue
        tag = tag.lower()
        if tag in VOID or attrs.rstrip().endswith("/"):
            continue
        if close:
            while stack and stack.pop()[0] != tag:
                pass
        elif tag in ("script", "style", "svg", "title", "head"):
            stack.append((tag, True, True))
        elif tag == "details":
            stack.append((tag, hidden or not re.search(r"\sopen(?=[\s>]|$)", attrs), hidden))
        elif tag == "summary" and stack and stack[-1][0] == "details":
            stack.append((tag, stack[-1][2], stack[-1][2]))
        else:
            stack.append((tag, hidden, hidden))
    return re.sub(r"\s+", " ", "".join(out))


def ids_of(text: str) -> list[str]:
    p = Ids()
    p.feed(text)
    return p.ids


def data_of(text: str) -> dict:
    m = re.search(r'<script type="application/json" id="br-data">(.*?)</script>', text, re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


@pytest.fixture(scope="module")
def facts(tmp_path_factory):
    out = tmp_path_factory.mktemp("facts")
    assert main(["prep", str(BOARD / "board.kicad.xml"), "--out", str(out)]) == 0
    return out


@pytest.fixture(scope="module")
def full(facts, tmp_path_factory):
    out = tmp_path_factory.mktemp("report")
    argv = ["report", "--findings", str(BOARD / "findings.json"), "--facts", str(facts),
            "--bench", str(BOARD / "bench.json"), "--known-good", str(BOARD / "known_good.json"),
            "--previous", str(BOARD / "previous_findings.json"), "--status", str(BOARD / "status.json"),
            "--placement", str(BOARD / "board-pos.csv"), "--pos-units", "mm", "--detail", "full", "--out", str(out)]
    assert main(argv) == 0
    return out


def findings():
    return json.loads((BOARD / "findings.json").read_text(encoding="utf-8"))["findings"]


def test_writes_every_output(full):
    for name in ("report.html", "report_artifact.html", "report.md", "findings.json", "status.json", "analysis.html"):
        assert (full / name).exists(), name
    active = [f["id"] for f in findings() if f["verification"]["status"] != "WRONG"]
    assert sorted(p.stem for p in (full / "tickets").glob("*.md")) == sorted(active)


def test_html_has_every_section_and_every_finding(full):
    text = (full / "report.html").read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")
    ids = ids_of(text)
    for section in SECTIONS:
        assert section in ids, section
    for f in findings():
        assert f["id"] in text
        if f["verification"]["status"] != "WRONG":
            assert f["id"] in ids and f"d-{f['id']}" in ids and f"p-{f['id']}" in ids
        else:
            assert f["id"] not in ids
    assert "Not ready to build. Two blockers." in text
    assert "fonts.googleapis.com" in text and '"IBM Plex Sans", "Segoe UI"' in text
    assert "prefers-color-scheme: dark" in text and "max-width: 560px" in text


def test_element_and_checkbox_ids_are_unique(full):
    for name in ("report.html", "report_artifact.html", "analysis.html"):
        ids = ids_of((full / name).read_text(encoding="utf-8"))
        assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1][:5]
    checks = [i for i in ids_of((full / "report.html").read_text(encoding="utf-8")) if i.startswith("chk-")]
    assert len(checks) == 7 + 7 and "chk-F-003" not in checks


def test_artifact_variant_keeps_state_in_the_db(full):
    art = (full / "report_artifact.html").read_text(encoding="utf-8")
    local = (full / "report.html").read_text(encoding="utf-8")
    assert art.startswith("<title>")
    for code in ('window.claude.use("db")', 'window.claude.use("user")', 'collection("status").onSnapshot',
                 'db.doc("status/" + id)', "user.profiles(ids)", "invalid_argument", "useLocal()"):
        assert code in art, code
    assert "window.claude" not in local and "localStorage" in local
    assert data_of(art) == data_of(local)


def test_page_data_carries_status_key_pointers_and_placement(full):
    d = data_of((full / "report.html").read_text(encoding="utf-8"))
    assert d["key"] == f"Synthetic node-B-{d['hash']}"
    assert d["status"]["F-004"]["done"] is True and d["status"]["b1"]["done"] is True
    assert d["status"]["F-001"]["by"] == "R. D."
    assert d["bench"] == ["b1", "b2", "b3", "b4", "b5", "b6", "b7"]
    r61 = next(c for c in d["pointers"]["F-002"] if c["label"] == "R61")
    rows = dict(r61["dl"])
    assert rows["Sheet"] == "Ethernet"
    assert rows["On the PCB"] == "Bottom, X 56.00 Y 6.00 mm"
    assert "R61.1 on PHY_MODE0" in rows["In this finding"]
    assert d["place"]["parts"]["R61"] == [56.0, 6.0, "b"] and d["place"]["extent_from"] == "parts"
    assert "not the board outline" in d["place"]["caption"]
    assert [c["label"] for c in d["pointers"]["F-001"]] == ["R11", "R10", "U1"]


def test_written_findings_validate_and_carry_the_merged_status(full):
    data = json.loads((full / "findings.json").read_text(encoding="utf-8"))
    for f in data["findings"]:
        assert score.validate(f, FINDING) == [], f["id"]
    by = {f["id"]: f for f in data["findings"]}
    assert by["F-004"]["status"] == {"fixed": True, "fixed_at": "2026-10-14T10:00:00Z"}
    assert by["F-001"]["status"]["fixed"] is True
    assert data["board"] == "Synthetic node"


def test_fixture_checks_validate():
    checks = json.loads((BOARD / "checks.json").read_text(encoding="utf-8"))["checks"]
    for c in checks:
        assert score.validate(c, CHECK) == [], c["id"]
    bad = {"id": "x.EN-1", "block": "ldo", "instance": "U1", "item": "EN-1", "verdict": "not_applicable"}
    assert any("missing reason" in e for e in score.validate(bad, CHECK))


def test_what_changed_matches_old_and_new(full):
    text = (full / "report.html").read_text(encoding="utf-8")
    fold = re.search(r'<details class="fold" id="br-changes">(.*?)</details>', text, re.S).group(1)
    assert "1 reopened · 6 new · 1 fixed · 1 not found again · 1 still open" in fold
    assert re.search(r"Reopened</span></td><td><a href=\"#F-002\">", fold)
    assert "P-02 R32 pulls U6 ALERT" in fold and "R32 is DNP in the new data" in fold
    assert "P-03" in fold and "not confirmed in the data" in fold
    row = text.split('<article class="item sev-blocker" id="F-002">')[1].split("</article>")[0]
    assert '<span class="chip blocker">Reopened</span>' in row and "In the previous review of 2026-09-20 as P-01." in row


def test_math_fold_reads_in_order(full):
    text = (full / "report.html").read_text(encoding="utf-8")
    row = text.split('<article class="item sev-question" id="F-003">')[1].split("</article>")[0]
    math = row.split("<summary>Math</summary>")[1]
    order = [math.index(x) for x in ('class="vw v-', 'class="lead"', 'class="keyline"', "<svg", "<figcaption>",
                                     "<summary>The math</summary>")]
    assert order == sorted(order)
    assert "Phase margin <b>30.2°</b> (want 45° or more)" in math
    assert 'href="analysis.html#chk-U2.BR-1"' in row


def test_analysis_has_every_check_and_links_back(full):
    text = (full / "analysis.html").read_text(encoding="utf-8")
    ids = ids_of(text)
    for c in json.loads((BOARD / "checks.json").read_text(encoding="utf-8"))["checks"]:
        assert f"chk-{c['id']}" in ids, c["id"]
    assert 'href="report.html#F-003"' in text
    assert re.search(r'<details class="chk" id="chk-U1.BR-7">', text)
    assert re.search(r'<details class="chk" id="chk-U1.EN-1" open>', text)
    assert "Measured loop gain" in text and "p.18" in text
    assert "The datasheet says EN rising threshold is 1.15 to 1.25 V (synthetic U1 datasheet rev A, p.5)." in text
    assert '<span class="vw v-fail">Fails</span> U1 enable: +5V never turns on' in text
    assert 'class="chip' not in text and "checker 1" not in text
    assert text.count("<svg") >= 6


def test_analysis_default_view_has_no_variable_names(full):
    seen = visible_text((full / "analysis.html").read_text(encoding="utf-8"))
    checks = json.loads((BOARD / "checks.json").read_text(encoding="utf-8"))["checks"]
    calcs = [r for c in checks for r in c.get("results", []) + c.get("simulation", {}).get("results", [])]
    names = {k for r in calcs for k in [*r.get("inputs", {}), *r.get("outputs", {})] if "_" in k or len(k) > 2}
    assert len(names) > 20
    leaked = sorted(n for n in names if re.search(rf"(?<![\w.]){re.escape(n)}(?![\w.])", seen) and "_" in n)
    assert leaked == []
    assert "calc." not in seen and "sim.measure" not in seen
    assert "Fails" in seen and "Phase margin" in seen and "(want 45° or more)" in seen
    assert "The math" in seen and "BR-1" in seen


def test_a_check_better_than_its_calculation_is_flagged():
    calc = {"calculator": "calc.lc_tank.lc_filter", "name": "LC filter", "verdict": "marginal"}
    check = {"id": "FB1.FLT-1", "verdict": "pass", "results": [calc]}
    assert plain.check_problems(check) and "calc.lc_tank.lc_filter" in plain.check_problems(check)[0]
    assert plain.check_problems(check, plain=True)[0].startswith("This check says Passes")
    assert plain.check_problems(check | {"summary": "No harmonic reaches 145 kHz."}) == []
    assert plain.check_problems(check | {"verdict": "fail"}) == []
    for c in json.loads((BOARD / "checks.json").read_text(encoding="utf-8"))["checks"]:
        assert plain.check_problems(c) == [], c["id"]


def test_markdown_report_and_tickets(full):
    md = (full / "report.md").read_text(encoding="utf-8")
    for head in ("## Summary", "## What changed", "## Findings", "## Required footprints", "## Firmware handoff",
                 "## Accepted risks and deviations", "## Bench test plan", "## Known-good list", "## Appendix"):
        assert head in md, head
    for f in findings():
        assert f["id"] in md
    assert "calc.loop.margins" in md and "| out | Phase margin | 30.2° |" in md
    assert "Phase margin 30.2° (want 45° or more)" in md
    ticket = (full / "tickets" / "F-002.md").read_text(encoding="utf-8")
    assert ticket.startswith("# No Ethernet link") and "Fix: DNP R61." in ticket and "Verify: Bench step 3." in ticket
    assert "\u2014" not in md + ticket


def test_report_reads_ipc_in_the_facts_folder_and_builds_bench_from_findings(facts, tmp_path):
    local = tmp_path / "facts"
    shutil.copytree(facts, local)
    shutil.copy(BOARD / "board.d356", local / "board.d356")
    flist = [f for f in findings() if f["id"] != "F-008"]
    (tmp_path / "f.json").write_text(json.dumps(flist), encoding="utf-8")
    out = tmp_path / "out"
    assert main(["report", "--findings", str(tmp_path / "f.json"), "--facts", str(local), "--out", str(out)]) == 0
    text = (out / "report.html").read_text(encoding="utf-8")
    d = data_of(text)
    assert d["place"]["kind"] == "ipc356" and d["place"]["extent_from"] == "pads"
    assert d["bench"] == ["b1", "b2"]
    assert "br-changes" not in ids_of(text) and "br-refuted" not in ids_of(text)
    assert "No checks.json was given" in text
    assert not (out / "analysis.html").exists()


def test_clashing_ids_stop_the_report(facts, tmp_path):
    (tmp_path / "bench.json").write_text(json.dumps([{"id": "F-001", "title": "clash"}]), encoding="utf-8")
    with pytest.raises(SystemExit, match="F-001 is used twice"):
        main(["report", "--findings", str(BOARD / "findings.json"), "--facts", str(facts),
              "--bench", str(tmp_path / "bench.json"), "--out", str(tmp_path / "out")])
