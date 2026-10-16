"""python -m boardreview datasheets: every MPN with its datasheet URL, and an optional PDF download (local only)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from boardreview.__main__ import main

XML = """<?xml version="1.0" encoding="UTF-8"?>
<!-- Synthetic netlist for the datasheets command. No real board data. -->
<export version="E">
  <design><source>synthetic.kicad_sch</source><tool>Eeschema 8.0.4</tool></design>
  <components>
    <comp ref="U1"><value>SYN-LDO</value><datasheet>{u1}</datasheet>
      <fields><field name="MPN">SYN-LDO-18</field><field name="Manufacturer">Synthetic</field></fields></comp>
    <comp ref="U2"><value>SYN-BUCK</value><datasheet>~</datasheet>
      <fields><field name="MPN">SYN-BUCK-1</field></fields></comp>
    <comp ref="U3"><value>SYN-BUCK</value><datasheet>~</datasheet>
      <fields><field name="MPN">SYN-BUCK-1</field></fields></comp>
    <comp ref="R1"><value>10k</value><fields><field name="MPN">SYN-R10K</field></fields></comp>
    <comp ref="R2"><value>10k</value><fields><field name="MPN">SYN-R10K</field></fields></comp>
    <comp ref="U4"><value>SYN-SW</value><fields><field name="MPN">SYN-SW</field>
      <field name="Datasheet">{u4}</field></fields></comp>
    <comp ref="U5"><value>SYN-BIG</value><fields><field name="MPN">SYN-BIG</field>
      <field name="Datasheet">{u5}</field></fields></comp>
    <comp ref="U6"><value>SYN-GONE</value><fields><field name="MPN">SYN-GONE</field>
      <field name="Datasheet">{u6}</field></fields></comp>
  </components>
  <nets>
    <net code="1" name="VIN"><node ref="U1" pin="1"/><node ref="U2" pin="1"/><node ref="U3" pin="1"/>
      <node ref="R1" pin="1"/><node ref="U4" pin="1"/><node ref="U5" pin="1"/><node ref="U6" pin="1"/></net>
    <net code="2" name="GND"><node ref="U1" pin="2"/><node ref="U2" pin="2"/><node ref="U3" pin="2"/>
      <node ref="R1" pin="2"/><node ref="R2" pin="1"/><node ref="U4" pin="2"/><node ref="U5" pin="2"/>
      <node ref="U6" pin="2"/></net>
  </nets>
</export>
"""
PDF = b"%PDF-1.7\n% synthetic test document, not a vendor file\n%%EOF\n"
HTML = b"<!doctype html><html><body>Please enable JavaScript to view this page.</body></html>"


class _Server(BaseHTTPRequestHandler):
    agents: list[str] = []

    def do_GET(self):  # noqa: N802
        _Server.agents.append(self.headers.get("User-Agent", ""))
        body, ctype, code = {"/sw.pdf": (PDF, "application/pdf", 200), "/landing": (HTML, "text/html", 200),
                             "/big.pdf": (PDF + b"0" * 5000, "application/pdf", 200)}.get(self.path,
                                                                                          (b"no", "text/plain", 404))
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture()
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Server)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _board(tmp_path, base):
    local = tmp_path / "local.pdf"
    local.write_bytes(PDF)
    xml = XML.format(u1=local.as_uri(), u4=f"{base}/sw.pdf", u5=f"{base}/big.pdf", u6=f"{base}/landing")
    (tmp_path / "board.xml").write_text(xml, encoding="utf-8")
    (tmp_path / "bom.csv").write_text(f"Reference,MPN,Datasheet URL\nU2,SYN-BUCK-1,{base}/missing.pdf\n"
                                      "U3,SYN-BUCK-1,\n", encoding="utf-8")
    return tmp_path / "board.xml", tmp_path / "bom.csv"


def _rows(out):
    return {d["mpn"]: d for d in json.loads((out / "datasheets.json").read_text(encoding="utf-8"))["datasheets"]}


def test_lists_every_mpn_with_parts_url_and_status(tmp_path):
    netlist, bom = _board(tmp_path, "http://127.0.0.1:9")
    out = tmp_path / "ds"
    assert main(["datasheets", "--netlist", str(netlist), "--bom", str(bom), "--out", str(out)]) == 0
    rows = _rows(out)
    assert set(rows) == {"SYN-LDO-18", "SYN-BUCK-1", "SYN-R10K", "SYN-SW", "SYN-BIG", "SYN-GONE"}
    assert rows["SYN-BUCK-1"]["parts"] == ["U2", "U3"]
    assert rows["SYN-BUCK-1"]["url"] == "http://127.0.0.1:9/missing.pdf"
    assert rows["SYN-LDO-18"]["url"].startswith("file:")
    assert rows["SYN-R10K"]["status"] == "no_url" and rows["SYN-R10K"]["parts"] == ["R1", "R2"]
    assert rows["SYN-SW"]["status"] == "listed"
    md = (out / "datasheets.md").read_text(encoding="utf-8")
    assert "| MPN | Parts | URL | Status |" in md and "| SYN-R10K | R1, R2 |" in md
    assert not list(out.glob("*.pdf"))


def test_download_keeps_pdfs_and_records_html_pages_as_unavailable(tmp_path, server):
    netlist, bom = _board(tmp_path, server)
    out = tmp_path / "ds"
    argv = ["datasheets", "--netlist", str(netlist), "--bom", str(bom), "--out", str(out), "--download",
            "--max-bytes", "1000", "--timeout", "5"]
    assert main(argv) == 0
    rows = _rows(out)
    assert rows["SYN-SW"]["status"] == "downloaded"
    assert (out / rows["SYN-SW"]["file"]).read_bytes() == PDF
    assert rows["SYN-LDO-18"]["status"] == "downloaded"
    assert rows["SYN-GONE"]["status"] == "unavailable"
    assert "not a PDF" in rows["SYN-GONE"]["reason"] and "text/html" in rows["SYN-GONE"]["reason"]
    assert rows["SYN-BIG"]["status"] == "unavailable" and "1000 bytes" in rows["SYN-BIG"]["reason"]
    assert rows["SYN-BUCK-1"]["status"] == "unavailable" and "404" in rows["SYN-BUCK-1"]["reason"]
    assert rows["SYN-R10K"]["status"] == "no_url"
    assert sorted(p.name for p in out.glob("*.pdf")) == sorted([rows["SYN-SW"]["file"], rows["SYN-LDO-18"]["file"]])
    assert all("Mozilla" in a for a in _Server.agents)


def test_eda_agent_parameters_carry_the_datasheet(tmp_path):
    payload = {"components": [{"designator": "U1", "comment": "SYN-LDO", "parameters": {
        "Manufacturer Part Number": "SYN-LDO-33", "ComponentLink1URL": "https://example.invalid/ldo.pdf"},
        "pins": [{"pin": "1", "name": "IN", "net": "VIN"}, {"pin": "2", "name": "GND", "net": "GND"}]}]}
    (tmp_path / "board.json").write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "ds"
    assert main(["datasheets", "--netlist", str(tmp_path / "board.json"), "--out", str(out)]) == 0
    assert _rows(out)["SYN-LDO-33"]["url"] == "https://example.invalid/ldo.pdf"


def test_only_http_https_and_file_urls_are_fetched(tmp_path):
    from boardreview.datasheets import fetch

    status, reason, _, _ = fetch("ftp://example.invalid/x.pdf", tmp_path / "x.pdf")
    assert status == "unavailable" and "ftp" in reason
    assert not (tmp_path / "x.pdf").exists()
