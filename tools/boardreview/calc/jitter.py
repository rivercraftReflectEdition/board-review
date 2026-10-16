"""Clock jitter, phase noise and converter SNR with caller-supplied limits."""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from scipy.special import jv

from boardreview.calc.base import Band, Key, Marker, Quantity, Result, Verdict, fmt, plot_from_arrays

TWO_PI = 2 * math.pi
MT008 = "ADI MT-008 Rev A, October 2008, p.2 and p.4, equations 2 to 3"
AN491 = "Skyworks AN491 Rev 0.2, September 22 2021, p.6, equation 1"
AN756 = "ADI AN-756 Rev 0, December 2004, p.5, equations 12 to 13"
BANERJEE = "TI SNAA106C, May 2017, printed p.1, 12 and 228"
LIMIT_SOURCE = "the requirement, the part datasheet, or a stated engineering judgment"


def _finite(**values) -> None:
    for name, value in values.items():
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")


def _positive(**values) -> None:
    _finite(**values)
    for name, value in values.items():
        if value <= 0:
            raise ValueError(f"{name} must be positive")


def _nonnegative(**values) -> None:
    _finite(**values)
    for name, value in values.items():
        if value < 0:
            raise ValueError(f"{name} must be nonnegative")


def _db_power(value: float, factor: float = 10) -> float:
    return factor * math.log10(value) if value > 0 else -math.inf


def _value_text(value: float, unit: str) -> str:
    if value == -math.inf:
        return "no contribution"
    if value == math.inf:
        return "unbounded"
    return fmt(value, unit)


def _limit(value: float, unit: str, label: str, limit: float | None, inputs: dict,
           marginal_limit: float | None = None, minimum: bool = False) -> tuple[Verdict, str, str]:
    if limit is None:
        if marginal_limit is not None:
            raise ValueError("a marginal limit needs a pass limit")
        return Verdict.INFO, f"no {label.lower()} limit supplied", f"Supply a {label.lower()} limit from {LIMIT_SOURCE}."
    _finite(limit=limit)
    inputs["limit"] = Quantity(limit, unit, LIMIT_SOURCE, f"{label} limit")
    if marginal_limit is not None:
        _finite(marginal_limit=marginal_limit)
        if minimum or marginal_limit < limit:
            raise ValueError("the marginal upper limit must be at least the pass limit")
        inputs["marginal_limit"] = Quantity(marginal_limit, unit, LIMIT_SOURCE, f"{label} marginal upper limit")
    ok = value >= limit if minimum else value <= limit
    if ok:
        verdict, phrase = Verdict.PASS, "is at or above" if minimum else "is at or below"
    elif marginal_limit is not None and value <= marginal_limit:
        verdict, phrase = Verdict.MARGINAL, "is above"
    else:
        verdict, phrase = Verdict.FAIL, "does not meet"
    direction = "minimum" if minimum else "maximum"
    text = f"This {phrase} the supplied {fmt(limit, unit)} {direction} {label.lower()} limit."
    if verdict is Verdict.MARGINAL:
        text += f" It is within the supplied {fmt(marginal_limit, unit)} marginal upper limit."
    return verdict, text, text


def _table(points: Sequence[tuple[float, float]], name: str) -> np.ndarray:
    data = np.asarray(points, dtype=float)
    if data.ndim != 2 or data.shape[1] != 2 or len(data) < 2:
        raise ValueError(f"{name} needs at least two frequency and level pairs")
    if not np.isfinite(data).all() or np.any(data[:, 0] <= 0) or np.any(np.diff(data[:, 0]) <= 0):
        raise ValueError(f"{name} needs finite levels and strictly increasing positive frequencies")
    return data


def _table_inputs(data: np.ndarray, prefix: str, label: str, unit: str) -> dict[str, Quantity]:
    inputs = {}
    for i, (frequency, level) in enumerate(data, 1):
        inputs[f"{prefix}{i}_hz"] = Quantity(frequency, "Hz", label=f"{label} point {i} offset")
        inputs[f"{prefix}{i}_db"] = Quantity(level, unit, label=f"{label} point {i} level")
    return inputs


def snr_jitter(f_in_hz: float, t_clk_s: float, t_ap_s: float = 0.0, snr_adc_db: float | None = None, *,
               loss_limit_db: float | None = None, loss_fail_db: float | None = None,
               snr_min_db: float | None = None, context: str = "nominal") -> Result:
    """Jitter-limited SNR and optional converter SNR degradation at the analog input frequency."""
    _positive(f_in_hz=f_in_hz)
    _nonnegative(t_clk_s=t_clk_s, t_ap_s=t_ap_s)
    if snr_adc_db is not None:
        _finite(snr_adc_db=snr_adc_db)
    if snr_adc_db is None and (loss_limit_db is not None or loss_fail_db is not None):
        raise ValueError("an SNR loss limit needs the converter's own SNR")
    if loss_limit_db is not None:
        _nonnegative(loss_limit_db=loss_limit_db)
    total_s = math.hypot(t_clk_s, t_ap_s)
    noise_db = _db_power(TWO_PI * f_in_hz * total_s, 20)
    snr_j_db = -noise_db
    inputs = {"f_in_hz": Quantity(f_in_hz, "Hz", label="Analog input frequency"),
              "t_clk_s": Quantity(t_clk_s, "s", label="External clock RMS jitter"),
              "t_ap_s": Quantity(t_ap_s, "s", label="Converter aperture RMS jitter")}
    outputs = {"total_s": Quantity(total_s, "s", label="Combined RMS jitter"),
               "snr_j_db": Quantity(snr_j_db, "dB", label="Jitter-limited SNR")}
    summary = (f"The combined RMS jitter is {fmt(total_s, 's')} at {fmt(f_in_hz, 'Hz')}, giving "
               f"{_value_text(snr_j_db, 'dB')} of jitter-limited SNR.")
    key = [Key("total_s"), Key("snr_j_db") if total_s else Key("t_clk_s")]
    verdict, reason = Verdict.INFO, "no SNR or SNR loss limit supplied"
    checks = []
    if snr_adc_db is not None:
        inputs["snr_adc_db"] = Quantity(snr_adc_db, "dB", label="Converter SNR without the added jitter")
        loss_db = float(10 / math.log(10) * np.logaddexp(0.0, (snr_adc_db + noise_db) * math.log(10) / 10))
        snr_total_db = snr_adc_db - loss_db
        outputs.update(snr_total_db=Quantity(snr_total_db, "dB", label="Combined converter SNR"),
                       loss_db=Quantity(loss_db, "dB", label="SNR loss from jitter"))
        summary += f" The converter then has {fmt(snr_total_db, 'dB')} SNR, a loss of {fmt(loss_db, 'dB')}."
        key = [Key("total_s"), Key("snr_total_db"), Key("loss_db")]
        if loss_limit_db is not None or loss_fail_db is not None:
            checks.append(_limit(loss_db, "dB", "SNR loss", loss_limit_db, inputs, loss_fail_db))
    if snr_min_db is not None:
        snr_inputs = {}
        checks.append(_limit(outputs.get("snr_total_db", outputs["snr_j_db"]).value, "dB", "SNR",
                             snr_min_db, snr_inputs, minimum=True))
        inputs["snr_min_db"] = snr_inputs["limit"]
        allowed_noise = 10 ** (-snr_min_db / 10)
        if snr_adc_db is not None:
            allowed_noise -= 10 ** (-snr_adc_db / 10)
        if allowed_noise >= 0:
            outputs["jitter_allowed_s"] = Quantity(math.sqrt(allowed_noise) / (TWO_PI * f_in_hz), "s",
                                                  "includes aperture jitter", "Total RMS jitter allowed by SNR")
    if checks:
        verdict = max((v for v, _, _ in checks), key=lambda v: {Verdict.PASS: 0, Verdict.MARGINAL: 1, Verdict.FAIL: 2}[v])
        reason = " ".join(r for _, r, _ in checks)
        summary += " " + " ".join(s for _, _, s in checks)
    else:
        summary += f" Supply a minimum SNR or maximum SNR loss from {LIMIT_SOURCE}."
    plots = ()
    if total_s > 0:
        f = np.unique(np.r_[np.geomspace(f_in_hz / 100, f_in_hz * 100, 201), f_in_hz])
        jitter_db = -20 * np.log10(TWO_PI * f * total_s)
        series = [("Jitter SNR", "dB", jitter_db)]
        if snr_adc_db is not None:
            combined = -10 / math.log(10) * np.logaddexp(-snr_adc_db * math.log(10) / 10,
                                                       -jitter_db * math.log(10) / 10)
            series.append(("Converter SNR", "dB", combined))
        markers = [Marker("Analog input", x=f_in_hz)]
        if snr_min_db is not None:
            markers.append(Marker("Required SNR", y=snr_min_db, unit="dB"))
        plots = (plot_from_arrays("SNR against analog input frequency", "Analog input frequency", "Hz", f,
                                  series, x_log=True, markers=markers,
                                  caption=f"RMS jitter is fixed at {fmt(total_s, 's')}; the marked input is "
                                          f"{fmt(f_in_hz, 'Hz')}."),)
    return Result("Converter SNR from jitter", "t = hypot(t_clk, t_ap); SNRj = -20 log10(2 pi f_in t); "
                  "SNRtotal = -10 log10(10^(-SNRadc/10) + 10^(-SNRj/10)); loss = SNRadc - SNRtotal",
                  inputs, outputs, verdict, reason, refs=(MT008, "ADI AN-501 Rev A, March 2006, p.2, equations 5 to 6"),
                  assumptions=("sinusoidal analog input", "uncorrelated clock and aperture jitter",
                               "converter baseline SNR excludes the jitter added here; do not count aperture noise twice"),
                  plots=plots, summary=summary, key=tuple(key)).in_context(context)


def pn_to_jitter(points: Sequence[tuple[float, float]], f1_hz: float, f2_hz: float, f0_hz: float, *,
                 limit_s: float | None = None, marginal_limit_s: float | None = None,
                 mask_points_db: Sequence[tuple[float, float]] | None = None,
                 context: str = "nominal") -> Result:
    """Integrate SSB phase noise with exact power laws between log-frequency table points."""
    _positive(f1_hz=f1_hz, f2_hz=f2_hz, f0_hz=f0_hz)
    data = _table(points, "phase noise table")
    if not data[0, 0] <= f1_hz < f2_hz <= data[-1, 0]:
        raise ValueError("integration band must be increasing and inside the phase noise table")
    mask = _table(mask_points_db, "mask table") if mask_points_db is not None else None
    if mask is not None and not mask[0, 0] <= f1_hz < f2_hz <= mask[-1, 0]:
        raise ValueError("integration band must be inside the mask table")
    bounds = [f1_hz, f2_hz, *data[(data[:, 0] > f1_hz) & (data[:, 0] < f2_hz), 0]]
    if mask is not None:
        bounds.extend(mask[(mask[:, 0] > f1_hz) & (mask[:, 0] < f2_hz), 0])
    f = np.unique(bounds)
    levels = np.interp(np.log(f), np.log(data[:, 0]), data[:, 1])
    if mask is not None:
        levels += np.interp(np.log(f), np.log(mask[:, 0]), mask[:, 1])
    areas = []
    for lo, hi, l_lo, l_hi in zip(f[:-1], f[1:], levels[:-1], levels[1:]):
        width = math.log(hi / lo)
        exponent = (l_hi - l_lo) * math.log(10) / 10 + width
        ratio = math.expm1(exponent) / exponent if exponent != 0 else 1.0
        areas.append(10 ** (l_lo / 10) * lo * width * ratio)
    area = math.fsum(areas)
    sigma = math.sqrt(2 * area)
    jitter_s = sigma / (TWO_PI * f0_hz)
    inputs = {"f1_hz": Quantity(f1_hz, "Hz", label="Integration band start"),
              "f2_hz": Quantity(f2_hz, "Hz", label="Integration band stop"),
              "f0_hz": Quantity(f0_hz, "Hz", label="Clock carrier frequency"),
              **_table_inputs(data, "pn", "Phase noise", "dBc/Hz")}
    if mask is not None:
        inputs.update(_table_inputs(mask, "mask", "Transfer magnitude", "dB"))
    if limit_s is not None:
        _nonnegative(limit_s=limit_s)
    verdict, reason, limit_text = _limit(jitter_s, "s", "RMS jitter", limit_s, inputs, marginal_limit_s)
    plot_f = np.unique(np.r_[data[:, 0], f, np.geomspace(data[0, 0], data[-1, 0], 240)])
    plot_l = np.interp(np.log(plot_f), np.log(data[:, 0]), data[:, 1])
    series = [("Phase noise", "dBc/Hz", plot_l)]
    if mask is not None:
        inside = (plot_f >= f1_hz) & (plot_f <= f2_hz)
        effective = np.full_like(plot_f, np.nan)
        effective[inside] = plot_l[inside] + np.interp(np.log(plot_f[inside]), np.log(mask[:, 0]), mask[:, 1])
        series.append(("After transfer", "dBc/Hz", effective))
    plot = plot_from_arrays("Phase noise integration", "Offset frequency", "Hz", plot_f, series, x_log=True,
                            markers=(Marker("Band start", x=f1_hz), Marker("Band stop", x=f2_hz)),
                            bands=(Band("Integrated offset band", f1_hz, f2_hz),),
                            caption=f"The shaded band from {fmt(f1_hz, 'Hz')} to {fmt(f2_hz, 'Hz')} contributes "
                                    f"{fmt(jitter_s, 's')} RMS jitter at {fmt(f0_hz, 'Hz')}.")
    return Result("Integrated phase noise jitter", "A = integral(10^(L/10) |H|^2 df); "
                  "L is linear in log(f) per segment; sigma = sqrt(2 A); jitter = sigma/(2 pi f0)", inputs,
                  {"area_dbc": Quantity(_db_power(area), "dBc", label="Integrated single-sideband noise"),
                   "sigma_rad": Quantity(sigma, "rad", label="RMS phase deviation"),
                   "jitter_s": Quantity(jitter_s, "s", label="Integrated RMS jitter")}, verdict, reason,
                  refs=(MT008, "SiTime AN10007 Rev 1.21, p.9 to 10, equations 3 to 4", BANERJEE),
                  assumptions=("SSB phase noise excludes discrete spurs and AM noise", "no extrapolation outside either table",
                               "mask values are 20 log10 of transfer magnitude; their power weighting is 10^(mask/10)"),
                  plots=(plot,), summary=f"Integrated noise from {fmt(f1_hz, 'Hz')} to {fmt(f2_hz, 'Hz')} is "
                  f"{fmt(_db_power(area), 'dBc')}, giving {fmt(jitter_s, 's')} RMS jitter at {fmt(f0_hz, 'Hz')}. "
                  + limit_text, key=(Key("area_dbc"), Key("jitter_s", f"at most {fmt(limit_s, 's')}" if limit_s is not None
                                                                  else "set the consumer's jitter limit"))).in_context(context)


def rss(terms_s: Sequence[float], limit_s: float | None = None, *, marginal_limit_s: float | None = None,
        context: str = "nominal") -> Result:
    """Root-sum-square independent RMS jitter contributions measured over the same offset band."""
    terms = tuple(terms_s)
    if not terms:
        raise ValueError("at least one jitter contribution is required")
    for term in terms:
        _nonnegative(term_s=term)
    if limit_s is not None:
        _nonnegative(limit_s=limit_s)
    total_s = math.hypot(*terms)
    inputs = {f"term{i}_s": Quantity(term, "s", label=f"RMS jitter contribution {i}")
              for i, term in enumerate(terms, 1)}
    verdict, reason, text = _limit(total_s, "s", "RMS jitter", limit_s, inputs, marginal_limit_s)
    return Result("Combined RMS jitter", "total = sqrt(sum(term^2))", inputs,
                  {"total_s": Quantity(total_s, "s", label="Total RMS jitter")}, verdict, reason,
                  refs=("ADI Analog Dialogue 42-02, February 2008, p.4", "Skyworks AN766 Rev 0.1, September 23 2021, p.2"),
                  assumptions=("independent contributions with the same integration band and jitter definition",
                               "correlated spurs require phase-aware summation, not RSS"),
                  summary=f"The {fmt(len(terms), 'count')} independent contributions total {fmt(total_s, 's')} RMS jitter. "
                          + text, key=(Key("total_s"),)).in_context(context)


def multiply(dbc_hz: float, n: float, *, limit_db: float | None = None, context: str = "nominal") -> Result:
    """Ideal phase-noise change for an output-to-input frequency ratio, including division."""
    _finite(dbc_hz=dbc_hz)
    _positive(n=n)
    change = 20 * math.log10(n)
    output = dbc_hz + change
    inputs = {"dbc_hz": Quantity(dbc_hz, "dBc/Hz", label="Input phase noise"),
              "n": Quantity(n, "", "output frequency divided by input frequency", "Frequency ratio")}
    verdict, reason, text = _limit(output, "dBc/Hz", "Phase noise", limit_db, inputs)
    return Result("Phase noise through frequency scaling", "Lout = Lin + 20 log10(N)", inputs,
                  {"dbc_hz": Quantity(output, "dBc/Hz", label="Output phase noise"),
                   "change_db": Quantity(change, "dB", label="Phase noise change")}, verdict, reason,
                  refs=(BANERJEE,), assumptions=("ideal frequency scaling at the same absolute offset frequency",
                                               "no additive device noise or PLL filtering included"),
                  summary=f"A frequency ratio of {fmt(n)} changes phase noise by {fmt(change, 'dB')} to "
                          f"{fmt(output, 'dBc/Hz')}. " + text,
                  key=(Key("change_db"), Key("dbc_hz"))).in_context(context)


def spur_to_jitter(spur_dbc: float, f0_hz: float, *, limit_s: float | None = None,
                   context: str = "nominal") -> Result:
    """RMS timing deviation of a small symmetric PM spur pair specified by either sideband."""
    _finite(spur_dbc=spur_dbc)
    _positive(f0_hz=f0_hz)
    if spur_dbc >= 0:
        raise ValueError("a small PM sideband must be below the carrier")
    if limit_s is not None:
        _nonnegative(limit_s=limit_s)
    jitter_s = 10 ** (spur_dbc / 20) / (math.sqrt(2) * math.pi * f0_hz)
    inputs = {"spur_dbc": Quantity(spur_dbc, "dBc", "one side of a symmetric PM pair", "Clock sideband level"),
              "f0_hz": Quantity(f0_hz, "Hz", label="Clock carrier frequency")}
    verdict, reason, text = _limit(jitter_s, "s", "RMS jitter", limit_s, inputs)
    return Result("Clock spur equivalent jitter", "beta = 2*10^(spur/20); jitter = beta/(sqrt(2)*2*pi*f0)", inputs,
                  {"jitter_s": Quantity(jitter_s, "s", label="Spur pair RMS timing deviation")}, verdict, reason,
                  refs=(AN491,), assumptions=("small-angle sinusoidal phase modulation with symmetric sidebands",
                                             "the given level is per sideband, not their summed power",
                                             "AM spurs do not imply timing jitter"),
                  summary=f"A {fmt(spur_dbc, 'dBc')} PM sideband at {fmt(f0_hz, 'Hz')} represents "
                          f"{fmt(jitter_s, 's')} RMS timing deviation from the symmetric pair. " + text,
                  key=(Key("jitter_s"),)).in_context(context)


def spur_transfer(spur_dbc: float, f_in_hz: float, f_clk_hz: float, *, limit_db: float | None = None,
                  context: str = "nominal") -> Result:
    """Transfer a small clock PM sideband to the converter output for a sinusoidal analog input."""
    _finite(spur_dbc=spur_dbc)
    _positive(f_in_hz=f_in_hz, f_clk_hz=f_clk_hz)
    output = spur_dbc + 20 * math.log10(f_in_hz / f_clk_hz)
    inputs = {"spur_dbc": Quantity(spur_dbc, "dBc", label="Clock phase sideband"),
              "f_in_hz": Quantity(f_in_hz, "Hz", label="Analog input frequency"),
              "f_clk_hz": Quantity(f_clk_hz, "Hz", label="Sample clock frequency")}
    verdict, reason, text = _limit(output, "dBc", "Converter spur", limit_db, inputs)
    return Result("Clock spur at converter output", "spur_out = spur_clk + 20 log10(f_in/f_clk)", inputs,
                  {"spur_out_dbc": Quantity(output, "dBc", "relative to the analog input tone", "Converter sideband")},
                  verdict, reason, refs=(AN756,), assumptions=("small-angle clock phase modulation",
                                                             "use analog input frequency before alias folding"),
                  summary=f"The {fmt(spur_dbc, 'dBc')} clock sideband becomes {fmt(output, 'dBc')} relative to the "
                          f"{fmt(f_in_hz, 'Hz')} input tone with a {fmt(f_clk_hz, 'Hz')} sample clock. " + text,
                  key=(Key("spur_out_dbc"),)).in_context(context)


def ripple_sideband(k_push_hz_per_v: float, v_pk_v: float, f_m_hz: float, *, limit_db: float | None = None,
                    loop_bandwidth_hz: float | None = None, context: str = "nominal") -> Result:
    """Supply or tuning ripple FM sideband, with an exact Bessel ratio for the modulation index."""
    _finite(k_push_hz_per_v=k_push_hz_per_v)
    _nonnegative(v_pk_v=v_pk_v)
    _positive(f_m_hz=f_m_hz)
    beta = abs(k_push_hz_per_v) * v_pk_v / f_m_hz
    carrier, side = abs(float(jv(0, beta))), abs(float(jv(1, beta)))
    sideband = _db_power(side / carrier, 20) if carrier else math.inf
    approx = _db_power(beta / 2, 20)
    inputs = {"k_push_hz_per_v": Quantity(k_push_hz_per_v, "Hz/V", label="Frequency pushing or tuning sensitivity"),
              "v_pk_v": Quantity(v_pk_v, "V", label="Ripple peak amplitude"),
              "f_m_hz": Quantity(f_m_hz, "Hz", label="Ripple modulation frequency")}
    verdict, reason, text = _limit(sideband, "dBc", "Sideband", limit_db, inputs)
    if loop_bandwidth_hz is not None:
        _positive(loop_bandwidth_hz=loop_bandwidth_hz)
        inputs["loop_bandwidth_hz"] = Quantity(loop_bandwidth_hz, "Hz", label="PLL loop bandwidth")
        if f_m_hz <= loop_bandwidth_hz:
            verdict = Verdict.UNKNOWN
            reason = "ripple is within the loop bandwidth; supply-to-phase transfer is needed"
            text = "The ripple is within the PLL bandwidth; its measured or modeled supply-to-phase transfer is needed."
    return Result("Ripple-induced FM sideband", "beta = abs(Kpush)*Vpk/fm; sideband = 20 log10(abs(J1(beta)/J0(beta))); "
                  "small-angle sideband = 20 log10(beta/2)", inputs,
                  {"beta": Quantity(beta, "rad", label="Peak modulation index"),
                   "sideband_dbc": Quantity(sideband, "dBc", label="First FM sideband"),
                   "small_angle_dbc": Quantity(approx, "dBc", label="Small-angle sideband estimate")}, verdict, reason,
                  refs=("DERIVED from sinusoidal FM; ADI Analog Dialogue 45-09, September 2011, p.1 to 2",
                        "ADI Power Supply Modulation Ratio Demystified, 2018, p.1 to 2"),
                  assumptions=("sinusoidal ripple and constant frequency sensitivity", "peak voltage, not RMS or peak-to-peak",
                               "free-running oscillator or ripple outside PLL bandwidth; otherwise supply-to-phase transfer is needed",
                               "exact first sideband uses Bessel functions; large modulation also creates higher sidebands"),
                  summary=f"Ripple at {fmt(f_m_hz, 'Hz')} gives a {fmt(beta, 'rad')} peak modulation index and "
                          f"{_value_text(sideband, 'dBc')} in the first sideband. " + text,
                  key=(Key("beta"),) + ((Key("sideband_dbc"),) if math.isfinite(sideband) else ())).in_context(context)


def vc_noise(f0_hz: float, kv_per_v: float, vn_v_rthz: float, fm_hz: float, *,
             limit_db: float | None = None, context: str = "nominal") -> Result:
    """Control-voltage noise as phase PSD and SSB phase noise under a one-sided voltage PSD convention."""
    _positive(f0_hz=f0_hz, fm_hz=fm_hz)
    _finite(kv_per_v=kv_per_v)
    _nonnegative(vn_v_rthz=vn_v_rthz)
    phase_asd = f0_hz * abs(kv_per_v) * vn_v_rthz / fm_hz
    phase_db = _db_power(phase_asd, 20)
    ssb_db = phase_db - 10 * math.log10(2)
    inputs = {"f0_hz": Quantity(f0_hz, "Hz", label="VCXO carrier frequency"),
              "kv_per_v": Quantity(kv_per_v, "1/V", "fractional sensitivity; multiply ppm/V by 1e-6", "Fractional tuning sensitivity"),
              "vn_v_rthz": Quantity(vn_v_rthz, "V/sqrt(Hz)", "one-sided amplitude density at the control pin", "Control voltage noise"),
              "fm_hz": Quantity(fm_hz, "Hz", label="Offset frequency")}
    verdict, reason, text = _limit(ssb_db, "dBc/Hz", "SSB phase noise", limit_db, inputs)
    return Result("VCXO control noise contribution", "Sphi = (f0 Kv vn/fm)^2; phase PSD = 10 log10(Sphi); "
                  "SSB L = 10 log10(Sphi/2)", inputs,
                  {"s_phi_dbc_hz": Quantity(phase_db, "dB(rad^2/Hz)", "plan W9 phase PSD convention, not SSB L", "Phase noise power density"),
                   "ssb_dbc_hz": Quantity(ssb_db, "dBc/Hz", label="Single-sideband phase noise")}, verdict, reason,
                  refs=("WENZEL-VCXO, Wenzel Associates VCXOs tutorial, undated, noise formula (page not given in plan)", MT008),
                  assumptions=("one-sided voltage noise PSD; SSB phase noise is half the phase PSD",
                               "W9 calls phase PSD dBc/Hz; the separate SSB output avoids the 3.01 dB convention ambiguity",
                               "UNSURE whether WENZEL-VCXO uses one-sided voltage noise; verify that convention in the source",
                               "control sensitivity is linear at the operating point; noise is specified after filtering"),
                  summary=f"At {fmt(fm_hz, 'Hz')} offset the control noise gives {_value_text(phase_db, 'dB(rad^2/Hz)')} "
                          f"phase density, or {_value_text(ssb_db, 'dBc/Hz')} SSB phase noise. " + text,
                  key=(Key("ssb_dbc_hz"), Key("s_phi_dbc_hz")) if phase_asd else (Key("fm_hz"),)).in_context(context)


def ssc_emi(spread_frac: float, f_c_hz: float, rbw_hz: float, *, min_reduction_db: float | None = None,
            context: str = "nominal") -> Result:
    """Approximate spread-spectrum peak reduction from total occupied span and measurement RBW."""
    _nonnegative(spread_frac=spread_frac)
    _positive(f_c_hz=f_c_hz, rbw_hz=rbw_hz)
    if spread_frac >= 1:
        raise ValueError("fractional frequency span must be less than one")
    span = spread_frac * f_c_hz
    reduction = max(0.0, _db_power(span / rbw_hz))
    inputs = {"spread_frac": Quantity(spread_frac, "", "full span / carrier; for +/-1% use 0.02", "Total fractional spread"),
              "f_c_hz": Quantity(f_c_hz, "Hz", label="Clock carrier frequency"),
              "rbw_hz": Quantity(rbw_hz, "Hz", label="Measurement resolution bandwidth")}
    verdict, reason, text = _limit(reduction, "dB", "Peak reduction", min_reduction_db, inputs, minimum=True)
    return Result("Spread-spectrum peak reduction estimate", "span = spread_frac*f_c; reduction = max(0, 10 log10(span/RBW))",
                  inputs, {"span_hz": Quantity(span, "Hz", label="Full spread bandwidth"),
                           "reduction_db": Quantity(reduction, "dB", label="Estimated peak reduction")}, verdict, reason,
                  refs=("SiTime AN10005 Rev 1.2, p.5 and p.7",),
                  assumptions=("approximate uniform energy over the full spread; detector and modulation shape affect the measured peak",
                               "does not check receiver SSC compatibility or downstream PLL tracking",
                               "a span inside one RBW gives no resolved peak reduction"),
                  summary=f"The full spread is {fmt(span, 'Hz')} against {fmt(rbw_hz, 'Hz')} RBW, giving about "
                          f"{fmt(reduction, 'dB')} peak reduction. " + text,
                  key=(Key("span_hz"), Key("reduction_db"))).in_context(context)
