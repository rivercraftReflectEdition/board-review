"""Clock termination values, loaded input levels and first-order AC coupling."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np

from boardreview.calc.base import Key, Marker, Quantity, Result, Verdict, fmt, plot_from_arrays

PECL = "Renesas AN-828 Rev A, 2014-04-30, pp.3 to 9, 13"
LEVELS = "TI SLLA120, 2002-12, pp.3 to 16; SCAA062, 2003-03, Table 3 p.3"
HCSL = "Renesas AN-879 Rev B, 2015-04-02, pp.1 to 4; AN-808 Rev A, 2013-12-04, pp.1 to 2"
COUPLING = "Skyworks AN1051 Rev 0.3, 2021-07-26, sec.2.2 p.7; TI SCAA112, 2010-11, pp.2, 6 to 7"


def _finite(**values):
    for name, value in values.items():
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")


def _positive(**values):
    _finite(**values)
    if any(value <= 0 for value in values.values()):
        raise ValueError("positive values required: " + ", ".join(values))


def _nonnegative(**values):
    _finite(**values)
    if any(value < 0 for value in values.values()):
        raise ValueError("nonnegative values required: " + ", ".join(values))


def termination(
    standard: str,
    vcc_v: float,
    z0_ohm: float,
    r_out_ohm: float | None = None,
    *,
    topology: str = "dc",
    vtt_v: float | None = None,
    output_cm_v: float | None = None,
    pull_down_current_a: float | None = None,
    vendor_values_ohm: Mapping[str, float] | None = None,
    fitted_ohm: Mapping[str, float] | None = None,
    error_limit_frac: float | None = None,
    context: str = "nominal",
) -> Result:
    """Resistor targets per leg (LVDS across the pair), with an explicit fitted-value error limit."""
    _positive(vcc_v=vcc_v, z0_ohm=z0_ohm)
    if r_out_ohm is not None:
        _nonnegative(r_out_ohm=r_out_ohm)
    if error_limit_frac is not None:
        _nonnegative(error_limit_frac=error_limit_frac)
    standard = standard.upper()
    if standard not in {"LVPECL", "LVDS", "HCSL", "LP-HCSL", "CML", "LVCMOS"}:
        raise ValueError("unsupported clock output standard")
    if topology not in {"dc", "pull_down"} or (topology == "pull_down" and standard != "LVPECL"):
        raise ValueError("pull_down topology is for conventional LVPECL only")
    labels = {"r_up": "Pull-up resistor", "r_down": "Pull-down resistor", "r_diff": "Differential resistor",
              "r_shunt": "Shunt resistor", "r_series": "Source series resistor"}
    inputs = {"vcc": Quantity(vcc_v, "V", label="Driver supply"),
              "z0": Quantity(z0_ohm, "ohm", label="Single-ended line impedance")}
    assumptions = ["targets describe the chosen topology, not proof that it suits a particular part",
                   "fitted values must include internal resistors when they provide the stated termination"]
    forbidden = set()
    if vendor_values_ohm is not None:
        expected = dict(vendor_values_ohm)
        if not expected or expected.keys() - labels.keys():
            raise ValueError("vendor values must use r_up, r_down, r_diff, r_shunt or r_series")
        _nonnegative(**expected)
        formula = "target resistances supplied from the part datasheet"
        assumptions.append("vendor target values override the generic output-standard network")
        for name, value in expected.items():
            inputs[f"vendor_{name}"] = Quantity(value, "ohm", label=f"Vendor {labels[name].lower()}")
    elif standard == "LVPECL" and topology == "pull_down":
        if output_cm_v is None or pull_down_current_a is None:
            raise ValueError("LVPECL pull-down needs output_cm_v and pull_down_current_a from the driver datasheet")
        _positive(output_cm_v=output_cm_v, pull_down_current_a=pull_down_current_a)
        expected = {"r_down": output_cm_v / pull_down_current_a}
        formula = "Rdown = Vcm / Iaverage (each leg to ground, ahead of the coupling capacitor)"
        inputs.update(output_cm=Quantity(output_cm_v, "V", label="Output common mode"),
                      pull_down_current=Quantity(pull_down_current_a, "A", label="Average pull-down current per leg"))
        assumptions.append("conventional emitter-follower LVPECL only; check vendor exceptions such as Si534x")
    elif standard == "LVPECL":
        vt = vcc_v - 2.0 if vtt_v is None else vtt_v
        _finite(vtt_v=vt)
        if not 0 < vt < vcc_v:
            raise ValueError("LVPECL termination voltage must lie between ground and VCC")
        expected = {"r_up": z0_ohm * vcc_v / vt, "r_down": z0_ohm * vcc_v / (vcc_v - vt)}
        formula = "Rup = Z0 VCC / Vtt; Rdown = Z0 VCC / (VCC - Vtt); generic LVPECL Vtt = VCC - 2 V"
        inputs["vtt"] = Quantity(vt, "V", label="Termination bias voltage")
    elif standard in {"LVCMOS", "LP-HCSL"}:
        if r_out_ohm is None:
            raise ValueError("source series termination needs r_out_ohm from the driver datasheet")
        if r_out_ohm > z0_ohm:
            raise ValueError("driver resistance exceeds line impedance; a passive series match is impossible")
        expected = {"r_series": z0_ohm - r_out_ohm}
        forbidden = {"r_shunt", "r_diff"}
        formula = "Rs = Z0 - Rout; no external end termination for the generic push-pull topology"
        inputs["r_out"] = Quantity(r_out_ohm, "ohm", label="Driver output resistance")
        assumptions.append("one source drives one line; integrated source resistance belongs in Rout")
    elif standard == "LVDS":
        expected, formula = {"r_diff": 2 * z0_ohm}, "Rdiff = 2 Z0 across the receiver pair"
    else:
        expected, formula = {"r_shunt": z0_ohm}, "Rshunt = Z0 on each leg"
        assumptions.append("shunt to ground for traditional HCSL; to VCC for conventional CML")
    outputs = {name: Quantity(value, "ohm", label=labels[name]) for name, value in expected.items()}
    target_text = ", ".join(f"{labels[name].lower()} {fmt(value, 'ohm')}" for name, value in expected.items())
    key = [Key(name, "datasheet topology required") for name in expected][:2]
    text = f"The {standard} {topology.replace('_', ' ')} network calls for {target_text}."
    verdict, reason = Verdict.INFO, "target values only"
    fitted = dict(fitted_ohm or {})
    if fitted.keys() - expected.keys() - forbidden:
        raise ValueError("fitted resistor names do not belong to the chosen network")
    _nonnegative(**fitted)
    if fitted:
        errors = [abs(value - expected[name]) / expected[name] if expected[name] else
                  (0.0 if value == 0 else math.inf) for name, value in fitted.items() if name in expected]
        error = max(errors, default=0.0)
        for name, value in fitted.items():
            inputs[f"fitted_{name}"] = Quantity(value, "ohm", label=f"Fitted {labels[name].lower()}")
        outputs["error_pct"] = Quantity(100 * error, "%", label="Largest fitted resistor error")
        key.append(Key("error_pct", f"at most {fmt(100 * error_limit_frac, '%')}" if error_limit_frac is not None
                       else "limit needed"))
        text += f" The largest fitted resistor error is {fmt(100 * error, '%')}."
        if error_limit_frac is None:
            reason = "give error_limit_frac from the part datasheet or a stated engineering judgment"
        else:
            inputs["error_limit"] = Quantity(100 * error_limit_frac, "%", label="Allowed resistor error")
            if forbidden & fitted.keys() or error > error_limit_frac:
                verdict, reason = Verdict.FAIL, "fitted network exceeds the error limit or adds an end termination"
            elif expected.keys() - fitted.keys():
                verdict, reason = Verdict.UNKNOWN, "not every required resistor was supplied"
            else:
                verdict, reason = Verdict.PASS, "all fitted resistors are within the supplied error limit"
            text += f" Allowed error is {fmt(100 * error_limit_frac, '%')}; {reason}."
        if forbidden & fitted.keys():
            text += " The fitted end termination loads this source-terminated output."
    if not fitted or error_limit_frac is None:
        text += " Supply fitted values and an error limit from the datasheet or a stated engineering judgment to judge them."
    return Result("clock termination", formula, inputs, outputs, verdict, reason,
                  refs=(PECL, LEVELS, HCSL, "Renesas AN-953, 2017-03-06, pp.1, 5, 17"),
                  assumptions=tuple(assumptions), summary=text, key=tuple(key)).in_context(context)


def compat(
    voh_v: float | Sequence[float],
    vol_v: float | Sequence[float],
    *,
    rx_cm_min_v: float | None = None,
    rx_cm_max_v: float | None = None,
    rx_vid_min_v: float | None = None,
    rx_vid_max_v: float | None = None,
    rx_abs_min_v: float | None = None,
    rx_abs_max_v: float | None = None,
    r_source_ohm: float = 0.0,
    r_bias_ohm: float | None = None,
    bias_v: float = 0.0,
    ac_coupled: bool = False,
    context: str = "nominal",
) -> Result:
    """Check paired high/low corners through a per-leg Thevenin bias network."""
    _nonnegative(r_source_ohm=r_source_ohm)
    _finite(bias_v=bias_v)
    if r_bias_ohm is not None:
        _positive(r_bias_ohm=r_bias_ohm)
    if ac_coupled and r_bias_ohm is None:
        raise ValueError("AC coupling needs the receiver bias resistance, including any internal bias")
    hi, lo = np.broadcast_arrays(np.asarray(voh_v, dtype=float), np.asarray(vol_v, dtype=float))
    if hi.size == 0 or hi.ndim > 1 or not np.all(np.isfinite(hi)) or not np.all(np.isfinite(lo)) or np.any(hi < lo):
        raise ValueError("give finite paired high/low corners with VOH >= VOL")
    hi, lo = hi.reshape(-1), lo.reshape(-1)
    gain = 1.0 if r_bias_ohm is None else r_bias_ohm / (r_source_ohm + r_bias_ohm)
    cm = np.full_like(hi, bias_v) if ac_coupled else gain * (hi / 2 + lo / 2) + (1 - gain) * bias_v
    swing = gain * (hi - lo)
    high, low = cm + swing / 2, cm - swing / 2
    inputs = {"r_source": Quantity(r_source_ohm, "ohm", label="Source and series resistance per leg"),
              "bias": Quantity(bias_v, "V", label="Receiver bias Thevenin voltage")}
    if r_bias_ohm is not None:
        inputs["r_bias"] = Quantity(r_bias_ohm, "ohm", label="Receiver bias Thevenin resistance per leg")
    for i, (h, l) in enumerate(zip(hi, lo), 1):
        inputs[f"voh_{i}"] = Quantity(h, "V", label=f"Driver high level, corner {i}")
        inputs[f"vol_{i}"] = Quantity(l, "V", label=f"Driver low level, corner {i}")
    limits = {"cm_min": rx_cm_min_v, "cm_max": rx_cm_max_v, "vid_min": rx_vid_min_v,
              "vid_max": rx_vid_max_v, "abs_min": rx_abs_min_v, "abs_max": rx_abs_max_v}
    for lower, upper in ((rx_cm_min_v, rx_cm_max_v), (rx_vid_min_v, rx_vid_max_v), (rx_abs_min_v, rx_abs_max_v)):
        if lower is not None and upper is not None and lower > upper:
            raise ValueError("receiver minimum exceeds maximum")
    margins = {}
    values = {"cm_min": min(cm), "cm_max": max(cm), "vid_min": min(swing), "vid_max": max(swing),
              "abs_min": min(low), "abs_max": max(high)}
    labels = {"cm_min": "Lowest common mode", "cm_max": "Highest common mode",
              "vid_min": "Smallest differential magnitude", "vid_max": "Largest differential magnitude",
              "abs_min": "Lowest pin voltage", "abs_max": "Highest pin voltage"}
    outputs = {name: Quantity(value, "V", label=labels[name]) for name, value in values.items()}
    for name, limit in limits.items():
        if limit is not None:
            _finite(**{name: limit})
            if name.startswith("vid") and limit < 0:
                raise ValueError("receiver differential magnitudes must be nonnegative")
            inputs[f"rx_{name}"] = Quantity(limit, "V", label=f"Receiver {labels[name].lower()} limit")
            margin = values[name] - limit if name.endswith("min") else limit - values[name]
            margins[name] = margin
            outputs[f"margin_{name}"] = Quantity(margin, "V", label=f"Margin for {labels[name].lower()}")
    text = (f"At the receiver, common mode is {fmt(min(cm), 'V')} to {fmt(max(cm), 'V')} and the differential "
            f"magnitude is {fmt(min(swing), 'V')} to {fmt(max(swing), 'V')}. ")
    key = [Key("cm_min"), Key("vid_max")]
    if margins:
        worst = min(margins, key=margins.get)
        key = [Key(f"margin_{worst}", "at least 0 V"), Key("vid_max")]
        text += (f"The smallest checked margin is {fmt(margins[worst], 'V')} for {labels[worst].lower()}, "
                 f"against {fmt(limits[worst], 'V')}. ")
    missing = [labels[name].lower() for name, value in limits.items() if value is None]
    if margins and min(margins.values()) < 0:
        verdict, reason = Verdict.FAIL, "a supplied receiver limit is exceeded; clock reception is outside specification"
    elif missing:
        verdict, reason = Verdict.UNKNOWN, "receiver datasheet limits still needed: " + ", ".join(missing)
    else:
        verdict, reason = Verdict.PASS, "all supplied corners lie inside the receiver limits"
    text += reason[0].upper() + reason[1:] + "."
    return Result("clock input compatibility",
                  "g = Rbias/(Rsource + Rbias); DC: Vrx = g Vdriver + (1-g) Vbias; "
                  "AC: Vcm = Vbias; VID = g (VOH - VOL); margin = distance inside each receiver limit",
                  inputs, outputs, verdict, reason, refs=(LEVELS, PECL),
                  assumptions=("complementary differential legs with paired VOH and VOL at each supplied corner",
                               "VID is differential magnitude, equal to one leg's peak-to-peak swing, not differential peak-to-peak",
                               "Rbias includes all per-leg loading; reduce a divider to its Thevenin voltage and resistance",
                               "AC case assumes settled bias and negligible capacitor reactance; check AC coupling separately",
                               "resistive model excludes ringing and clamps; coupling permission is a separate datasheet check"),
                  summary=text, key=tuple(key)).in_context(context)


def ac_coupling(
    c_f: float,
    r_bias_ohm: float,
    f_clk_hz: float,
    duty: float,
    v_pp_v: float,
    slew_v_per_s: float,
    *,
    r_source_ohm: float = 0.0,
    bias_offset_v: float = 0.0,
    run_bits: int = 0,
    bit_rate_hz: float | None = None,
    xc_limit_ohm: float | None = None,
    fc_limit_hz: float | None = None,
    droop_limit_frac: float | None = None,
    dt_limit_s: float | None = None,
    context: str = "nominal",
) -> Result:
    """First-order high-pass corner, reactance, edge shift and constant-level run droop."""
    _positive(c_f=c_f, r_bias_ohm=r_bias_ohm, f_clk_hz=f_clk_hz, v_pp_v=v_pp_v, slew_v_per_s=slew_v_per_s)
    _nonnegative(r_source_ohm=r_source_ohm)
    _finite(duty=duty, bias_offset_v=bias_offset_v)
    if not 0 < duty < 1 or isinstance(run_bits, bool) or not isinstance(run_bits, int) or run_bits < 0:
        raise ValueError("duty must be between zero and one; run_bits must be a nonnegative integer")
    if run_bits and bit_rate_hz is None:
        raise ValueError("give bit_rate_hz for run-length droop")
    if bit_rate_hz is not None:
        _positive(bit_rate_hz=bit_rate_hz)
    tau = (r_source_ohm + r_bias_ohm) * c_f
    fc, xc = 1 / (2 * math.pi * tau), 1 / (2 * math.pi * f_clk_hz * c_f)
    run_s = run_bits / bit_rate_hz if run_bits else 0.0
    droop = -math.expm1(-run_s / tau)
    gain = r_bias_ohm / (r_source_ohm + r_bias_ohm)
    dv = gain * (duty - 0.5) * v_pp_v + bias_offset_v
    dt = abs(dv) / slew_v_per_s
    inputs = {"c": Quantity(c_f, "F", label="Coupling capacitance per leg"),
              "r_bias": Quantity(r_bias_ohm, "ohm", label="Bias and load Thevenin resistance per leg"),
              "r_source": Quantity(r_source_ohm, "ohm", label="Source resistance per leg"),
              "f_clk": Quantity(f_clk_hz, "Hz", label="Clock frequency"),
              "duty": Quantity(duty, "", label="Input high-time fraction"),
              "v_pp": Quantity(v_pp_v, "V", label="Single-ended swing before the capacitor"),
              "slew": Quantity(slew_v_per_s, "V/s", label="Slew at the receiver crossing"),
              "bias_offset": Quantity(bias_offset_v, "V", label="Additional receiver baseline offset"),
              "run_bits": Quantity(run_bits, "count", label="Consecutive equal bits")}
    if bit_rate_hz is not None:
        inputs["bit_rate"] = Quantity(bit_rate_hz, "Hz", label="Bit rate")
    outputs = {"fc_hz": Quantity(fc, "Hz", label="High-pass corner"),
               "xc_ohm": Quantity(xc, "ohm", label="Capacitor reactance at the clock"),
               "tau_s": Quantity(tau, "s", label="Bias settling time constant"),
               "dv_v": Quantity(dv, "V", label="Baseline offset from duty and bias"),
               "dt_s": Quantity(dt, "s", label="Magnitude of crossing shift per edge"),
               "duty_shift_frac": Quantity(2 * dt * f_clk_hz, "", label="Magnitude of high-time fraction shift"),
               "run_s": Quantity(run_s, "s", label="Constant-level run duration"),
               "droop": Quantity(droop, "", label="Fraction lost during the run")}
    checks = (("xc_ohm", xc_limit_ohm), ("fc_hz", fc_limit_hz), ("droop", droop_limit_frac), ("dt_s", dt_limit_s))
    supplied, failed, missing = [], [], []
    for name, limit in checks:
        q = outputs[name]
        if limit is None:
            missing.append(q.label.lower())
        else:
            _nonnegative(**{name: limit})
            if name == "droop" and limit > 1:
                raise ValueError("droop limit must be a fraction between zero and one")
            inputs[f"limit_{name}"] = Quantity(limit, q.unit, label=f"Limit for {q.label.lower()}")
            supplied.append(f"{q.label.lower()} at most {fmt(limit, q.unit)}")
            if q.value > limit:
                failed.append(q.label.lower())
    if failed:
        verdict, reason = Verdict.FAIL, "supplied limits exceeded: " + ", ".join(failed)
    elif not supplied:
        verdict, reason = Verdict.INFO, "no pass limits supplied"
    elif missing:
        verdict, reason = Verdict.UNKNOWN, "some pass limits are missing"
    else:
        verdict, reason = Verdict.PASS, "all four supplied limits are satisfied by this first-order model"
    text = (f"The coupling corner is {fmt(fc, 'Hz')} and reactance at {fmt(f_clk_hz, 'Hz')} is {fmt(xc, 'ohm')}. "
            f"The baseline offset is {fmt(dv, 'V')}, moving each crossing by {fmt(dt, 's')}; a {fmt(run_s, 's')} "
            f"run loses {fmt(droop)} of its initial level. ")
    if supplied:
        text += "Requested limits are " + "; ".join(supplied) + ". "
    text += reason[0].upper() + reason[1:] + "."
    if missing:
        text += (" Supply limits for " + ", ".join(missing)
                 + " from the receiver timing requirement, part datasheet or a stated engineering judgment.")
    f = np.unique(np.append(np.geomspace(min(fc, f_clk_hz) / 100, max(fc, f_clk_hz) * 100, 200), [fc, f_clk_hz]))
    times = np.unique(np.append(np.linspace(0, run_s if run_s else 5 * tau, 150), run_s))
    plots = (plot_from_arrays("Coupling high-pass response", "Frequency", "Hz", f,
                             [("Voltage transfer", "dB", 20 * np.log10(gain * f / np.hypot(f, fc)))],
                             x_log=True, markers=(Marker("Corner", x=fc), Marker("Clock", x=f_clk_hz)),
                             caption=f"The corner is {fmt(fc, 'Hz')}; the clock is at {fmt(f_clk_hz, 'Hz')}."),
             plot_from_arrays("Constant-level run decay", "Time since edge", "s", times,
                              [("Level remaining", "", np.exp(-times / tau))],
                              markers=(Marker("Run duration", x=run_s),),
                              caption=f"After {fmt(run_s, 's')}, {fmt(droop)} of the initial level is lost."))
    key = tuple(Key(name, f"at most {fmt(limit, outputs[name].unit)}" if limit is not None else "limit needed")
                for name, limit in checks[:3])
    return Result("clock AC coupling",
                  "tau = (Rsource + Rbias) C; fc = 1/(2 pi tau); Xc = 1/(2 pi fclk C); "
                  "g = Rbias/(Rsource + Rbias); dV = g (D - 0.5) Vpp + Voffset; "
                  "dt = abs(dV)/slew; duty shift = 2 dt fclk; "
                  "droop = 1 - exp(-run_bits/(bit_rate tau))",
                  inputs, outputs, verdict, reason, refs=(COUPLING, "DERIVED: RC step decay and local linear crossing model"),
                  assumptions=("per-leg equivalent circuit; reduce the full differential bias network before use",
                               "ideal capacitor and resistive source and load; excludes ESR, ESL and capacitor resonance",
                               "duty offset is a first-order estimate for a repetitive two-level waveform with tau much longer than a period",
                               "duty shift uses equal rising and falling crossing slopes; a missing crossing is outside this model",
                               "droop is relative to the initial step; start-stop recovery and false edges need a transient check"),
                  plots=plots, summary=text, key=key).in_context(context)
