import shutil
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
