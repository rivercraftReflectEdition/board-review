"""SAR input settling, JESD payload rates and SYSREF alignment frequencies."""

from __future__ import annotations

import math

import numpy as np

from boardreview.calc.base import Key, Marker, Quantity, Result, Verdict, fmt, plot_from_arrays


def _positive(**values) -> None:
    for name, value in values.items():
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")


def _integer(**values) -> None:
    _positive(**values)
    for name, value in values.items():
        if isinstance(value, bool) or int(value) != value:
            raise ValueError(f"{name} must be a positive integer")


def sar_rc(
    n_bits: int,
    v_ref_v: float,
    t_acq_s: float,
    c_ext_f: float,
    *,
    r_ohm: float | None = None,
    t_conv_s: float | None = None,
    c_dac_f: float | None = None,
    f_hz: float | None = None,
    v_pk_v: float | None = None,
    c_ratio_min: float | None = None,
    context: str = "nominal",
) -> Result:
    """Bound a single input RC for half-LSB settling, using a full-scale or sine kickback step."""
    _integer(n_bits=n_bits)
    _positive(v_ref_v=v_ref_v, t_acq_s=t_acq_s, c_ext_f=c_ext_f)
    optional = {"r_ohm": r_ohm, "t_conv_s": t_conv_s, "c_dac_f": c_dac_f,
                "f_hz": f_hz, "v_pk_v": v_pk_v, "c_ratio_min": c_ratio_min}
    _positive(**{k: v for k, v in optional.items() if v is not None})
    dynamic = any(v is not None for v in (t_conv_s, f_hz, v_pk_v))
    if dynamic and any(v is None for v in (t_conv_s, c_dac_f, f_hz, v_pk_v)):
        raise ValueError("sine kickback needs t_conv_s, c_dac_f, f_hz and v_pk_v together")
    if c_ratio_min is not None and c_dac_f is None:
        raise ValueError("c_ratio_min needs c_dac_f")
    half_lsb = v_ref_v * math.exp(-(n_bits + 1) * math.log(2))
    if half_lsb == 0:
        raise ValueError("half LSB is below the numeric range")
    step = (2 * math.pi * f_hz * v_pk_v * t_conv_s * c_dac_f / (c_ext_f + c_dac_f)
            if dynamic else v_ref_v)
    _positive(step_v=step)
    cycles = max(0.0, (n_bits + 1) * math.log(2) + math.log(step / v_ref_v))
    tau = t_acq_s / cycles if cycles > 0 else math.inf
    r_max, bw = tau / c_ext_f, 1 / (2 * math.pi * tau)
    inputs = {
        "n_bits": Quantity(n_bits, "bit", label="Converter resolution"),
        "v_ref_v": Quantity(v_ref_v, "V", label="Reference voltage"),
        "t_acq_s": Quantity(t_acq_s, "s", label="Acquisition time available"),
        "c_ext_f": Quantity(c_ext_f, "F", label="External filter capacitance"),
    }
    labels = {"r_ohm": ("ohm", "Total fitted drive resistance"), "t_conv_s": ("s", "Conversion time"),
              "c_dac_f": ("F", "Sampling DAC capacitance"), "f_hz": ("Hz", "Analog input frequency"),
              "v_pk_v": ("V", "Analog input peak voltage"), "c_ratio_min": ("", "Minimum capacitance ratio")}
    inputs.update({k: Quantity(v, labels[k][0], label=labels[k][1])
                   for k, v in optional.items() if v is not None})
    outputs = {
        "step_v": Quantity(step, "V", label="Initial settling step"),
        "half_lsb_v": Quantity(half_lsb, "V", label="Half LSB error limit"),
        "time_constants": Quantity(cycles, "", label="Time constants needed"),
        "tau_s": Quantity(tau, "s", label="Maximum RC time constant"),
        "r_max_ohm": Quantity(r_max, "ohm", label="Maximum total drive resistance"),
        "bw_hz": Quantity(bw, "Hz", label="Minimum RC bandwidth"),
    }
    verdict = Verdict.INFO
    reason = "fitted drive resistance needed to check settling"
    summary = (f"A {fmt(step, 'V')} step needs an RC time constant at most {fmt(tau, 's')}, "
               f"or at least {fmt(bw, 'Hz')} bandwidth, to settle in {fmt(t_acq_s, 's')}. "
               f"With {fmt(c_ext_f, 'F')}, the total resistance can be at most {fmt(r_max, 'ohm')}.")
    if cycles == 0:
        summary = (f"The {fmt(step, 'V')} initial step is already within the {fmt(half_lsb, 'V')} half-LSB limit. "
                   "Settling imposes no finite resistance limit; the minimum settling bandwidth is 0 Hz.")
    if r_ohm is not None:
        actual_tau = r_ohm * c_ext_f
        residual = step * math.exp(-t_acq_s / actual_tau)
        outputs["residual_v"] = Quantity(residual, "V", label="Error after acquisition")
        outputs["settling_s"] = Quantity(cycles * actual_tau, "s", label="Settling time needed")
        verdict = Verdict.PASS if r_ohm <= math.nextafter(r_max, math.inf) else Verdict.FAIL
        reason = f"total resistance {fmt(r_ohm, 'ohm')} against {fmt(r_max, 'ohm')} maximum"
        summary += (f" The fitted {fmt(r_ohm, 'ohm')} leaves {fmt(residual, 'V')} error against "
                    f"{fmt(half_lsb, 'V')}; settling is "
                    + ("within the acquisition time." if verdict is Verdict.PASS else "outside the acquisition time."))
    else:
        summary += " Supply the fitted total resistance to compare with this limit from the resolution and acquisition requirement."
    if c_dac_f is not None:
        ratio = c_ext_f / c_dac_f
        outputs["c_ratio"] = Quantity(ratio, "", label="External to sampling capacitance ratio")
        if c_ratio_min is not None:
            summary += f" The capacitance ratio is {fmt(ratio)} against a minimum of {fmt(c_ratio_min)}."
            if ratio < c_ratio_min:
                verdict, reason = Verdict.FAIL, "capacitance ratio below the supplied minimum"
        else:
            summary += " No capacitance ratio limit was supplied; take it from the driver or ADC datasheet."
    curve_tau = r_ohm * c_ext_f if r_ohm is not None else tau
    times = np.linspace(0, t_acq_s, 201)
    errors = step * np.exp(-times / curve_tau)
    plot = plot_from_arrays(
        "Input settling during acquisition", "Time after acquisition starts", "s", times,
        [("Remaining error", "V", errors)],
        markers=(Marker("Half LSB", y=half_lsb, unit="V"), Marker("Acquisition ends", x=t_acq_s)),
        caption=f"Remaining error after {fmt(t_acq_s, 's')}; half LSB is {fmt(half_lsb, 'V')}.",
    )
    return Result(
        "SAR input RC settling",
        "Vstep = Vref, or 2 pi f Vpk tconv Cdac/(Cext + Cdac); Vhalf = Vref/2^(N+1); "
        "NTC = max(0, ln(Vstep/Vhalf)); tau = tacq/NTC; Rmax = tau/Cext; BW = 1/(2 pi tau)",
        inputs, outputs, verdict, reason,
        refs=("AD46, Analog Dialogue 46-12, 2012-12, p.1 to 4",
              "ADS8910B, SBAS707B, 2018-01, p.57 to 58"),
        assumptions=("single-pole linear settling; amplifier settling, distortion and noise need separate checks",
                     "R includes driver output resistance; the RC pole uses the external capacitance",
                     "sine kickback is a slope estimate, not a bound for arbitrary channel switching" if dynamic
                     else "full-reference step, suitable for a conservative unipolar full-scale transition"),
        plots=(plot,), summary=summary,
        key=(Key("half_lsb_v", "error no greater than this"),) if cycles == 0 else
            (Key("tau_s", "RC no greater than this"), Key("r_max_ohm", "resistance no greater than this"),
             Key("bw_hz", "bandwidth at least this")),
    ).in_context(context)


def jesd_lane_rate(
    m: int,
    np: int,
    fs_hz: float,
    l: int,
    encoding: str,
    *,
    lane_max_bps: float | None = None,
    lane_min_bps: float | None = None,
    context: str = "nominal",
) -> Result:
    """Compute encoded bits per second per lane against explicitly supplied interface bounds."""
    _integer(m=m, np=np, l=l)
    _positive(fs_hz=fs_hz)
    ratios = {"8b/10b": 10 / 8, "64b/66b": 66 / 64}
    if encoding not in ratios:
        raise ValueError("encoding must be 8b/10b or 64b/66b")
    _positive(**{k: v for k, v in {"lane_max_bps": lane_max_bps, "lane_min_bps": lane_min_bps}.items()
                 if v is not None})
    if lane_max_bps is not None and lane_min_bps is not None and lane_min_bps > lane_max_bps:
        raise ValueError("lane_min_bps must not exceed lane_max_bps")
    rate = m * np * fs_hz * ratios[encoding] / l
    _positive(lane_bps=rate)
    inputs = {"m": Quantity(m, "count", label="Virtual converters per link"),
              "np": Quantity(np, "bit", label="Transport bits per sample"),
              "fs_hz": Quantity(fs_hz, "Hz", label="Transport sample rate per converter"),
              "l": Quantity(l, "count", label="Lanes per link"),
              "encoding_ratio": Quantity(ratios[encoding], "", encoding, "Line encoding overhead")}
    outputs = {"lane_bps": Quantity(rate, "bit/s", label="Encoded rate per lane")}
    verdict, reason = Verdict.INFO, "interface maximum needed from both endpoint datasheets"
    summary = f"The {encoding} link needs {fmt(rate, 'bit/s')} on each of {fmt(l, 'count')} lanes."
    if lane_min_bps is not None:
        inputs["lane_min_bps"] = Quantity(lane_min_bps, "bit/s", label="Minimum interface lane rate")
        summary += f" The supplied minimum is {fmt(lane_min_bps, 'bit/s')}."
    if lane_max_bps is not None:
        inputs["lane_max_bps"] = Quantity(lane_max_bps, "bit/s", label="Maximum interface lane rate")
        summary += f" The supplied maximum is {fmt(lane_max_bps, 'bit/s')}."
        verdict, reason = Verdict.PASS, "lane rate within the supplied bounds"
    if (lane_max_bps is not None and rate > lane_max_bps) or (lane_min_bps is not None and rate < lane_min_bps):
        verdict, reason = Verdict.FAIL, "lane rate outside the supplied interface bounds"
        summary += " This rate is outside the interface range; change the transport mode or lane count."
    elif lane_max_bps is None:
        summary += " Supply the smaller endpoint maximum from the datasheets or the interface requirement before judging the rate."
    else:
        summary += " This rate is inside the supplied range; signal integrity and supported transport modes still need checks."
    return Result(
        "JESD lane rate", "lane rate = M Nprime fs (encoded bits / payload bits) / L", inputs, outputs, verdict, reason,
        refs=("AD9680 Rev E, 2019-03, p.73", "UG-1578 Rev 0, 2021-07, p.58",
              "SBAA402A, 2021-04, p.3 to 4"),
        assumptions=("use virtual converter count and sample rate after decimation or before interpolation, as the mode defines",
                     "supplied bounds combine both endpoints and the selected JESD revision; encoding alone sets no maximum"),
        summary=summary, key=(Key("lane_bps", "inside both endpoint limits"),),
    ).in_context(context)


def sysref(
    lane_bps: float,
    f: int | None = None,
    k: int | None = None,
    f_sysref_hz: float | None = None,
    *,
    encoding: str = "8b/10b",
    e: int | None = None,
    dividers: tuple[int, ...] = (1, 2, 3, 4),
    context: str = "nominal",
) -> Result:
    """List SYSREF submultiples and check alignment with a JESD204B LMFC or JESD204C LEMC."""
    _positive(lane_bps=lane_bps)
    inputs = {"lane_bps": Quantity(lane_bps, "bit/s", label="Encoded rate per lane")}
    if encoding == "8b/10b":
        if f is None or k is None or e is not None:
            raise ValueError("8b/10b needs F and K, with no E")
        _integer(f=f, k=k)
        alignment = lane_bps / (10 * f * k)
        inputs.update(f=Quantity(f, "count", label="Octets per frame per lane"),
                      k=Quantity(k, "count", label="Frames per multiframe"))
        counter, formula = "LMFC", "alignment = lane rate/(10 F K); allowed SYSREF = alignment/n, integer n >= 1"
    elif encoding == "64b/66b":
        if e is None or f is not None or k is not None:
            raise ValueError("64b/66b needs E, with no F or K")
        _integer(e=e)
        alignment = lane_bps / (2112 * e)
        inputs["e"] = Quantity(e, "count", label="Multiblocks per extended multiblock")
        counter, formula = "LEMC", "alignment = lane rate/(2112 E); allowed SYSREF = alignment/n, integer n >= 1"
    else:
        raise ValueError("encoding must be 8b/10b or 64b/66b")
    _positive(alignment_hz=alignment)
    for divider in dividers:
        _integer(divider=divider)
    outputs = {"alignment_hz": Quantity(alignment, "Hz", counter, "Alignment counter frequency")}
    for divider in dict.fromkeys(dividers):
        inputs[f"display_divider_{divider}"] = Quantity(divider, "count", label=f"Listed SYSREF divider {divider}")
        outputs[f"allowed_{divider}_hz"] = Quantity(alignment / divider, "Hz", label=f"Allowed SYSREF at divider {divider}")
    summary = (f"The {counter} runs at {fmt(alignment, 'Hz')}; allowed periodic SYSREF frequencies are this rate "
               "divided by a positive integer.")
    verdict, reason = Verdict.INFO, "requested SYSREF frequency needed from the synchronization requirement"
    key = [Key("alignment_hz", "SYSREF divides this by a positive integer")]
    if f_sysref_hz is not None:
        _positive(f_sysref_hz=f_sysref_hz)
        inputs["f_sysref_hz"] = Quantity(f_sysref_hz, "Hz", label="Requested SYSREF frequency")
        n = alignment / f_sysref_hz
        _positive(divider_ratio=n)
        nearest = round(n)
        allowed = nearest >= 1 and abs(n - nearest) <= 32 * math.ulp(n)
        outputs["n"] = Quantity(n, "", label="Alignment to SYSREF frequency ratio")
        verdict = Verdict.PASS if allowed else Verdict.FAIL
        reason = "integer SYSREF submultiple" if allowed else "SYSREF is not a positive integer submultiple"
        ratio_text = fmt(n) if allowed else f"{fmt(n)} (more precisely {fmt(n, digits=15)})"
        summary += (f" At {fmt(f_sysref_hz, 'Hz')}, the divider is {ratio_text}, "
                    + ("so the frequency is allowed." if allowed else "so the frequency is outside the allowed family."))
        key.append(Key("n", "positive integer"))
    else:
        summary += " Supply the requested frequency from the synchronization requirement to check membership."
    summary += " Coupling, device divider restrictions, setup and hold still need datasheet checks."
    return Result(
        "SYSREF frequency alignment", formula, inputs, outputs, verdict, reason,
        refs=("SLYT628, AAJ 2Q 2015, p.16 eq.1", "UG-1578 Rev 0, 2021-07, p.27 to 28"),
        assumptions=("frequency ratio only; numerical equality allows 32 floating-point ULPs, not clock tolerance",
                     "listed dividers are examples, not a finite allowed set",
                     "64b/66b uses E from the selected JESD204C mode" if encoding == "64b/66b"
                     else "F and K come from the selected JESD204B mode"),
        summary=summary, key=tuple(key),
    ).in_context(context)
