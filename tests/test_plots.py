import importlib.util
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from boardreview.calc import crystal, divider, lc_tank, loop, mlcc_bias
from boardreview.calc.base import Marker, Plot, Series, keep_indices, plot_from_arrays, si_text
from boardreview.report import svgplot
from boardreview.sim import measure, setups
from boardreview.sim.rawfile import RawFile, Variable
from boardreview.sim.runner import RunResult, parse_log
from boardreview.sim.sanity import SanityReport

ROOT = Path(__file__).resolve().parent.parent
FINDING = json.loads((ROOT / "skill" / "schemas" / "finding.schema.json").read_text(encoding="utf-8"))
spec = importlib.util.spec_from_file_location("evals_score", ROOT / "evals" / "score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)
SVG = "{http://www.w3.org/2000/svg}"


def markers(svg: str) -> dict[str, ET.Element]:
    root = ET.fromstring(svg)
    return {g.get("data-label"): g for g in root.iter(f"{SVG}g") if g.get("class") == "pl-marker"}


def polyline(svg: str, series: str) -> list[tuple[float, float]]:
    root = ET.fromstring(svg)
    pts = []
    for el in root.iter(f"{SVG}polyline"):
        if el.get("data-series") == series:
            pts += [tuple(float(v) for v in p.split(",")) for p in el.get("points").split()]
    return pts


def plot_errors(p: Plot) -> list[str]:
    return score.validate(p.to_dict(), FINDING["$defs"]["plot"], FINDING)


def test_svg_is_well_formed_and_carries_each_marker():
    p = Plot("Synthetic <check> & limits", "Time", "s", (0.0, 1e-3, 2e-3, 3e-3),
             (Series("out", "V", (0.0, 1.0, float("nan"), 2.0)), Series("in", "A", (1.0, 1.5, 2.0, 2.5))),
             markers=(Marker("edge", x=1e-3), Marker("peak <2 V>", x=3e-3, y=2.0, unit="V"),
                      Marker("limit", y=2.2, unit="A"), Marker("off the axis", x=9.0)))
    svg = svgplot.plot_svg(p, "t1")
    root = ET.fromstring(svg)
    assert root.get("role") == "img" and root.find(f"{SVG}title").text == "Synthetic <check> & limits"
    found = markers(svg)
    assert set(found) == {"edge", "peak <2 V>", "limit"}
    assert found["edge"].get("data-kind") == "vline" and float(found["edge"].get("data-x")) == 1e-3
    assert found["peak <2 V>"].get("data-kind") == "point" and float(found["peak <2 V>"].get("data-y")) == 2.0
    assert found["limit"].get("data-kind") == "hline" and found["limit"].get("data-unit") == "A"
    assert len(polyline(svg, "out")) == 3 and len(list(root.iter(f"{SVG}polyline"))) == 3
    lay = svgplot.layout(p)
    assert [pn.unit for pn in lay.panels] == ["V", "A"]
    circle = found["peak <2 V>"].find(f"{SVG}circle")
    assert float(circle.get("cx")) == pytest.approx(lay.x(3e-3), abs=0.06)
    assert float(circle.get("cy")) == pytest.approx(lay.panel_for("V").y(2.0), abs=0.06)
    assert "var(--accent" in svg and "var(--blocker" in svg


def test_bode_crossover_marker_sits_where_the_gain_crosses_0_db():
    blocks = [loop.Integrator(5e3), loop.Pole(50e3), loop.Pole(400e3)]
    r = loop.margins(blocks, 10.0, 10e6)
    fc, pm = r.outputs["fc"].value, r.outputs["pm"].value
    plot = r.plots[0]
    fc_mark = next(m for m in plot.markers if m.label.startswith("fc"))
    pm_mark = next(m for m in plot.markers if m.label.startswith("PM"))
    assert fc_mark.x == fc and pm_mark.x == fc and 180.0 + pm_mark.y == pytest.approx(pm, abs=1e-9)
    svg = svgplot.plot_svg(plot)
    lay = svgplot.layout(plot)
    line = next(markers(svg)[k] for k in markers(svg) if k.startswith("fc")).find(f"{SVG}line")
    x_mark = float(line.get("x1"))
    assert x_mark == pytest.approx(lay.x(fc), abs=0.06)
    y0 = lay.panel_for("dB").y(0.0)
    pts = polyline(svg, "Gain")
    i = next(k for k in range(len(pts) - 1) if (pts[k][1] - y0) * (pts[k + 1][1] - y0) <= 0)
    (xa, ya), (xb, yb) = pts[i], pts[i + 1]
    x_cross = xa + (y0 - ya) / (yb - ya) * (xb - xa)
    assert abs(x_cross - x_mark) < 1.5
    gm_mark = next(m for m in plot.markers if m.label.startswith("GM"))
    assert -gm_mark.y == pytest.approx(r.outputs["gm"].value, abs=1e-6)


def test_bode_of_a_pure_integrator_crosses_at_its_unity_frequency():
    r = loop.margins([loop.Integrator(20e3), loop.Pole(1e6)], 10.0, 100e3)
    lay = svgplot.layout(r.plots[0])
    fc = r.outputs["fc"].value
    assert fc == pytest.approx(20e3 / math.sqrt(1 + (fc / 1e6) ** 2), rel=1e-9)
    assert lay.x(fc) == pytest.approx(svgplot.LEFT + (math.log10(fc) - 1) / 4 * (svgplot.W - svgplot.RIGHT - svgplot.LEFT))


def test_every_calculator_plot_validates_and_marks_the_verdict_point():
    loop_r = loop.margins([loop.Gain(1e3), loop.Integrator(1.0), loop.Pole(2e3), loop.Pole(50e3)], 10.0, 10e6)
    lc = lc_tank.lc_filter(lc_tank.bead_from_spec(220, 100e6, 0.1), lc_tank.Cap(1e-6, 5e-3, 0.5e-9),
                           f_switch_hz=(2.2e6,))
    v = np.linspace(0.0, 16.0, 17)
    mlcc = mlcc_bias.mlcc_effective(10e-6, "X7R", 0.10, 5.0, v, 1 - 0.04 * v, c_required_f=4e-6)
    en = divider.enable_thresholds(1.15, 1.20, 1.26, 1.05, 1.10, 1.15, 57.6e3, 27.4e3, i_leak_a=3e-6, vin_min_v=4.02)
    xtal = crystal.oscillation_margin(80.0, 8e6, 3e-12, 10e-12, gm_a_per_v=1e-3, gm_crit_max_a_per_v=1.95e-3)
    for r, calc in ((loop_r, "calc.loop.margins"), (lc, "calc.lc_tank.lc_filter"),
                    (mlcc, "calc.mlcc_bias.mlcc_effective"), (en, "calc.divider.enable_thresholds"),
                    (xtal, "calc.crystal.oscillation_margin")):
        assert r.plots, calc
        for p in r.plots:
            assert plot_errors(p) == [], calc
            ET.fromstring(svgplot.plot_svg(p))
        schema = FINDING
        assert score.validate(r.to_dict(calc), schema["$defs"]["calculation"], schema) == [], calc
    assert [p.title for p in lc.plots] == ["Filter transfer, source to load", "Impedance seen from the load"]
    assert {m.x for m in lc.plots[0].markers if m.label.startswith("fsw")} == {2.2e6}
    assert next(m for m in lc.plots[0].markers if m.label.startswith("peak")).y == pytest.approx(lc.outputs["peak"].value)
    c_low = next(m for m in mlcc.plots[0].markers if m.label.startswith("C low"))
    assert (c_low.x, c_low.y) == (5.0, pytest.approx(mlcc.outputs["c_low"].value))
    worst = next(m for m in en.plots[0].markers if m.label.startswith("enable worst"))
    assert (worst.x, worst.y) == (pytest.approx(en.outputs["enable_max"].value), 1.26)
    low = en.plots[0].series[1]
    assert np.interp(worst.x, en.plots[0].x, low.y) == pytest.approx(1.26, abs=2e-3)
    limits = {m.label: m.y for m in xtal.plots[0].markers if m.x is None}
    assert limits == {"Gmcritmax 1.95 mA/V": 1.95e-3, "gm / 5": pytest.approx(2e-4)}
    point = next(m for m in xtal.plots[0].markers if m.x is not None)
    assert point.y == pytest.approx(xtal.outputs["gm_crit"].value)


def test_mlcc_without_a_bias_curve_has_no_plot():
    assert mlcc_bias.mlcc_effective(100e-9, "C0G", 0.05).plots == ()


def test_long_series_are_thinned_but_keep_their_peaks():
    y = np.sin(np.linspace(0, 200 * math.pi, 100_001))
    y[54_321] = 7.0
    idx = keep_indices([y], 600)
    assert len(idx) <= 602 and 54_321 in idx and idx[0] == 0 and idx[-1] == 100_000
    p = plot_from_arrays("t", "x", "s", np.arange(len(y)), [("y", "V", y)])
    assert max(p.series[0].y) == 7.0 and len(p.x) == len(p.series[0].y)


def test_tick_labels_use_si_prefixes():
    assert [svgplot.si(v) for v in (1e4, 2.2e6, 5e-4, 1.0, 0.0)] == ["10k", "2.2M", "500µ", "1", "0"]
    major, minor = svgplot.log_ticks(10.0, 1e7)
    assert major == [10.0 ** k for k in range(1, 8)] and 20.0 in minor
    assert svgplot.nice_step(37.0, "deg") == 45.0 and svgplot.nice_step(0.37) == 0.5
    assert si_text(12_300.0, "Hz") == "12.3 kHz"


def test_measured_loop_gain_result_carries_a_bode_plot():
    f = np.logspace(2, 6, 25)
    t = 5e3 / (1j * f) / (1 + 1j * f / 30e3) / (1 + 1j * f / 60e3)
    m = measure.loop_margins(f, t)
    r = measure.margins_result(m, f_hz=f, t_loop=t)
    assert plot_errors(r.plots[0]) == []
    assert next(k for k in r.plots[0].markers if k.label.startswith("fc")).x == m.crossover_hz
    points = [setups.LoopGainPoint(float(a), complex(b), 1.0, 1.0, None) for a, b in zip(f, t)]
    res = setups.LoopGainResult(points, m, SanityReport())
    assert res.results[0].plots and res.results[0].plots[0].title == "Measured loop gain"
    assert setups.LoopGainResult([], m, SanityReport()).results[0].plots == ()


def fake_run(tmp_path: Path, t: np.ndarray, **cols: np.ndarray) -> RunResult:
    raw_path = tmp_path / "fake.raw"
    raw_path.write_bytes(b"synthetic")
    variables = [Variable(0, "time", "time")] + [Variable(i + 1, f"V({n})", "voltage") for i, n in enumerate(cols)]
    raw = RawFile(header={"plotname": "Transient Analysis"}, variables=variables,
                  data=np.vstack([t, *cols.values()]), step_bounds=[(0, len(t))])
    return RunResult("ltspice", (), tmp_path / "fake.net", raw_path, None, 0, 0.0, False, parse_log(""), raw)


def test_load_step_and_startup_results_carry_waveform_plots(tmp_path, monkeypatch):
    t = np.linspace(0, 1e-3, 100_001)
    x = np.clip(t - 1e-4, 0, None)
    out = 3.3 - 0.05 * np.exp(-0.2 * 2 * np.pi * 20e3 * x) * np.sin(2 * np.pi * 20e3 * x)
    ls = setups.LoadStepSetup(body="V1 out 0 3.3", out_node="out", i_from_a=0.0, i_to_a=1.0, t_step_s=1e-4,
                              t_stop_s=1e-3)
    monkeypatch.setattr(setups, "run", lambda *a, **k: fake_run(tmp_path, t, out=out))
    res = setups.run_load_step(ls, tmp_path)
    dev = next(r for r in res.results if r.name == "peak deviation after step")
    p = dev.plots[0]
    assert plot_errors(p) == [] and len(p.x) <= 602
    assert next(m for m in p.markers if m.label == "step").x == 1e-4
    peak = next(m for m in p.markers if m.label.startswith("peak"))
    assert peak.x == pytest.approx(res.steps[0].t_peak_s) and min(p.series[0].y) == pytest.approx(peak.y, abs=1e-4)
    tt = np.linspace(0, 2e-3, 20_001)
    vout = 3.3 * np.clip(tt / 2e-4, 0, 1) + 0.4 * np.exp(-(((tt - 3e-4) / 1e-4) ** 2))
    su = setups.StartupSetup(body="Vin vin 0 5\nRx vin out 1\nRl out 0 1", in_node="vin", out_node="out", vin_v=5.0,
                             ramp_s=1e-4, t_stop_s=2e-3, v_target_v=3.3, input_source="Vin")
    monkeypatch.setattr(setups, "run", lambda *a, **k: fake_run(tmp_path, tt, out=vout, vin=np.full_like(tt, 5.0)))
    sres = setups.run_startup(su, tmp_path)
    sp = sres.results[0].plots[0]
    assert plot_errors(sp) == [] and [s.label for s in sp.series] == ["output", "input"]
    assert {m.label for m in sp.markers} >= {"target 3.3 V", "overshoot 12 %"}


def test_impedance_result_carries_impedance_and_transfer_plots():
    f = np.logspace(3, 8, 300)
    z = 0.01 + 2j * np.pi * f * 1e-9 + 1 / (2j * np.pi * f * 10e-6)
    s = measure.impedance_summary(f, z, 0.05)
    res = setups.ImpedanceResult(None, f, z, s, 1 / (1 + 1j * f / 1e5))
    plots = res.results[0].plots
    assert [p.title for p in plots] == ["Rail impedance", "Transfer, source to rail"]
    assert all(plot_errors(p) == [] for p in plots)
    assert next(m for m in plots[0].markers if m.label.startswith("target")).y == 0.05
    assert plots[0].y_log and plots[0].x_log
    for p in plots:
        ET.fromstring(svgplot.plot_svg(p))
