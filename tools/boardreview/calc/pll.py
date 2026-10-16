"""Passive charge-pump filters: C1 || (R2 + C2), with R3 to a shunt C3 at the VCO."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from itertools import product

import numpy as np
from scipy.optimize import brentq

from boardreview.calc.base import Key, Marker, Quantity, Result, Verdict, fmt, plot_from_arrays

TWO_PI = 2 * math.pi
BANERJEE = "TI SNAA106C, PLL Performance, Simulation, and Design, 5th ed., May 2017, pp.339 to 347"


def _positive(**values):
    for name, value in values.items():
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")


def _coefficients(parts):
    c1, c2, r2 = parts["c1"], parts["c2"], parts["r2"]
    c3, r3 = parts.get("c3", 0.0), parts.get("r3", 0.0)
    return (c1 + c2 + c3, r2 * c2 * (c1 + c3) + r3 * c3 * (c1 + c2),
            r2 * r3 * c1 * c2 * c3, r2 * c2)


def _gain(f_hz, k, coefficients):
    a0, a1, a2, t2 = coefficients
    s = 1j * TWO_PI * np.asarray(f_hz)
    return k * (1 + s * t2) / (s * s * (a0 + s * a1 + s * s * a2))


def _phase(f_hz, coefficients):
    a0, a1, a2, t2 = coefficients
    w = TWO_PI * np.asarray(f_hz)
    return -180 + np.degrees(np.arctan(w * t2) - np.arctan2(w * a1, a0 - w * w * a2))


def _crossover(k, coefficients):
    estimate = math.sqrt(k / coefficients[0]) / TWO_PI
    lo, hi = math.log10(estimate) - 1, math.log10(estimate) + 1

    def db(log_f):
        return 20 * math.log10(abs(_gain(10**log_f, k, coefficients)))

    for _ in range(80):
        if db(lo) >= 0 and db(hi) <= 0:
            return 10**brentq(db, lo, hi, xtol=1e-12)
        lo, hi = lo - 1, hi + 1
    raise ValueError("could not bracket the crossover; check the parameter scales")


def loop_filter_design(
    icp_a: float,
    kvco_hz_per_v: float,
    n: float,
    fc_hz: float,
    pm_deg: float,
    order: int = 2,
    gamma: float = 1.0,
    t31: float = 0.4,
    context: str = "ideal",
) -> Result:
    """Synthesize a second- or third-order passive filter at a requested crossover and phase margin."""
    _positive(icp_a=icp_a, kvco_hz_per_v=kvco_hz_per_v, n=n, fc_hz=fc_hz, gamma=gamma)
    if order not in (2, 3):
        raise ValueError("order must be 2 or 3")
    if not math.isfinite(pm_deg) or not 0 < pm_deg < 90:
        raise ValueError("pm_deg must be between 0 and 90 degrees")
    if order == 3 and (not math.isfinite(t31) or not 0 < t31 <= 1):
        raise ValueError("t31 must be in (0, 1]")
    w, phi = TWO_PI * fc_hz, math.radians(pm_deg)
    ratio = t31 if order == 3 else 0.0

    def phase_error(x):
        return math.atan(gamma / (x * (1 + ratio))) - math.atan(x) - math.atan(ratio * x) - phi

    x = brentq(phase_error, 1e-12, max(1.0, gamma / math.tan(phi)), xtol=1e-14)
    t1, t3 = x / w, ratio * x / w
    t2 = gamma / (w * w * (t1 + t3))
    a0 = icp_a * kvco_hz_per_v / (n * w * w) * math.sqrt(
        (1 + (w * t2)**2) / ((1 + (w * t1)**2) * (1 + (w * t3)**2)))
    if order == 2:
        c1 = a0 * t1 / t2
        c3, r3 = 0.0, 0.0
    else:
        a1, a2 = a0 * (t1 + t3), a0 * t1 * t3
        c1 = a2 / t2**2 * (1 + math.sqrt(1 + t2 * (t2 * a0 - a1) / a2))
        c3 = (-t2**2 * c1**2 + t2 * a1 * c1 - a2 * a0) / (t2**2 * c1 - a2)
        r3 = a2 / (t2 * c1 * c3)
    c2 = a0 - c1 - c3
    r2 = t2 / c2
    parts = dict(c1=c1, c2=c2, r2=r2)
    if order == 3:
        parts.update(c3=c3, r3=r3)
    _positive(**parts)
    outputs = {f"{p}_{'f' if p.startswith('c') else 'ohm'}":
               Quantity(v, "F" if p.startswith("c") else "ohm", label=p.upper()) for p, v in parts.items()}
    outputs.update({"t1_s": Quantity(t1, "s", label="First pole time constant"),
                    "t2_s": Quantity(t2, "s", label="Zero time constant")})
    if order == 3:
        outputs["t3_s"] = Quantity(t3, "s", label="Second pole time constant")
    inputs = {"icp_a": Quantity(icp_a, "A", label="Charge-pump current"),
              "kvco_hz_per_v": Quantity(kvco_hz_per_v, "Hz/V", label="VCO tuning gain"),
              "n": Quantity(n, "", label="Feedback division ratio"),
              "fc_hz": Quantity(fc_hz, "Hz", label="Requested crossover"),
              "pm_deg": Quantity(pm_deg, "deg", label="Requested phase margin"),
              "order": Quantity(order, "", label="Filter order"),
              "gamma": Quantity(gamma, "", label="Loop shaping factor")}
    if order == 3:
        inputs["t31"] = Quantity(t31, "", "T3/T1", "Pole time constant ratio")
    text = (f"At {fmt(fc_hz, 'Hz')} and {fmt(pm_deg, 'deg')}, the filter needs C1 {fmt(c1, 'F')}, "
            f"C2 {fmt(c2, 'F')} and R2 {fmt(r2, 'ohm')}.")
    if order == 3:
        text += f" Add R3 {fmt(r3, 'ohm')} and C3 {fmt(c3, 'F')} at the VCO."
    text += " Check rounded parts, VCO gain range and capacitor bias loss before judging margin."
    f = np.logspace(math.log10(fc_hz) - 3, math.log10(fc_hz) + 3, 1001)
    coefficients = _coefficients(parts)
    plot = plot_from_arrays(
        "Synthesized PLL open-loop Bode", "Frequency", "Hz", f,
        [("Gain", "dB", 20 * np.log10(abs(_gain(f, icp_a * kvco_hz_per_v / n, coefficients)))),
         ("Phase", "deg", _phase(f, coefficients))], x_log=True,
        markers=[Marker("Unity gain", y=0, unit="dB"), Marker("Phase boundary", y=-180, unit="deg"),
                 Marker("Requested crossover", x=fc_hz, y=0, unit="dB"),
                 Marker(f"Phase margin {fmt(pm_deg, 'deg')}", x=fc_hz, y=pm_deg - 180, unit="deg")],
        caption=f"Ideal unrounded parts target {fmt(pm_deg, 'deg')} of phase margin at {fmt(fc_hz, 'Hz')}.")
    return Result(
        name="PLL passive loop filter design",
        formula=("wc = 2*pi*fc; phi = atan(wc*T2)-atan(wc*T1)-atan(wc*T3); "
                 "T3 = T31*T1; T2 = gamma/(wc^2*(T1+T3)); "
                 "A0 = Icp*Kvco/(N*wc^2)*sqrt((1+(wc*T2)^2)/((1+(wc*T1)^2)*(1+(wc*T3)^2))); "
                 "2nd: C1=A0*T1/T2; C2=A0-C1; R2=T2/C2; "
                 "3rd: A1=A0*(T1+T3); A2=A0*T1*T3; "
                 "C1=A2/T2^2*(1+sqrt(1+T2*(T2*A0-A1)/A2)); "
                 "C3=(-T2^2*C1^2+T2*A1*C1-A2*A0)/(T2^2*C1-A2); "
                 "C2=A0-C1-C3; R2=T2/C2; R3=A2/(T2*C1*C3)"),
        inputs=inputs, outputs=outputs, verdict=Verdict.INFO,
        reason="synthesis targets are not a tolerance or stability check", refs=(BANERJEE,),
        assumptions=("Icp is pump current in A; Icp/(2*pi) A/rad and 2*pi*Kvco rad/s/V cancel",
                     "C1 and series R2-C2 shunt the pump node; R3 connects that node to VCO shunt C3",
                     "second-order C1 uses A0*T1/T2; the reversed ratio in book eq.38.19 is a typo"),
        summary=text, key=(Key("c1_f"), Key("c2_f"), Key("r2_ohm")), plots=(plot,),
    ).in_context(context)


def _part_ranges(parts, component_tolerance_frac, capacitor_bias_factor, inputs):
    tolerances = component_tolerance_frac
    biases = capacitor_bias_factor
    for supplied, allowed, name in ((tolerances, parts, "component tolerance"),
                                    (biases, {p for p in parts if p.startswith("c")}, "capacitor bias")):
        if isinstance(supplied, Mapping) and set(supplied) - set(allowed):
            raise ValueError(f"unknown {name} keys: {sorted(set(supplied) - set(allowed))}")
    ranges = []
    for part, value in parts.items():
        tol = tolerances.get(part, 0.0) if isinstance(tolerances, Mapping) else tolerances
        if not math.isfinite(tol) or not 0 <= tol < 1:
            raise ValueError("component tolerances must be fractions in [0, 1)")
        inputs[f"{part}_tolerance"] = Quantity(tol, "", label=f"{part.upper()} tolerance fraction")
        bias = biases.get(part, 1.0) if isinstance(biases, Mapping) else biases
        bounds = np.atleast_1d(bias).astype(float) if part.startswith("c") else np.array([1.0])
        if bounds.size not in (1, 2) or bounds.ndim != 1 or not np.all(np.isfinite(bounds)) or \
                np.any(bounds <= 0) or np.any(bounds > 1) or bounds[0] > bounds[-1]:
            raise ValueError("capacitor bias factors must be in (0, 1], scalar or ordered lower/upper pair")
        if part.startswith("c"):
            inputs[f"{part}_bias_min"] = Quantity(bounds[0], "", label=f"{part.upper()} minimum retained fraction")
            inputs[f"{part}_bias_max"] = Quantity(bounds[-1], "", label=f"{part.upper()} maximum retained fraction")
        ranges.append(sorted({value * (1 - tol) * bounds[0], value * (1 + tol) * bounds[-1]}))
    return ranges


def loop_filter_check(
    icp_a: float,
    kvco_hz_per_v: float | Sequence[float],
    n: float,
    r2_ohm: float,
    c1_f: float,
    c2_f: float,
    *,
    r3_ohm: float | None = None,
    c3_f: float | None = None,
    f_offset_hz: float | None = None,
    f_pfd_hz: float | None = None,
    component_tolerance_frac: float | Mapping[str, float] = 0.0,
    capacitor_bias_factor: float | Mapping[str, float | Sequence[float]] = 1.0,
    pm_min_deg: float | None = None,
    pm_fail_deg: float | None = None,
    att_max_db: float | None = None,
    context: str = "nominal",
) -> Result:
    """Check specified VCO gains and part endpoints; bias factors are retained capacitance, keyed c1/c2/c3."""
    _positive(icp_a=icp_a, n=n, r2_ohm=r2_ohm, c1_f=c1_f, c2_f=c2_f)
    parts = dict(c1=c1_f, c2=c2_f, r2=r2_ohm)
    if (r3_ohm is None) != (c3_f is None):
        raise ValueError("provide both r3_ohm and c3_f for a third-order filter")
    if r3_ohm is not None:
        _positive(r3_ohm=r3_ohm, c3_f=c3_f)
        parts.update(c3=c3_f, r3=r3_ohm)
    gains = np.atleast_1d(kvco_hz_per_v).astype(float)
    if gains.ndim != 1 or not gains.size or not np.all(np.isfinite(gains)) or np.any(gains <= 0):
        raise ValueError("VCO gains must be a nonempty sequence of finite positive values")
    for name, value in (("pm_min_deg", pm_min_deg), ("pm_fail_deg", pm_fail_deg), ("att_max_db", att_max_db)):
        if value is not None and not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if pm_fail_deg is not None and (pm_min_deg is None or pm_fail_deg > pm_min_deg):
        raise ValueError("pm_fail_deg requires pm_min_deg and must not exceed it")
    for name, value in (("f_offset_hz", f_offset_hz), ("f_pfd_hz", f_pfd_hz)):
        if value is not None:
            _positive(**{name: value})
    if f_offset_hz is not None and f_pfd_hz is not None:
        raise ValueError("use f_offset_hz or f_pfd_hz to select the attenuation frequency")
    offset = f_offset_hz if f_offset_hz is not None else f_pfd_hz
    if att_max_db is not None and offset is None:
        raise ValueError("an attenuation limit requires an offset or PFD frequency")
    inputs = {"icp_a": Quantity(icp_a, "A", label="Charge-pump current"),
              "n": Quantity(n, "", label="Feedback division ratio")}
    for part, value in parts.items():
        inputs[part] = Quantity(value, "F" if part.startswith("c") else "ohm", label=f"Fitted {part.upper()}")
    for j, gain in enumerate(gains, 1):
        inputs[f"kvco_{j}"] = Quantity(gain, "Hz/V", label=f"VCO gain point {j}")
    for name, value, unit, label in (
        ("pm_min_deg", pm_min_deg, "deg", "Required phase margin"),
        ("pm_fail_deg", pm_fail_deg, "deg", "Phase margin failure boundary"),
        ("att_max_db", att_max_db, "dB", "Maximum open-loop gain at offset"),
        ("f_offset_hz" if f_pfd_hz is None else "f_pfd_hz", offset, "Hz", "Attenuation offset"),
    ):
        if value is not None:
            inputs[name] = Quantity(value, unit, label=label)
    ranges = _part_ranges(parts, component_tolerance_frac, capacitor_bias_factor, inputs)
    corners = []
    outputs = {}
    for gain, values in product(gains, product(*ranges)):
        corner = dict(zip(parts, values))
        coefficients = _coefficients(corner)
        k = icp_a * gain / n
        fc = _crossover(k, coefficients)
        pm = float(180 + _phase(fc, coefficients))
        att = float(20 * np.log10(abs(_gain(offset, k, coefficients)))) if offset is not None else None
        corners.append((fc, pm, att, k, coefficients))
        j = len(corners)
        note = f"VCO gain {fmt(gain, 'Hz/V')}; " + ", ".join(
            f"{p.upper()} {fmt(v, 'F' if p.startswith('c') else 'ohm')}" for p, v in corner.items())
        outputs[f"fc_{j}_hz"] = Quantity(fc, "Hz", note, f"Corner {j} crossover")
        outputs[f"pm_{j}_deg"] = Quantity(pm, "deg", note, f"Corner {j} phase margin")
        if att is not None:
            outputs[f"att_{j}_db"] = Quantity(att, "dB", note, f"Corner {j} open-loop gain at offset")
    worst = min(corners, key=lambda c: c[1])
    fc, pm = worst[:2]
    outputs.update({"fc_hz": Quantity(fc, "Hz", label="Crossover at lowest phase margin"),
                    "pm_deg": Quantity(pm, "deg", label="Lowest phase margin"),
                    "fc_min_hz": Quantity(min(c[0] for c in corners), "Hz", label="Minimum crossover"),
                    "fc_max_hz": Quantity(max(c[0] for c in corners), "Hz", label="Maximum crossover"),
                    "corners": Quantity(len(corners), "count", label="Evaluated endpoints")})
    verdict = Verdict.INFO
    clauses = []
    if pm_min_deg is not None:
        verdict = Verdict.PASS
        if pm < pm_min_deg - 1e-8:
            verdict = Verdict.MARGINAL if pm_fail_deg is not None and pm >= pm_fail_deg - 1e-8 else Verdict.FAIL
        clauses.append(f"We require at least {fmt(pm_min_deg, 'deg')} of phase margin"
                       + (f", with failure below {fmt(pm_fail_deg, 'deg')}" if pm_fail_deg is not None else "") + ".")
    else:
        clauses.append("Supply a phase margin limit from the board requirement or datasheet, or state an engineering judgment.")
    key = [Key("pm_deg", f"at least {fmt(pm_min_deg, 'deg')}" if pm_min_deg is not None else "limit needed"),
           Key("fc_hz")]
    text = f"The lowest phase margin is {fmt(pm, 'deg')} at {fmt(fc, 'Hz')} across {fmt(len(corners), 'count')} evaluated endpoints."
    if offset is not None:
        att_corner = max(corners, key=lambda c: c[2])
        att = att_corner[2]
        outputs["att_offset_db"] = Quantity(att, "dB", "20 log10 |G|", "Highest open-loop gain at offset")
        if f_pfd_hz is not None:
            outputs["att_pfd_db"] = outputs["att_offset_db"]
        closed = max(20 * math.log10(abs((g := _gain(offset, c[3], c[4])) / (1 + g))) for c in corners)
        outputs["reference_transfer_db"] = Quantity(closed, "dB", "20 log10 |G/(1+G)|; normalized to DC gain N",
                                                     "Highest normalized reference transfer at offset")
        text += f" The highest open-loop gain at {fmt(offset, 'Hz')} is {fmt(att, 'dB')}."
        key.append(Key("att_offset_db", f"at most {fmt(att_max_db, 'dB')}" if att_max_db is not None else "limit needed"))
        if att_max_db is not None:
            if att > att_max_db + 1e-8:
                verdict = Verdict.FAIL
            clauses.append(f"We require at most {fmt(att_max_db, 'dB')} at that offset.")
        else:
            clauses.append("Supply an offset gain limit from the spur budget or datasheet to judge that attenuation.")
    if verdict is Verdict.PASS and pm_min_deg is None:
        verdict = Verdict.INFO
    clauses.append({Verdict.PASS: "The specified limits are met at these endpoints.",
                    Verdict.FAIL: "A specified limit is violated; measure settling and reference spurs on the bench.",
                    Verdict.MARGINAL: "The margin lies between the supplied boundaries; check ringing on the bench.",
                    Verdict.INFO: "The numbers describe the modeled filter without a complete pass decision."}[verdict])
    f = np.logspace(math.log10(min(min(c[0] for c in corners), offset or math.inf) / 100),
                    math.log10(max(max(c[0] for c in corners) * 100, offset or 0) * 10), 1001)
    series, plotted = [], set()
    selected = [("Lowest margin", worst), ("Minimum crossover", min(corners, key=lambda c: c[0])),
                ("Maximum crossover", max(corners, key=lambda c: c[0]))]
    if offset is not None:
        selected.append(("Highest offset gain", att_corner))
    for label, corner in selected:
        if corner in plotted:
            continue
        plotted.add(corner)
        series.extend([(f"{label} gain", "dB", 20 * np.log10(abs(_gain(f, corner[3], corner[4])))),
                       (f"{label} phase", "deg", _phase(f, corner[4]))])
    markers = [Marker("Unity gain", y=0, unit="dB"), Marker("Phase boundary", y=-180, unit="deg"),
               Marker(f"Crossover {fmt(fc, 'Hz')}", x=fc, y=0, unit="dB"),
               Marker(f"Phase margin {fmt(pm, 'deg')}", x=fc, y=pm - 180, unit="deg")]
    if pm_min_deg is not None:
        markers.append(Marker("Required margin at crossover", y=pm_min_deg - 180, unit="deg"))
    if offset is not None:
        markers.append(Marker("Offset gain", x=offset, y=outputs["att_offset_db"].value, unit="dB"))
    if att_max_db is not None:
        markers.append(Marker("Offset gain limit", y=att_max_db, unit="dB"))
    return Result(
        name="PLL passive loop filter check",
        formula=("A0=C1+C2+C3; A1=R2*C2*(C1+C3)+R3*C3*(C1+C2); A2=R2*R3*C1*C2*C3; "
                 "Z(s)=(1+s*R2*C2)/(s*(A0+s*A1+s^2*A2)); G(s)=Icp*Kvco*Z(s)/(N*s); "
                 "|G(j*2*pi*fc)|=1; PM=180+arg(G(fc)); att=20*log10|G(offset)|; "
                 "Ceff=Cnom*bias_factor*(1 +/- tolerance); reference transfer=G/(1+G)"),
        inputs=inputs, outputs=outputs, verdict=verdict, reason=" ".join(clauses), refs=(BANERJEE,),
        assumptions=("Icp/(2*pi) A/rad and 2*pi*Kvco rad/s/V cancel; divider ratio is the VCO feedback N",
                     "C1 and series R2-C2 shunt the pump node; R3 feeds VCO shunt C3; no VCO input loading",
                     "continuous-time small-signal model; sampled PFD effects, delay, leakage and parasitics excluded",
                     "all supplied VCO gain points and part endpoint combinations are evaluated; not a proof over continuous ranges",
                     "bias factors are retained capacitance, multiplied by tolerance; dielectric absorption and microphonics excluded",
                     "offset attenuation is open-loop gain, not an absolute spur prediction; normalized reference transfer is also reported"),
        plots=(plot_from_arrays("PLL open-loop Bode", "Frequency", "Hz", f, series, x_log=True, markers=markers,
                                caption=f"Lowest phase margin {fmt(pm, 'deg')} at {fmt(fc, 'Hz')}; curves show selected evaluated endpoints."),),
        summary=" ".join([text, *clauses]), key=tuple(key),
    ).in_context(context)
