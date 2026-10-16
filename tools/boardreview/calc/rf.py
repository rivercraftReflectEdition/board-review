"""RF lineup, loading, attenuator, stability and shield calculations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import product
from typing import Sequence

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.signal import find_peaks

from boardreview.calc.base import Key, Marker, Quantity, Result, Verdict, fmt, plot_from_arrays
from boardreview.calc.lc_tank import Cap

TWO_PI = 2 * math.pi


@dataclass(frozen=True)
class Stage:
    """Matched small-signal stage, with input-referred IP3 and optional missing data."""

    gain_db: float
    nf_db: float | None = None
    iip3_dbm: float | None = None


def _q(value, unit, label, note=""):
    return Quantity(float(value), unit, note=note, label=label)


def _positive(**values):
    for name, value in values.items():
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")


def _nonnegative(**values):
    for name, value in values.items():
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and nonnegative")


def _gamma(gamma):
    g = abs(complex(gamma))
    if not math.isfinite(g) or g > 1:
        raise ValueError("gamma must have finite magnitude from zero through one")
    return g


def _rl(gamma):
    return -20 * math.log10(abs(gamma)) if abs(gamma) else math.inf


def _want(limit, unit, lower=False):
    return "requirement needed" if limit is None else f"{fmt(limit, unit)} or {'more' if lower else 'less'}"


def _limits(inputs, outputs, specs):
    verdict, lines = Verdict.INFO, []
    for name, value, unit, label, output, lower in specs:
        if value is None:
            continue
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
        inputs[name] = _q(value, unit, label)
        actual = outputs[output].value
        good = actual >= value if lower else actual <= value
        verdict = Verdict.FAIL if not good or verdict is Verdict.FAIL else Verdict.PASS
        lines.append(f"{label} is {fmt(value, unit)} or {'more' if lower else 'less'}")
    if not lines:
        wanted = " or ".join(spec[3].lower() for spec in specs) or "a numerical limit"
        return verdict, f"Supply {wanted} from the board requirement or part datasheet to judge this result."
    return verdict, "; ".join(lines) + ("; outside a supplied limit." if verdict is Verdict.FAIL else "; within the supplied limits.")


def _result(name, formula, inputs, outputs, verdict, summary, key, refs, context, assumptions=(), plots=()):
    return Result(name=name, formula=formula, inputs=inputs, outputs=outputs, verdict=verdict,
                  reason=summary, summary=summary, key=tuple(Key(k, want) for k, want in key),
                  refs=tuple(refs), assumptions=tuple(assumptions), plots=tuple(plots)).in_context(context)


def cascade(
    stages: Sequence[Stage], *, gain_min_db: float | None = None, gain_max_db: float | None = None,
    nf_max_db: float | None = None, iip3_min_dbm: float | None = None,
    oip3_min_dbm: float | None = None, context: str = "nominal", refs: tuple[str, ...] = (),
) -> Result:
    """Friis noise, power gain and input/output intercept of a matched stage chain."""
    if not stages:
        raise ValueError("at least one stage is needed")
    inputs, outputs = {}, {}
    before, noise, reciprocal_ip3 = 1.0, 1.0, 0.0
    missing_nf, missing_ip3 = False, False
    for i, stage in enumerate(stages, 1):
        if not math.isfinite(stage.gain_db):
            raise ValueError("stage gain must be finite")
        inputs[f"stage{i}_gain"] = _q(stage.gain_db, "dB", f"Stage {i} gain")
        outputs[f"stage{i}_gain_before"] = _q(10 * math.log10(before), "dB", f"Gain before stage {i}")
        if stage.nf_db is None:
            missing_nf = True
        else:
            _nonnegative(nf_db=stage.nf_db)
            inputs[f"stage{i}_nf"] = _q(stage.nf_db, "dB", f"Stage {i} noise figure")
            contribution = (10 ** (stage.nf_db / 10) - 1) / before
            noise += contribution
            outputs[f"stage{i}_noise_contribution"] = _q(contribution, "", f"Stage {i} added noise factor")
        if stage.iip3_dbm is None:
            missing_ip3 = True
        else:
            if not math.isfinite(stage.iip3_dbm):
                raise ValueError("stage intercept must be finite; use None for missing data")
            inputs[f"stage{i}_iip3"] = _q(stage.iip3_dbm, "dBm", f"Stage {i} input intercept")
            contribution = before / (1e-3 * 10 ** (stage.iip3_dbm / 10))
            reciprocal_ip3 += contribution
            outputs[f"stage{i}_ip3_contribution"] = _q(contribution, "1/W", f"Stage {i} reciprocal intercept contribution")
        before *= 10 ** (stage.gain_db / 10)
    gain = sum(stage.gain_db for stage in stages)
    nf = math.nan if missing_nf else 10 * math.log10(noise)
    ip3 = math.nan if missing_ip3 else 10 * math.log10(1e3 / reciprocal_ip3)
    outputs.update(gain_db=_q(gain, "dB", "Chain gain"), nf_db=_q(nf, "dB", "Chain noise figure"),
                   iip3_dbm=_q(ip3, "dBm", "Chain input intercept"),
                   oip3_dbm=_q(ip3 + gain, "dBm", "Chain output intercept"))
    specs = [("gain_min", gain_min_db, "dB", "Minimum gain", "gain_db", True),
             ("gain_max", gain_max_db, "dB", "Maximum gain", "gain_db", False),
             ("nf_max", nf_max_db, "dB", "Maximum noise figure", "nf_db", False),
             ("iip3_min", iip3_min_dbm, "dBm", "Minimum input intercept", "iip3_dbm", True),
             ("oip3_min", oip3_min_dbm, "dBm", "Minimum output intercept", "oip3_dbm", True)]
    known_specs = [s for s in specs if not math.isnan(outputs[s[4]].value)]
    verdict, limits = _limits(inputs, outputs, known_specs)
    for name, value, unit, label, _, _ in specs:
        if value is not None:
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
            inputs[name] = _q(value, unit, label)
    if (missing_nf or missing_ip3) and verdict is not Verdict.FAIL:
        verdict = Verdict.UNKNOWN
        limits += " Missing stage noise figure or intercept data must come from the part datasheet or measurement."
    summary = (f"The chain gain is {fmt(gain, 'dB')}, noise figure is {fmt(nf, 'dB')}, and input intercept is "
               f"{fmt(ip3, 'dBm')}; output intercept is {fmt(ip3 + gain, 'dBm')}. {limits}")
    return _result("RF cascade", "F = 1 + sum((Fi-1)/Gbefore); G = product(Gi); "
                   "1/IIP3_W = sum(Gbefore/IIP3i_W); OIP3_dBm = IIP3_dBm + G_dB",
                   inputs, outputs, verdict, summary,
                   [("gain_db", " to ".join(fmt(x, "dB") for x in (gain_min_db, gain_max_db))
                     if gain_min_db is not None and gain_max_db is not None else
                     _want(gain_min_db, "dB", True) if gain_min_db is not None else _want(gain_max_db, "dB")),
                    ("nf_db", _want(nf_max_db, "dB")),
                    ("oip3_dbm", _want(oip3_min_dbm, "dBm", True)) if oip3_min_dbm is not None else
                    ("iip3_dbm", _want(iip3_min_dbm, "dBm", True))],
                   ("AN57-1, 5952-8255E, 2010-08-05, eq. 2-3 p.8",
                    "MC-LIN, Mini-Circuits, 2022-09-30, cascade intercept formula") + refs, context,
                   ("matched power gains at one frequency and bias; noise factors share reference temperature",
                    "small-signal intercept approximation; compression and stage absolute maxima are not assessed"))


def mismatch(*, rl_db: float | None = None, gamma: complex | None = None,
             context: str = "nominal", refs: tuple[str, ...] = ()) -> Result:
    """Positive return loss or reflection magnitude to mismatch loss and VSWR."""
    if (rl_db is None) == (gamma is None):
        raise ValueError("supply exactly one of rl_db and gamma")
    inputs = {}
    if rl_db is not None:
        if math.isnan(rl_db) or rl_db < 0:
            raise ValueError("return loss must be nonnegative")
        g = 10 ** (-rl_db / 20)
        inputs["return_loss"] = _q(rl_db, "dB", "Return loss")
    else:
        g = _gamma(gamma)
        inputs["gamma_real"] = _q(complex(gamma).real, "", "Reflection real part")
        inputs["gamma_imag"] = _q(complex(gamma).imag, "", "Reflection imaginary part")
    ml = -10 * math.log10(1 - g * g) if g < 1 else math.inf
    vswr = (1 + g) / (1 - g) if g < 1 else math.inf
    outputs = {"gamma": _q(g, "", "Reflection magnitude"), "ml_db": _q(ml, "dB", "Mismatch loss"),
               "vswr": _q(vswr, "", "Voltage standing wave ratio")}
    text = (f"Reflection magnitude is {fmt(g)}, mismatch loss is {fmt(ml, 'dB')}, and VSWR is {fmt(vswr)}. "
            "This is the reflected-power loss into a matched source; compare it with the board loss budget.")
    return _result("RF mismatch", "ML = -10 log10(1-|Gamma|^2); VSWR = (1+|Gamma|)/(1-|Gamma|)",
                   inputs, outputs, Verdict.INFO, text, [("ml_db", "board loss budget"), ("vswr", "port requirement")],
                   ("DERIVED from incident and reflected power; return loss = -20 log10 |Gamma|",) + refs, context,
                   ("passive load; matched source; infinite loss or VSWR is reported as n/a at total reflection",))


def shunt_c(c_f: float, f_hz: float, z0_ohm: float, *, rl_min_db: float | None = None,
            il_max_db: float | None = None, context: str = "nominal", refs: tuple[str, ...] = ()) -> Result:
    """Return and insertion loss of an ideal shunt capacitance between equal ports."""
    _nonnegative(c_f=c_f)
    _positive(f_hz=f_hz, z0_ohm=z0_ohm)
    y = 1j * TWO_PI * f_hz * c_f * z0_ohm
    rl, il = _rl(-y / (2 + y)), -20 * math.log10(abs(2 / (2 + y)))
    inputs = {"c": _q(c_f, "F", "Shunt capacitance"), "f": _q(f_hz, "Hz", "Signal frequency"),
              "z0": _q(z0_ohm, "ohm", "Port impedance")}
    outputs = {"rl_db": _q(rl, "dB", "Return loss"), "il_db": _q(il, "dB", "Insertion loss")}
    verdict, limits = _limits(inputs, outputs,
                             [("rl_min", rl_min_db, "dB", "Minimum return loss", "rl_db", True),
                              ("il_max", il_max_db, "dB", "Maximum insertion loss", "il_db", False)])
    return _result("RF shunt capacitance", "y = j 2 pi f C Z0; S11 = -y/(2+y); S21 = 2/(2+y)",
                   inputs, outputs, verdict,
                   f"At {fmt(f_hz, 'Hz')} the return loss is {fmt(rl, 'dB')} and insertion loss is {fmt(il, 'dB')}. {limits}",
                   [("rl_db", f"at least {fmt(rl_min_db, 'dB')}" if rl_min_db is not None else "port requirement"),
                    ("il_db", f"at most {fmt(il_max_db, 'dB')}" if il_max_db is not None else "loss budget")],
                   ("DERIVED from the ABCD matrix of a shunt admittance",) + refs, context,
                   ("ideal lumped capacitance at the signal frequency; package and PCB parasitics excluded",))


def peak_voltage(p_w: float, z0_ohm: float, *, gamma: complex = 0.0, working_v: float | None = None,
                 context: str = "nominal", refs: tuple[str, ...] = ()) -> Result:
    """Incident sinusoidal power to the worst standing-wave RMS and peak voltages."""
    _nonnegative(p_w=p_w)
    _positive(z0_ohm=z0_ohm)
    g = _gamma(gamma)
    rms = math.sqrt(p_w * z0_ohm)
    peak = math.sqrt(2) * rms * (1 + g)
    inputs = {"p": _q(p_w, "W", "Incident power"), "z0": _q(z0_ohm, "ohm", "Line impedance"),
              "gamma": _q(g, "", "Reflection magnitude")}
    outputs = {"v_rms_v": _q(rms, "V", "Incident RMS voltage"),
               "v_max_rms_v": _q(rms * (1 + g), "V", "Standing-wave maximum RMS voltage"),
               "v_pk_v": _q(peak, "V", "Standing-wave maximum peak voltage")}
    if working_v is not None:
        _positive(working_v=working_v)
    verdict, limits = _limits(inputs, outputs,
                             [("working", working_v, "V", "Working voltage limit", "v_pk_v", False)])
    return _result("RF peak voltage", "Vincident_rms = sqrt(Pincident Z0); Vmax_pk = sqrt(2 Pincident Z0)(1+|Gamma|)",
                   inputs, outputs, verdict,
                   f"Incident RMS voltage is {fmt(rms, 'V')}; the maximum RF peak is {fmt(peak, 'V')}. {limits}",
                   [("v_rms_v", "incident sinusoid"), ("v_pk_v", _want(working_v, "V"))],
                   ("DERIVED; TPD1E0B04 SLVSDG9C, 2025-06, section 7.2.2 pp.13-14",) + refs, context,
                   ("incident rather than delivered power; worst standing-wave phase",
                    "sinusoid without DC offset; add waveform crest factor and DC bias separately",))


def dc_block(c_f: float, f_min_hz: float, z0_ohm: float, *, esl_h: float = 0.0, esr_ohm: float = 0.0,
             f_max_hz: float | None = None, prf_hz: float | None = None, il_max_db: float | None = None,
             context: str = "nominal", refs: tuple[str, ...] = ()) -> Result:
    """Series RLC coupling loss, ideal high-pass corner and C needed for a loss target."""
    _positive(c_f=c_f, f_min_hz=f_min_hz, z0_ohm=z0_ohm)
    _nonnegative(esl_h=esl_h, esr_ohm=esr_ohm)
    if f_max_hz is not None:
        _positive(f_max_hz=f_max_hz)
        if f_max_hz < f_min_hz:
            raise ValueError("band stop must be at or above band start")
    if prf_hz is not None:
        _positive(prf_hz=prf_hz)
    def loss(f):
        x = TWO_PI * f * esl_h - 1 / (TWO_PI * f * c_f)
        return 10 * np.log10(((2 * z0_ohm + esr_ohm) ** 2 + x * x) / (2 * z0_ohm) ** 2)
    il = float(loss(f_min_hz))
    il_stop = float(loss(f_max_hz)) if f_max_hz is not None else il
    corner = 1 / (TWO_PI * c_f * 2 * z0_ohm)
    srf = 1 / (TWO_PI * math.sqrt(esl_h * c_f)) if esl_h else math.inf
    prf_in_band = prf_hz is not None and f_max_hz is not None and f_min_hz <= prf_hz <= f_max_hz
    inputs = {"c": _q(c_f, "F", "Series capacitance"), "f_min": _q(f_min_hz, "Hz", "Lowest frequency"),
              "z0": _q(z0_ohm, "ohm", "Port impedance"), "esl": _q(esl_h, "H", "Series inductance"),
              "esr": _q(esr_ohm, "ohm", "Series resistance")}
    if f_max_hz is not None:
        inputs["f_max"] = _q(f_max_hz, "Hz", "Highest frequency")
    if prf_hz is not None:
        inputs["prf"] = _q(prf_hz, "Hz", "Published parallel resonance")
    outputs = {"il_min_db": _q(il, "dB", "Insertion loss at lowest frequency"),
               "il_worst_db": _q(max(il, il_stop), "dB", "Worst modeled band insertion loss"),
               "f_c_hz": _q(corner, "Hz", "Ideal high-pass corner"), "srf_hz": _q(srf, "Hz", "Series self-resonance"),
               "srf_in_band": _q(f_max_hz is not None and f_min_hz <= srf <= f_max_hz,
                                 "", "Series resonance inside band", "a series loss minimum, not a PRF notch"),
               "prf_in_band": _q(prf_in_band, "", "Published parallel resonance inside band",
                                 "unassessed when no PRF or upper band edge was supplied")}
    verdict, limits = _limits(inputs, outputs,
                             [("il_max", il_max_db, "dB", "Maximum band insertion loss", "il_worst_db", False)])
    if il_max_db is not None:
        _positive(il_max_db=il_max_db)
        needed = 1 / (TWO_PI * f_min_hz * 2 * z0_ohm * math.sqrt(math.expm1(il_max_db * math.log(10) / 10)))
        outputs["c_needed_f"] = _q(needed, "F", "Ideal capacitance needed", "ESL and ESR excluded from sizing")
        limits += f" An ideal capacitor needs at least {fmt(needed, 'F')} at the lowest frequency."
    if prf_in_band:
        verdict = Verdict.FAIL
        limits += f" Published PRF at {fmt(prf_hz, 'Hz')} lies inside the requested band."
    elif f_max_hz is not None and prf_hz is None and verdict is not Verdict.FAIL:
        verdict = Verdict.UNKNOWN
        limits += " PRF coverage is unknown; obtain vendor S-parameters or a VNA sweep."
    plots = ()
    if f_max_hz is not None and f_max_hz > f_min_hz:
        f = np.geomspace(f_min_hz, f_max_hz, 401)
        markers = [] if il_max_db is None else [Marker("Loss limit", y=il_max_db, unit="dB")]
        if prf_hz is not None:
            markers.append(Marker("Published PRF, not modeled", x=prf_hz))
        plots = (plot_from_arrays("DC block insertion loss", "Frequency", "Hz", f,
                                 [("Series RLC loss", "dB", loss(f))], x_log=True, markers=markers,
                                 caption="Series RLC loss only. A published PRF notch is marked but not modeled."),)
    return _result("RF DC block", "Zc = ESR + j(2 pi f ESL - 1/(2 pi f C)); "
                   "S21 = 2 Z0/(2 Z0+Zc); fc = 1/(4 pi Z0 C); Cneeded = 1/(4 pi f Z0 sqrt(10^(IL/10)-1))",
                   inputs, outputs, verdict,
                   f"Loss at the lowest frequency is {fmt(il, 'dB')}; worst modeled band loss is {fmt(max(il, il_stop), 'dB')}. "
                   f"The ideal corner is {fmt(corner, 'Hz')}. {limits}",
                   [("il_worst_db", _want(il_max_db, "dB")), ("f_c_hz", "below the operating band")],
                   ("ATC 001-927 Rev E, 2005-01, coupling and DC blocking; DERIVED series RLC transfer",
                    "JTI-SRF, 1999-01-17 p.1, SRF and PRF distinction") + refs, context,
                   ("equal real source and load impedances; corner and sizing use an ideal C",
                    "SRF is a loss minimum for a series capacitor, not a notch; PRF is not predicted by series RLC",
                    "voltage rating, dielectric bias and model validity require separate checks"), plots)


def pad(a_db: float, z0_ohm: float, *, topology: str = "pi", p_in_w: float,
        fitted_ohm: Sequence[float] | None = None, ratings_w: Sequence[float] | None = None,
        loss_error_max_db: float | None = None, rl_min_db: float | None = None,
        power_fraction_max: float | None = None, context: str = "nominal", refs: tuple[str, ...] = ()) -> Result:
    """Design a pi or T pad and evaluate fitted values and individual resistor powers."""
    _positive(a_db=a_db, z0_ohm=z0_ohm)
    _nonnegative(p_in_w=p_in_w)
    if topology not in ("pi", "t"):
        raise ValueError("topology must be pi or t")
    k = 10 ** (a_db / 20)
    if topology == "pi":
        r1 = z0_ohm * (k + 1) / (k - 1)
        r2 = z0_ohm * (k * k - 1) / (2 * k)
    else:
        r1 = z0_ohm * (k - 1) / (k + 1)
        r2 = 2 * k * z0_ohm / (k * k - 1)
    ideal = (r1, r2, r1)
    fitted = tuple(fitted_ohm) if fitted_ohm is not None else ideal
    if len(fitted) != 3:
        raise ValueError("fitted_ohm must contain input, middle and output resistor values")
    for value in fitted:
        _positive(resistor_ohm=value)
    r1, r2, r3 = fitted
    if topology == "pi":
        matrix = np.array([[1, 0], [1 / r1, 1]]) @ np.array([[1, r2], [0, 1]]) @ np.array([[1, 0], [1 / r3, 1]])
    else:
        matrix = np.array([[1, r1], [0, 1]]) @ np.array([[1, 0], [1 / r2, 1]]) @ np.array([[1, r3], [0, 1]])
    a, b, c, d = matrix.ravel()
    denominator = a + b / z0_ohm + c * z0_ohm + d
    s21 = 2 / denominator
    s11 = (a + b / z0_ohm - c * z0_ohm - d) / denominator
    s22 = (-a + b / z0_ohm - c * z0_ohm + d) / denominator
    loss = -20 * math.log10(abs(s21))
    vin = math.sqrt(p_in_w * z0_ohm) * (1 + s11)
    vout = math.sqrt(p_in_w * z0_ohm) * s21
    if topology == "pi":
        powers = (vin * vin / r1, (vin - vout) ** 2 / r2, vout * vout / r3)
    else:
        iout = vout / z0_ohm
        vmid = vout + iout * r3
        powers = ((vin - vmid) ** 2 / r1, vmid * vmid / r2, iout * iout * r3)
    inputs = {"a": _q(a_db, "dB", "Target attenuation"), "z0": _q(z0_ohm, "ohm", "Port impedance"),
              "p_in": _q(p_in_w, "W", "Available incident input power")}
    outputs = {"loss_db": _q(loss, "dB", "Fitted attenuation"),
               "loss_error_db": _q(abs(loss - a_db), "dB", "Absolute attenuation error"),
               "rl_input_db": _q(_rl(s11), "dB", "Input return loss"),
               "rl_output_db": _q(_rl(s22), "dB", "Output return loss"),
               "rl_worst_db": _q(min(_rl(s11), _rl(s22)), "dB", "Worst port return loss"),
               "p_out_w": _q(p_in_w * s21 * s21, "W", "Load power"),
               "p_reflected_w": _q(p_in_w * s11 * s11, "W", "Reflected input power")}
    roles = ("input shunt", "series", "output shunt") if topology == "pi" else ("input series", "shunt", "output series")
    for i, (design, actual, power, role) in enumerate(zip(ideal, fitted, powers, roles), 1):
        inputs[f"r{i}_fitted"] = _q(actual, "ohm", f"Fitted {role} resistor")
        outputs[f"r{i}_ideal_ohm"] = _q(design, "ohm", f"Ideal {role} resistor")
        outputs[f"p{i}_w"] = _q(power, "W", f"Power in {role} resistor")
    specs = [("loss_error_max", loss_error_max_db, "dB", "Maximum attenuation error", "loss_error_db", False),
             ("rl_min", rl_min_db, "dB", "Minimum port return loss", "rl_worst_db", True)]
    if ratings_w is not None:
        if len(ratings_w) != 3:
            raise ValueError("ratings_w must contain three resistor ratings")
        for i, rating in enumerate(ratings_w, 1):
            _positive(rating_w=rating)
            inputs[f"rating{i}"] = _q(rating, "W", f"Resistor {i} power rating")
        fraction = max(power / rating for power, rating in zip(powers, ratings_w))
        outputs["power_fraction"] = _q(fraction, "", "Largest fraction of resistor rating")
        if power_fraction_max is not None:
            _positive(power_fraction_max=power_fraction_max)
        specs.append(("power_fraction_max", power_fraction_max, "", "Maximum fraction of power rating", "power_fraction", False))
    verdict, limits = _limits(inputs, outputs, specs)
    if (ratings_w is None) != (power_fraction_max is None):
        if power_fraction_max is not None:
            _positive(power_fraction_max=power_fraction_max)
            inputs["power_fraction_max"] = _q(power_fraction_max, "", "Maximum fraction of power rating")
        if verdict is not Verdict.FAIL:
            verdict = Verdict.UNKNOWN
        limits += " Supply both resistor ratings from the datasheet and an allowed rating fraction from the board requirement."
    text = (f"The {topology} pad gives {fmt(loss, 'dB')} attenuation and {fmt(outputs['rl_worst_db'].value, 'dB')} "
            f"worst port return loss; the largest resistor dissipation is {fmt(max(powers), 'W')}. {limits}")
    key = [("loss_db", f"{fmt(a_db, 'dB')} target, error {_want(loss_error_max_db, 'dB')}"),
           ("rl_worst_db", _want(rl_min_db, "dB", True))]
    if ratings_w is not None:
        text += f" The largest fraction of a resistor rating is {fmt(fraction)}."
        key.append(("power_fraction", _want(power_fraction_max, "")))
    return _result("RF attenuator pad", "K=10^(A/20); pi: Rp=Z0(K+1)/(K-1), Rs=Z0(K^2-1)/(2K); "
                   "T: Rs=Z0(K-1)/(K+1), Rp=2KZ0/(K^2-1); S21=2/(A+B/Z0+CZ0+D); P=Vrms^2/R",
                   inputs, outputs, verdict, text, key,
                   ("DERIVED resistive nodal analysis; FRICKEY, IEEE T-MTT 42(2), 1994-02, Table I pp.205-211",) + refs,
                   context, (f"topology {topology}; resistor order is input, middle, output",
                             "ideal resistors; equal matched ports; input power is available incident power",
                             "frequency response and thermal derating require part and layout data"))


def stability(s, f_hz, *, k_min: float | None = None, delta_max: float | None = None,
              mu_min: float | None = None, context: str = "nominal", refs: tuple[str, ...] = ()) -> Result:
    """Rollett K, determinant and both mu factors at each supplied S-parameter point."""
    f = np.atleast_1d(np.asarray(f_hz, dtype=float))
    data = np.asarray(s, dtype=complex)
    if data.shape == (2, 2):
        data = data[None, ...]
    if f.ndim != 1 or data.shape != (len(f), 2, 2) or len(f) == 0:
        raise ValueError("s must have shape (N,2,2), with N frequencies")
    if not np.all(np.isfinite(data)) or not np.all(np.isfinite(f)) or np.any(f <= 0) or np.any(np.diff(f) <= 0):
        raise ValueError("finite S-parameters and positive increasing frequencies are required")
    s11, s12, s21, s22 = data[:, 0, 0], data[:, 0, 1], data[:, 1, 0], data[:, 1, 1]
    delta = s11 * s22 - s12 * s21
    coupling = np.abs(s12 * s21)
    numerator = 1 - np.abs(s11) ** 2 - np.abs(s22) ** 2 + np.abs(delta) ** 2
    with np.errstate(divide="ignore", invalid="ignore"):
        kval = numerator / (2 * coupling)
        mu = (1 - np.abs(s11) ** 2) / (np.abs(s22 - delta * s11.conj()) + coupling)
        mup = (1 - np.abs(s22) ** 2) / (np.abs(s11 - delta * s22.conj()) + coupling)
    inputs, outputs = {}, {}
    for i, frequency in enumerate(f, 1):
        inputs[f"f{i}"] = _q(frequency, "Hz", f"Sample {i} frequency")
        for row, col in product(range(2), repeat=2):
            v = data[i - 1, row, col]
            for component, value in (("real", v.real), ("imag", v.imag)):
                inputs[f"s{row+1}{col+1}_{i}_{component}"] = _q(value, "", f"Sample {i} S{row+1}{col+1} {component} part")
        for name, values, label in (("k", kval, "Rollett factor"), ("delta_abs", abs(delta), "Determinant magnitude"),
                                    ("mu", mu, "Input mu factor"), ("mu_prime", mup, "Output mu factor")):
            outputs[f"{name}{i}"] = _q(values[i - 1], "", f"Sample {i} {label}")
    outputs.update(k_min=_q(np.min(kval), "", "Lowest Rollett factor"),
                   delta_max=_q(np.max(abs(delta)), "", "Largest determinant magnitude"),
                   mu_min=_q(np.min(mu), "", "Lowest input mu factor"),
                   mu_prime_min=_q(np.min(mup), "", "Lowest output mu factor"))
    for name, value, label in (("k_limit", k_min, "Minimum Rollett factor"),
                               ("delta_limit", delta_max, "Maximum determinant magnitude"),
                               ("mu_limit", mu_min, "Minimum input mu factor")):
        if value is not None:
            if not math.isfinite(value):
                raise ValueError("stability limits must be finite")
            inputs[name] = _q(value, "", label)
    routes = []
    route_scores = []
    if k_min is not None and delta_max is not None:
        routes.append((kval > k_min) & (abs(delta) < delta_max))
        route_scores.append(np.minimum(kval - k_min, delta_max - abs(delta)))
    if mu_min is not None:
        routes.append(mu > mu_min)
        route_scores.append(mu - mu_min)
    if routes:
        good = np.logical_or.reduce(routes)
        scores = np.maximum.reduce(route_scores)
        worst = int(np.nanargmin(scores)) if not np.all(np.isnan(scores)) else 0
        verdict = Verdict.PASS if np.all(good) else Verdict.FAIL
        limits = ("Every supplied point is inside a complete supplied criterion." if verdict is Verdict.PASS else
                  "At least one supplied point is outside every complete supplied criterion; stability is not established.")
        if any(np.any(np.isnan(score)) for score in route_scores):
            verdict = Verdict.UNKNOWN
            limits = "A stability ratio is indeterminate; inspect the degenerate two-port and its terminations."
    else:
        worst = int(np.nanargmin(mu)) if not np.all(np.isnan(mu)) else 0
        verdict = Verdict.UNKNOWN
        limits = "Supply both K and determinant limits, or a mu limit, from the stability criterion in the requirement or datasheet."
    outputs["f_worst_hz"] = _q(f[worst], "Hz", "Worst supplied stability frequency")
    text = (f"The lowest Rollett factor is {fmt(float(np.min(kval)))}, largest determinant magnitude is "
            f"{fmt(float(np.max(abs(delta))))}, and lowest input mu is {fmt(float(np.min(mu)))}. {limits} "
            "These samples do not establish stability between points or outside the file band.")
    plots = ()
    if len(f) > 1:
        markers = [Marker("Worst supplied point", x=float(f[worst]))]
        markers += [Marker(label, y=value, unit="") for label, value in
                    (("K limit", k_min), ("Determinant limit", delta_max), ("Mu limit", mu_min)) if value is not None]
        plots = (plot_from_arrays("Amplifier stability", "Frequency", "Hz", f,
                                 [("K", "", kval), ("Determinant magnitude", "", abs(delta)),
                                  ("Input mu", "", mu), ("Output mu", "", mup)], x_log=True, markers=markers,
                                 caption="Compare all supplied frequency points with the caller's strict stability limits."),)
    return _result("RF two-port stability", "Delta=S11*S22-S12*S21; K=(1-|S11|^2-|S22|^2+|Delta|^2)/(2|S12*S21|); "
                   "mu=(1-|S11|^2)/(|S22-Delta*conj(S11)|+|S12*S21|); mu'=swap ports",
                   inputs, outputs, verdict, text,
                   [("k_min", f"strictly above {fmt(k_min)}" if k_min is not None else "criterion needed"),
                    ("delta_max", f"strictly below {fmt(delta_max)}" if delta_max is not None else "criterion needed"),
                    ("mu_min", f"strictly above {fmt(mu_min)}" if mu_min is not None else "criterion needed")],
                   ("KS5072 5990-9974EN, 2012-03-22 p.3; corrected determinant uses S11*S22",
                    "AN154 5952-1087, 2000-11 pp.19-22",
                    "UNSURE: mu source Edwards and Sinsky 1992 not opened; formula supplied in plan section 10.4") + refs,
                   context, ("linear two-port at the supplied bias, temperature and real reference impedance",
                             "strict inequalities; alternate complete criteria are combined per frequency"), plots)


def cavity_modes(a_m: float, b_m: float, d_m: float, *, f_max_hz: float | None = None,
                 epsilon_r: float = 1.0, count: int = 6, context: str = "nominal",
                 refs: tuple[str, ...] = ()) -> Result:
    """Lowest rectangular closed-cavity resonances, including permittivity if uniformly filled."""
    _positive(a_m=a_m, b_m=b_m, d_m=d_m, epsilon_r=epsilon_r)
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError("count must be a positive integer")
    # Every omitted index exceeds count, so its mode lies above count known two-index modes.
    modes = sorted((299792458 / (2 * math.sqrt(epsilon_r)) * math.sqrt((m / a_m) ** 2 + (n / b_m) ** 2 + (p / d_m) ** 2), m, n, p)
                   for m, n, p in product(range(count + 1), repeat=3) if (m == 0) + (n == 0) + (p == 0) <= 1)[:count]
    inputs = {"a": _q(a_m, "m", "Cavity length"), "b": _q(b_m, "m", "Cavity width"),
              "d": _q(d_m, "m", "Cavity height"), "epsilon_r": _q(epsilon_r, "", "Uniform relative permittivity"),
              "count": _q(count, "count", "Modes requested")}
    outputs = {"lowest_hz": _q(modes[0][0], "Hz", "Lowest cavity resonance")}
    for i, (frequency, m, n, p) in enumerate(modes, 1):
        outputs[f"mode{i}_hz"] = _q(frequency, "Hz", f"Cavity mode {m},{n},{p}")
    verdict = Verdict.INFO
    limit = "Supply the highest significant RF or harmonic frequency from the board requirement."
    if f_max_hz is not None:
        _positive(f_max_hz=f_max_hz)
        inputs["f_max"] = _q(f_max_hz, "Hz", "Highest significant frequency")
        verdict = Verdict.PASS if modes[0][0] > f_max_hz else Verdict.FAIL
        limit = f"The required highest significant frequency is {fmt(f_max_hz, 'Hz')}; the lowest mode is {'above' if verdict is Verdict.PASS else 'at or below'} it."
    return _result("RF shield cavity", "f_mnp=c/(2 sqrt(er))*sqrt((m/a)^2+(n/b)^2+(p/d)^2); at most one index zero",
                   inputs, outputs, verdict,
                   f"The lowest ideal cavity resonance is {fmt(modes[0][0], 'Hz')}. {limit}",
                   [("lowest_hz", f"above {fmt(f_max_hz, 'Hz')}" if f_max_hz is not None else "highest significant frequency needed")],
                   ("ICM, Cavity Resonances of Shielding Boxes and Cans, 2023-08-01; DERIVED closed-box modes",) + refs,
                   context, ("perfectly conducting closed rectangular cavity; uniform filling",
                             "mode indices count distinct index triples, not TE/TM degeneracy",
                             "PCB dielectric, seams, openings and internal metal can shift modes; bench verification required"))


def network_impedance(branches: Sequence[Cap], f_min_hz: float, f_max_hz: float, *,
                      z_max_ohm: float | None = None, forbidden_bands_hz: Sequence[tuple[float, float]] | None = None,
                      points_per_decade: int = 1000, context: str = "nominal", refs: tuple[str, ...] = ()) -> Result:
    """Parallel series-RLC capacitors, self-resonances and refined anti-resonance peaks."""
    _positive(f_min_hz=f_min_hz, f_max_hz=f_max_hz)
    if f_max_hz <= f_min_hz or not branches:
        raise ValueError("a nonempty network and increasing frequency range are required")
    if not isinstance(points_per_decade, int) or points_per_decade < 10:
        raise ValueError("points_per_decade must be an integer of at least 10")
    inputs = {"f_min": _q(f_min_hz, "Hz", "Sweep start"), "f_max": _q(f_max_hz, "Hz", "Sweep stop"),
              "points_per_decade": _q(points_per_decade, "count", "Sweep points per decade")}
    outputs, srfs = {}, []
    for i, branch in enumerate(branches, 1):
        _positive(c_f=branch.c_f)
        _nonnegative(esl_h=branch.esl_h, esr_ohm=branch.esr_ohm)
        inputs[f"c{i}"] = _q(branch.c_f, "F", f"Capacitor {i} capacitance")
        inputs[f"esl{i}"] = _q(branch.esl_h, "H", f"Capacitor {i} ESL")
        inputs[f"esr{i}"] = _q(branch.esr_ohm, "ohm", f"Capacitor {i} ESR")
        srf = 1 / (TWO_PI * math.sqrt(branch.esl_h * branch.c_f)) if branch.esl_h else math.inf
        outputs[f"srf{i}_hz"] = _q(srf, "Hz", f"Capacitor {i} self-resonance")
        if f_min_hz < srf < f_max_hz:
            srfs.append(srf)
    bands = tuple(forbidden_bands_hz) if forbidden_bands_hz is not None else ()
    for i, (lo, hi) in enumerate(bands, 1):
        _positive(band_start_hz=lo, band_stop_hz=hi)
        if hi < lo:
            raise ValueError("forbidden band must be increasing")
        inputs[f"band{i}_start"] = _q(lo, "Hz", f"Forbidden band {i} start")
        inputs[f"band{i}_stop"] = _q(hi, "Hz", f"Forbidden band {i} stop")
    def magnitude(f):
        impedances = np.array([branch.z(f) for branch in branches])
        with np.errstate(divide="ignore", invalid="ignore"):
            z = 1 / np.sum(1 / impedances, axis=0)
        return np.where(np.any(impedances == 0, axis=0), 0.0, np.abs(z))
    n = math.ceil(math.log10(f_max_hz / f_min_hz) * points_per_decade) + 1
    f = np.unique(np.r_[np.geomspace(f_min_hz, f_max_hz, n), srfs])
    z = magnitude(f)
    peaks = []
    for index in find_peaks(z)[0]:
        optimum = minimize_scalar(lambda lf: -float(magnitude(math.exp(lf))),
                                  bounds=(math.log(f[index-1]), math.log(f[index+1])),
                                  method="bounded", options={"xatol": 1e-13})
        fp = math.exp(optimum.x)
        peaks.append((fp, float(magnitude(fp))))
    f = np.unique(np.r_[f, [p[0] for p in peaks]])
    z = magnitude(f)
    worst = int(np.argmax(z))
    outputs["z_max_ohm"] = _q(z[worst], "ohm", "Largest impedance in sweep")
    outputs["f_max_z_hz"] = _q(f[worst], "Hz", "Frequency of largest impedance")
    outputs["peak_count"] = _q(len(peaks), "count", "Interior anti-resonance peaks")
    for i, (frequency, impedance) in enumerate(peaks, 1):
        outputs[f"peak{i}_hz"] = _q(frequency, "Hz", f"Anti-resonance {i} frequency")
        outputs[f"peak{i}_ohm"] = _q(impedance, "ohm", f"Anti-resonance {i} impedance")
    verdict, limits = _limits(inputs, outputs,
                             [("z_limit", z_max_ohm, "ohm", "Maximum network impedance", "z_max_ohm", False)])
    if z_max_ohm is not None:
        _positive(z_max_ohm=z_max_ohm)
    hits = [(fp, zp) for fp, zp in peaks if any(lo <= fp <= hi for lo, hi in bands)]
    if bands:
        if hits:
            verdict = Verdict.FAIL
            limits += f" {len(hits)} interior peak(s) lie in the forbidden bands."
        elif any(lo < f_min_hz or hi > f_max_hz for lo, hi in bands):
            if verdict is not Verdict.FAIL:
                verdict = Verdict.UNKNOWN
            limits += " Extend the sweep to cover every forbidden band."
        elif verdict is not Verdict.FAIL:
            verdict = Verdict.PASS
            limits = "No interior anti-resonance peak lies in the supplied forbidden bands. " + (limits if z_max_ohm is not None else "")
    main = max(peaks, key=lambda item: item[1]) if peaks else (float(f[worst]), float(z[worst]))
    outputs["f_peak_hz"] = _q(main[0], "Hz", "Largest interior peak frequency" if peaks else "Largest sampled impedance frequency")
    outputs["z_peak_ohm"] = _q(main[1], "ohm", "Largest interior peak impedance" if peaks else "Largest sampled impedance")
    text = (f"The network has {fmt(len(peaks), 'count')} interior peak(s); its selected peak is {fmt(main[1], 'ohm')} "
            f"at {fmt(main[0], 'Hz')}. The largest impedance over the sweep is {fmt(float(z[worst]), 'ohm')}. {limits}")
    markers = [Marker("Selected peak", x=main[0], y=main[1], unit="ohm")]
    if z_max_ohm is not None:
        markers.append(Marker("Impedance limit", y=z_max_ohm, unit="ohm"))
    curves = [("Parallel network", "ohm", z)] + [(f"Capacitor {i} alone", "ohm", abs(branch.z(f))) for i, branch in enumerate(branches, 1)]
    plots = (plot_from_arrays("RF decoupling impedance", "Frequency", "Hz", f, curves, x_log=True, y_log=True,
                             markers=markers, caption="Interior peaks are refined numerically; compare the network with each capacitor alone."),)
    return _result("RF parallel capacitor network", "Zi=ESRi+j(2 pi f ESLi-1/(2 pi f Ci)); Z=1/sum(1/Zi); SRFi=1/(2 pi sqrt(ESLi Ci))",
                   inputs, outputs, verdict, text, [("z_peak_ohm", "board impedance requirement"),
                   ("f_peak_hz", "outside specified forbidden bands"), ("z_max_ohm", _want(z_max_ohm, "ohm"))],
                   ("CY1032 AN1032 001-19299 Rev *C, 2014-11-03 pp.2-3; DERIVED series RLC branches",) + refs,
                   context, ("lumped constant C, ESL and ESR; no feed impedance or PCB coupling",
                             "peak search uses a log grid and bounded refinement; very narrow unsampled peaks can be missed",
                             "assumed ESL or missing frequency-dependent vendor data cannot establish a board pass"), plots)
