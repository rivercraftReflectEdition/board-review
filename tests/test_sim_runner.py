import math
import os
import shutil
import subprocess
import sys
import time
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


class _SleepyBackend:
    """A stand-in simulator that starts a grandchild, records its PID, and outlives any timeout."""

    name = "sleepy"

    def __init__(self, pid_file: Path):
        self.pid_file = pid_file

    def command(self, netlist: Path, ascii_raw: bool = False, solver: str | None = None) -> list[str]:
        child = "import time; time.sleep(30)"
        code = (f"import subprocess, sys, time; p = subprocess.Popen([sys.executable, '-c', {child!r}]); "
                f"open({str(self.pid_file)!r}, 'w').write(str(p.pid)); time.sleep(30)")
        return [sys.executable, "-c", code]

    def outputs(self, netlist: Path) -> tuple[Path, Path]:
        return netlist.with_suffix(".raw"), netlist.with_suffix(".log")

    def env(self, ascii_raw: bool) -> dict[str, str] | None:
        return None


def _alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out.split()
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_timeout_kills_the_simulator_and_its_children(tmp_path):
    pid_file = tmp_path / "child.pid"
    t0 = time.monotonic()
    res = run("* t\nR1 a 0 1\n.op\n", tmp_path, "sleepy", timeout_s=3, backend=_SleepyBackend(pid_file))
    assert res.timed_out and not res.ok
    assert time.monotonic() - t0 < 20
    assert not _alive(int(pid_file.read_text()))


LOG_MEAS_FORMS = """Files loaded:
C:\\x\\meas.net

f_45deg: ph(V(out))=-45 AT 1000.99644414
g1k: V(out) =(-3.01030150952dB,-45.0000102435\u00b0) at 1000
gpolar: V(out) =(0.707106654769,-45.0000102435\u00b0) at 1000
gcart: V(out) =(0.499999821218,-0.5) at 1000
t63: V(out)=0.632 AT 1.1001720146e-05
v20: V(out) =0.850356856676 at 2e-05
vavg: AVG(V(out) )=0.900169485747 FROM 1e-05 TO 5e-05
trise=2.19722297281e-05 FROM 2.05860642486e-06 TO 2.4030836153e-05
x: vmax*2=1.99989962578
"""

LOG_STEPPED_COMPLEX = """
Measurement: g1k
  step\tV(out) \tat
     1\t(-3.01030150952dB,-45.0000102435\u00b0)\t1000
     2\t(-6.98970252797dB,-63.4349570177\u00b0)\t1000

Measurement: f_45deg
  step\tph(V(out))=-45
     1\t999.999658167
     2\t500.049543835
"""


def test_parse_log_measurement_forms():
    # Lines as LTspice 26.0.2 prints them: WHEN gives "=target AT value", FIND gives "=value at point"
    m = parse_log(LOG_MEAS_FORMS).measurements
    assert m["f_45deg"] == [pytest.approx(1000.99644414)]
    assert m["t63"] == [pytest.approx(1.1001720146e-05)]
    for name in ("g1k", "gpolar", "gcart"):
        assert m[name][0] == pytest.approx(0.5 - 0.5j, abs=1e-6)
    assert m["v20"] == [pytest.approx(0.850356856676)]
    assert m["vavg"] == [pytest.approx(0.900169485747)]
    assert m["trise"] == [pytest.approx(2.19722297281e-05)]
    assert m["x"] == [pytest.approx(1.99989962578)]
    assert parse_log(LOG_MEAS_FORMS).measured_text["g1k"] == ["(-3.01030150952dB,-45.0000102435\u00b0)"]


def test_parse_log_stepped_complex_meas_table():
    rep = parse_log(LOG_STEPPED_COMPLEX)
    assert rep.measurements["g1k"] == [pytest.approx(0.5 - 0.5j, abs=1e-6), pytest.approx(0.2 - 0.4j, abs=1e-6)]
    assert rep.measurements["f_45deg"] == [pytest.approx(999.999658167), pytest.approx(500.049543835)]


@needs_ltspice
def test_ltspice_meas_results(tmp_path):
    # RC 1k and 159.155 nF: corner 1000 Hz, H(1 kHz) = 0.5 - 0.5j; step rise 10-90 percent = RC ln 9 = 349.7 us
    text = ("* meas\nV1 in 0 PULSE(0 1 1u 10n 10n 5m 10m) AC 1\nR1 in out 1k\nC1 out 0 159.155n\n"
            ".ac dec 50 10 100k\n.meas AC f_45deg WHEN ph(V(out))=-45\n.meas AC g1k FIND V(out) AT 1k\n.end\n")
    m = run(text, tmp_path, "ac").log.measurements
    assert m["f_45deg"][0] == pytest.approx(1000.0, rel=1e-3)
    assert m["g1k"][0] == pytest.approx(0.5 - 0.5j, abs=1e-4)
    tran = text.replace(".ac dec 50 10 100k", ".tran 0 2m 0 1u").split(".meas")[0]
    tran += ".meas TRAN trise TRIG V(out) VAL=0.1 RISE=1 TARG V(out) VAL=0.9 RISE=1\n.end\n"
    assert run(tran, tmp_path, "tran").log.measurements["trise"][0] == pytest.approx(159.155e-6 * math.log(9),
                                                                                    rel=5e-3)


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
    cmd = lt.command(tmp_path / "d.net", ascii_raw=True, solver="alt")
    assert cmd[1:4] == ["-b", "-ascii", "-alt"] and cmd[-1].endswith("d.net")


@needs_ltspice
def test_run_with_lib_dirs_makes_lib_paths_absolute(tmp_path):
    libdir = tmp_path / "my libs"
    libdir.mkdir()
    (libdir / "mydiv.lib").write_text(".subckt DIV a b g\nR1 a b 1k\nR2 b g 1k\n.ends\n")
    text = "* lib dirs\nV1 a 0 2\nX1 a b 0 DIV\n.lib mydiv.lib\n.op\n"
    assert not run(text, workdir=tmp_path, name="plain").ok
    res = run(text, workdir=tmp_path, name="abs", lib_dirs=[libdir])
    assert res.ok, res.summary()
    assert res.raw()["V(b)"][0] == pytest.approx(1.0)
    assert any(f.endswith("mydiv.lib") for f in res.log.files_loaded)


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


@pytest.mark.skipif(not NgSpice().available(), reason="ngspice not installed")
def test_ngspice_rc_transient(tmp_path):
    text = "* rc\nV1 in 0 PULSE(0 1 1u 10n 10n 500u 1m)\nR1 in out 1k\nC1 out 0 10n\n.tran 50n 100u\n.end\n"
    res = run(text, workdir=tmp_path, name="rc", backend=NgSpice())
    assert res.ok, res.summary()
    raw = res.raw()
    t, v = raw.axis(), raw["V(out)"]
    assert v[t > 90e-6].min() == pytest.approx(1.0, abs=0.01)


@needs_ltspice
def test_run_timeout_is_reported(tmp_path):
    slow = "* slow\nV1 a 0 SIN(0 1 1meg)\nR1 a b 1k\nC1 b 0 1n\n.tran 0 10 0 1n\n"
    res = run(slow, workdir=tmp_path, name="slow", timeout_s=3)
    assert res.timed_out and not res.ok
    assert "timed out" in res.summary()
