import shutil
from pathlib import Path

import pytest

from boardreview.sim.runner import LTspice, NgSpice, parse_log, render, run, write_netlist

FIXTURES = Path(__file__).parent / "fixtures" / "sim"
needs_ltspice = pytest.mark.skipif(not LTspice().available(), reason="LTspice not installed")

LOG_OK = """LTspice 26.0.2 for Windows
Circuit: C:\\x\\meas.net
Start Time: Wed Oct 14 19:41:31 2026
solver = Normal
Maximum thread count: 12
Direct Newton iteration failed to find operating point.
Starting Gmin stepping
Gmin stepping succeeded in finding the operating point.
Total elapsed time: 8.313 seconds.

Files loaded:
C:\\x\\meas.net
C:\\Users\\me\\AppData\\Local\\LTspice\\lib\\sub\\LTC3633A.sub

vmax: MAX(V(out))=0.86223256588 FROM 0 TO 0.005
Measurement "fail" FAIL'ed
"""

LOG_SYNTAX = """C:\\x\\bad.net(3): Expected resistor parameter(s) here.
R1 in out
         ^

"""

LOG_STEPPED_MEAS = """
.step c=1e-06
.step c=2e-06
Total elapsed time: 0.1 seconds.

Measurement: vpk
  step\tMAX(v(out))\tFROM\tTO
     1\t1.75\t0\t5e-05
     2\t1.62\t0\t5e-05

"""


def test_parse_log_ok_run():
    rep = parse_log(LOG_OK)
    assert rep.errors == ()
    assert rep.elapsed_s == pytest.approx(8.313)
    assert rep.measurements["vmax"] == [pytest.approx(0.86223256588)]
    assert rep.failed_measurements == ("fail",)
    assert any("Gmin stepping succeeded" in n for n in rep.notes)
    assert rep.files_loaded[-1].endswith("LTC3633A.sub")


def test_parse_log_syntax_error_keeps_context():
    rep = parse_log(LOG_SYNTAX)
    assert len(rep.errors) == 1
    assert "bad.net(3)" in rep.errors[0] and "R1 in out" in rep.errors[0]


def test_parse_log_stepped_meas_table():
    rep = parse_log(LOG_STEPPED_MEAS)
    assert rep.steps == ({"c": 1e-6}, {"c": 2e-6})
    assert rep.measurements["vpk"] == [1.75, 1.62]


def test_render_refuses_missing_values():
    assert render("R1 a b $r", r=1e3) == "R1 a b 1000"
    with pytest.raises(KeyError):
        render("R1 a b $r")


def test_write_netlist_adds_title_and_end(tmp_path):
    p = write_netlist("R1 a 0 1k\n.op", tmp_path / "x.net")
    lines = p.read_text().splitlines()
    assert lines[0].startswith("*") and lines[1] == "R1 a 0 1k" and lines[-1] == ".end"


def test_ngspice_command_shape(tmp_path):
    ng = NgSpice(exe="ngspice")
    cmd = ng.command(tmp_path / "d.net")
    assert cmd[:2] == ["ngspice", "-b"] and "-r" in cmd and "-o" in cmd


def test_ltspice_command_flags(tmp_path):
    lt = LTspice(exe="LTspice.exe")
    cmd = lt.command(tmp_path / "d.net", ascii_raw=True, solver="alt", include_dir=tmp_path)
    assert cmd[1:4] == ["-b", "-ascii", "-alt"]
    assert cmd[4] == f"-I{tmp_path}" and cmd[-1].endswith("d.net")


@needs_ltspice
def test_run_text_netlist_and_remove_stale_outputs(tmp_path):
    (tmp_path / "rc.raw").write_bytes(b"stale")
    text = (FIXTURES / "rc_tran.net").read_text()
    res = run(text, workdir=tmp_path, name="rc")
    assert res.ok, res.summary()
    assert res.raw_path.stat().st_size > 1000
    assert res.log.elapsed_s is not None
    assert "ok" in res.summary()


@needs_ltspice
def test_run_surfaces_syntax_error(tmp_path):
    shutil.copy(FIXTURES / "syntax_error.net", tmp_path / "bad.net")
    res = run(tmp_path / "bad.net")
    assert not res.ok
    assert any("bad.net(3)" in e for e in res.log.errors)
    with pytest.raises(RuntimeError, match="bad.net"):
        res.raw()


@needs_ltspice
def test_run_surfaces_missing_library(tmp_path):
    res = run("* missing lib\nV1 in 0 1\nX1 in 0 FOO\n.lib nosuchfile.lib\n.op\n", workdir=tmp_path, name="ml")
    assert not res.ok
    assert any("File not found" in e for e in res.log.errors)


@needs_ltspice
def test_run_timeout_is_reported(tmp_path):
    slow = "* slow\nV1 a 0 SIN(0 1 1meg)\nR1 a b 1k\nC1 b 0 1n\n.tran 0 10 0 1n\n"
    res = run(slow, workdir=tmp_path, name="slow", timeout_s=3)
    assert res.timed_out and not res.ok
    assert "timed out" in res.summary()
