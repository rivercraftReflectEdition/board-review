import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from boardreview.sim.rawfile import read_plots, read_raw, step_params_from_log
from boardreview.sim.runner import LTspice, run

FIXTURES = Path(__file__).parent / "fixtures" / "sim"
LOCAL = Path(__file__).parent / "local" / "ltc3633"
needs_ltspice = pytest.mark.skipif(not LTspice().available(), reason="LTspice not installed")


def _header(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


def _ltspice_binary_tran(t: np.ndarray, cols: list[np.ndarray], names: list[str], stepped: bool = False) -> bytes:
    flags = "real forward stepped" if stepped else "real forward"
    head = ["Title: synthetic", "Date: today", "Plotname: Transient Analysis", f"Flags: {flags}",
            f"No. Variables: {len(cols) + 1}", f"No. Points: {len(t)}", "Offset: 0", "Command: LTspice",
            "Variables:", "\t0\ttime\ttime"]
    head += [f"\t{i + 1}\t{n}\tvoltage" for i, n in enumerate(names)]
    head.append("Binary:")
    rec = np.dtype([("t", "<f8"), ("v", "<f4", (len(cols),))])
    data = np.zeros(len(t), dtype=rec)
    data["t"] = t
    data["v"] = np.stack(cols, axis=1)
    return _header(head).encode("utf-16-le") + data.tobytes()


def test_binary_mixed_precision_and_negative_time(tmp_path):
    t = np.linspace(0, 1e-3, 11)
    v = np.sin(2 * np.pi * 1e3 * t)
    t_stored = t.copy()
    t_stored[3] = -t_stored[3]
    p = tmp_path / "a.raw"
    p.write_bytes(_ltspice_binary_tran(t_stored, [v, 2 * v], ["V(a)", "V(b)"]))
    raw = read_raw(p)
    assert raw.names == ["time", "V(a)", "V(b)"]
    assert raw.unit("V(a)") == "V" and raw.variables[0].unit == "s"
    assert np.allclose(raw.axis(), t)
    assert np.allclose(raw["b"], 2 * v, atol=1e-6)
    assert raw.n_steps == 1


def test_stepped_split_and_params_from_log(tmp_path):
    t = np.concatenate([np.linspace(0, 1, 5), np.linspace(0, 1, 7)])
    v = np.concatenate([np.full(5, 1.0), np.full(7, 2.0)])
    p = tmp_path / "s.raw"
    p.write_bytes(_ltspice_binary_tran(t, [v], ["V(x)"], stepped=True))
    (tmp_path / "s.log").write_text("\n.step c=1e-06\nfoo\n.step c=4e-06\n")
    raw = read_raw(p)
    assert raw.step_bounds == [(0, 5), (5, 12)]
    assert raw.step_params == [{"c": 1e-6}, {"c": 4e-6}]
    assert np.all(raw.get("V(x)", step=1) == 2.0)


def test_ascii_complex(tmp_path):
    text = _header([
        "Title: x", "Plotname: AC Analysis", "Flags: complex forward log", "No. Variables: 2", "No. Points: 2",
        "Variables:", "\t0\tfrequency\tfrequency", "\t1\tV(out)\tvoltage", "Values:",
        "0\t\t1.0e+02,0.0e+00", "\t5.0e-01,-5.0e-01", "1\t\t1.0e+03,0.0e+00", "\t1.0e-01,-3.0e-01",
    ]).replace("\n", "\r\n")
    p = tmp_path / "ac.raw"
    p.write_bytes(text.encode("ascii"))
    raw = read_raw(p)
    assert raw.is_complex
    assert np.allclose(raw.axis(), [100.0, 1000.0])
    assert np.allclose(raw["out"], [0.5 - 0.5j, 0.1 - 0.3j])


ASCII_TRAN = _header([
    "Title: x", "Plotname: Transient Analysis", "Flags: real forward", "No. Variables: 2", "No. Points: 3",
    "Variables:", "\t0\ttime\ttime", "\t1\tV(out)\tvoltage", "Values:",
    "0\t\t0.0e+00", "\t1.0e+00", "1\t\t1.0e-06", "\t2.5e+00", "2\t\t2.0e-06", "\t-3.0e-01",
]).replace("\n", "\r\n")

ASCII_AC = _header([
    "Title: x", "Plotname: AC Analysis", "Flags: complex forward log", "No. Variables: 2", "No. Points: 2",
    "Variables:", "\t0\tfrequency\tfrequency", "\t1\tV(out)\tvoltage", "Values:",
    "0\t\t1.0e+02,0.0e+00", "\t5.0e-01,-5.0e-01", "1\t\t1.0e+03,0.0e+00", "\t1.0e-01,-3.0e-01",
]).replace("\n", "\r\n")


@pytest.mark.parametrize("encoding", ["ascii", "utf-16-le"])
def test_ascii_real_and_complex_in_either_encoding(tmp_path, encoding):
    (tmp_path / "t.raw").write_bytes(ASCII_TRAN.encode(encoding))
    (tmp_path / "a.raw").write_bytes(ASCII_AC.encode(encoding))
    tran, ac = read_raw(tmp_path / "t.raw"), read_raw(tmp_path / "a.raw")
    assert np.allclose(tran.axis(), [0.0, 1e-6, 2e-6]) and np.allclose(tran["out"], [1.0, 2.5, -0.3])
    assert np.allclose(ac.axis(), [100.0, 1000.0]) and np.allclose(ac["out"], [0.5 - 0.5j, 0.1 - 0.3j])


@pytest.mark.parametrize("encoding", ["ascii", "utf-16-le"])
def test_truncated_ascii_is_rejected(tmp_path, encoding):
    cut = ASCII_TRAN[: ASCII_TRAN.index("2\t\t2.0e-06")]
    (tmp_path / "t.raw").write_bytes(cut.encode(encoding))
    with pytest.raises(ValueError, match="3 points"):
        read_raw(tmp_path / "t.raw")


def test_truncated_binary_is_rejected(tmp_path):
    t = np.linspace(0, 1e-3, 11)
    blob = _ltspice_binary_tran(t, [np.sin(t)], ["V(a)"])
    (tmp_path / "b.raw").write_bytes(blob[:-5])
    with pytest.raises(ValueError, match="11 points"):
        read_raw(tmp_path / "b.raw")


def _binary_head(flags: str, n: int, names: list[str], kind: str = "time") -> bytes:
    head = ["Title: synthetic", "Plotname: Transient Analysis", f"Flags: {flags}", f"No. Variables: {len(names) + 1}",
            f"No. Points: {n}", "Command: LTspice", "Variables:", f"\t0\t{kind}\t{kind}"]
    head += [f"\t{i + 1}\t{nm}\tvoltage" for i, nm in enumerate(names)]
    return _header(head + ["Binary:"]).encode("utf-16-le")


def test_binary_double_and_real_fastaccess_layouts(tmp_path):
    # Layouts as LTspice 26.0.2 writes them: "real double forward" is point-major float64; "-FastAccess" stores
    # the time column (float64) and then each variable's whole trace (float32).
    t = np.linspace(0, 1e-3, 7)
    a, b = np.cos(t * 1e4), np.sin(t * 1e4)
    point_major = np.stack([t, a, b], axis=1).astype("<f8")
    (tmp_path / "d.raw").write_bytes(_binary_head("real double forward", 7, ["V(a)", "V(b)"]) + point_major.tobytes())
    fast = t.astype("<f8").tobytes() + np.concatenate([a, b]).astype("<f4").tobytes()
    (tmp_path / "f.raw").write_bytes(_binary_head("real forward fastaccess", 7, ["V(a)", "V(b)"]) + fast)
    fast_dbl = np.concatenate([t, a, b]).astype("<f8").tobytes()
    (tmp_path / "fd.raw").write_bytes(_binary_head("real double forward fastaccess", 7, ["V(a)", "V(b)"]) + fast_dbl)
    for name, tol in (("d", 0.0), ("f", 1e-7), ("fd", 0.0)):
        raw = read_raw(tmp_path / f"{name}.raw")
        assert np.allclose(raw.axis(), t, rtol=0, atol=0)
        assert np.allclose(raw["a"], a, atol=tol) and np.allclose(raw["b"], b, atol=tol)


def test_complex_fastaccess_is_rejected(tmp_path):
    head = _binary_head("complex forward log fastaccess", 2, ["V(a)"], kind="frequency")
    (tmp_path / "c.raw").write_bytes(head + np.zeros(4, dtype="<c16").tobytes())
    with pytest.raises(ValueError, match="FastAccess"):
        read_raw(tmp_path / "c.raw")


@needs_ltspice
def test_ltspice_fastaccess_and_double_match_the_default_binary(tmp_path):
    shutil.copy(FIXTURES / "rc_tran.net", tmp_path / "rc.net")
    ref = run(tmp_path / "rc.net").raw()
    text = (FIXTURES / "rc_tran.net").read_text().replace(".end", ".options numdgt=15\n.end")
    dbl = run(text, tmp_path, "dbl").raw()
    assert "double" in dbl.flags and np.allclose(dbl["V(out)"], ref["V(out)"], atol=1e-6)
    shutil.copy(tmp_path / "rc.raw", tmp_path / "fa.raw")
    subprocess.run([str(LTspice().exe), "-FastAccess", str(tmp_path / "fa.raw")], capture_output=True, timeout=120)
    fa = read_raw(tmp_path / "fa.raw")
    assert "fastaccess" in fa.flags and np.array_equal(fa.data, ref.data)


def _ascii_plot(plotname: str, flags: str, variables: list[tuple[str, str]], rows: list[list[float]]) -> bytes:
    lines = ["Title: x", f"Plotname: {plotname}", f"Flags: {flags}", f"No. Variables: {len(variables)}",
             f"No. Points: {len(rows)}", "Variables:"]
    lines += [f"\t{i}\t{n}\t{k}" for i, (n, k) in enumerate(variables)]
    lines.append("Values:")
    for k, row in enumerate(rows):
        lines.append(f"{k}\t\t{row[0]:.15e}")
        lines += [f"\t{v:.15e}" for v in row[1:]]
    return _header(lines).replace("\n", "\r\n").encode("ascii")


def test_stepped_operating_point_keeps_one_step_per_point(tmp_path):
    # LTspice 26 writes a stepped .op as one point per step, the step parameter first, and no .step lines in the log
    variables = [("v", "param"), ("V(a)", "voltage"), ("V(b)", "voltage")]
    (tmp_path / "op.raw").write_bytes(_ascii_plot("Operating Point", "real stepped", variables,
                                                  [[1.0, 1.0, 0.5], [2.0, 2.0, 1.0]]))
    (tmp_path / "op.log").write_text("Direct Newton iteration succeeded in finding operating point.\n" * 2)
    raw = read_raw(tmp_path / "op.raw")
    assert raw.step_bounds == [(0, 1), (1, 2)]
    assert raw.step_params == [{"v": 1.0}, {"v": 2.0}]
    assert raw.get("V(b)", step=1).tolist() == [1.0]


def test_descending_stepped_dc_sweep_splits_where_the_sweep_restarts(tmp_path):
    rows = [[v, v / 2] for v in (5.0, 4.0, 3.0)] + [[v, v / 3] for v in (5.0, 4.0, 3.0)]
    (tmp_path / "dc.raw").write_bytes(_ascii_plot("DC transfer characteristic", "real reverse linear stepped",
                                                  [("V1", "voltage"), ("V(b)", "voltage")], rows))
    (tmp_path / "dc.log").write_text(".step r=1000\n.step r=2000\n")
    raw = read_raw(tmp_path / "dc.raw")
    assert raw.step_bounds == [(0, 3), (3, 6)]
    assert raw.step_params == [{"r": 1000.0}, {"r": 2000.0}]


def test_step_count_mismatch_between_log_and_raw_is_reported(tmp_path):
    rows = [[0.0, 1.0], [1.0, 2.0], [0.0, 3.0], [1.0, 4.0]]
    (tmp_path / "s.raw").write_bytes(_ascii_plot("Transient Analysis", "real forward stepped",
                                                 [("time", "time"), ("V(x)", "voltage")], rows))
    (tmp_path / "s.log").write_text(".step c=1\n.step c=2\n.step c=3\n")
    with pytest.raises(ValueError, match="3 .step runs"):
        read_raw(tmp_path / "s.raw")


@needs_ltspice
def test_ltspice_stepped_operating_point(tmp_path):
    text = "* op step\nV1 a 0 {v}\nR1 a b 1k\nR2 b 0 1k\n.step param v list 1 2 3\n.op\n.end\n"
    raw = run(text, tmp_path, "op").raw()
    assert raw.n_steps == 3
    assert [p["v"] for p in raw.step_params] == [1.0, 2.0, 3.0]
    assert [raw.get("V(b)", step=k)[0] for k in range(3)] == pytest.approx([0.5, 1.0, 1.5])


def test_ngspice_style_all_double_two_plots(tmp_path):
    def plot(name: str, n: int) -> bytes:
        head = _header(["Title: ng", f"Plotname: {name}", "Flags: real", "No. Variables: 2", f"No. Points: {n}",
                        "Command: ngspice-42", "Variables:", "\t0\ttime\ttime", "\t1\tv(a)\tvoltage", "Binary:"])
        arr = np.stack([np.arange(n, dtype=float), np.arange(n, dtype=float) * 3], axis=1)
        return head.encode("ascii") + arr.astype("<f8").tobytes()
    p = tmp_path / "ng.raw"
    p.write_bytes(plot("Operating Point", 1) + plot("Transient Analysis", 4))
    plots = read_plots(p)
    assert [pl.plotname for pl in plots] == ["Operating Point", "Transient Analysis"]
    assert np.allclose(read_raw(p)["V(a)"], [0, 3, 6, 9])


def test_step_params_from_log_multi():
    assert step_params_from_log(".step r=1000 c=1e-09\n.step r=2000 c=1e-09") == [
        {"r": 1000.0, "c": 1e-9}, {"r": 2000.0, "c": 1e-9}]


@needs_ltspice
@pytest.mark.parametrize("ascii_raw", [False, True])
def test_ltspice_rc_transient_matches_analytic(tmp_path, ascii_raw):
    shutil.copy(FIXTURES / "rc_tran.net", tmp_path / "rc.net")
    res = run(tmp_path / "rc.net", ascii_raw=ascii_raw)
    assert res.ok, res.summary()
    raw = res.raw()
    t, v = raw.axis(), raw["V(out)"]
    sel = t > 1.02e-6
    expected = 1 - np.exp(-(t[sel] - 1.005e-6) / 10e-6)
    assert np.max(np.abs(v[sel] - expected)) < 5e-3


@needs_ltspice
def test_ltspice_rc_ac_binary_and_ascii_agree(tmp_path):
    shutil.copy(FIXTURES / "rc_ac.net", tmp_path / "b.net")
    shutil.copy(FIXTURES / "rc_ac.net", tmp_path / "a.net")
    rb, ra = run(tmp_path / "b.net").raw(), run(tmp_path / "a.net", ascii_raw=True).raw()
    f = rb.axis()
    h = rb["V(out)"]
    assert rb.is_complex and ra.is_complex
    assert np.allclose(h, 1 / (1 + 2j * np.pi * f * 1e3 * 10e-9), rtol=1e-6)
    assert np.allclose(ra["V(out)"], h, rtol=1e-9)


@needs_ltspice
def test_ltspice_stepped_lc_transient_and_ac(tmp_path):
    shutil.copy(FIXTURES / "lc_step.net", tmp_path / "lc.net")
    shutil.copy(FIXTURES / "lc_ac_step.net", tmp_path / "lcac.net")
    tr = run(tmp_path / "lc.net").raw()
    assert tr.n_steps == 2
    assert [p["c"] for p in tr.step_params] == [1e-6, 4e-6]
    for k in range(2):
        t = tr.axis(step=k)
        assert t[0] == 0 and np.all(np.diff(t) >= 0)
    ac = run(tmp_path / "lcac.net").raw()
    assert ac.n_steps == 2
    for k, c in enumerate((1e-6, 4e-6)):
        f, h = ac.axis(step=k), np.abs(ac.get("V(out)", step=k))
        f0 = 1 / (2 * np.pi * np.sqrt(10e-6 * c))
        assert f[np.argmax(h)] == pytest.approx(f0, rel=0.05)


@pytest.mark.skipif(not (LOCAL / "NEW_3V3_6p8uH_FCM.raw").exists(), reason="local LTC3633 raw not present")
def test_real_ltc3633_raw_loads():
    raw = read_raw(LOCAL / "NEW_3V3_6p8uH_FCM.raw")
    assert raw.data.shape == (62, 188105)
    assert raw.axis()[-1] == pytest.approx(600e-6)
    assert np.all(np.diff(raw.axis()) >= 0)
    assert 3.2 < np.mean(raw["V(out1)"][raw.axis() > 500e-6]) < 3.4
