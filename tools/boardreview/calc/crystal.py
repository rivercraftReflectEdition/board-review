"""Pierce crystal oscillator: load capacitance, pulling, oscillation margin and drive level."""

from __future__ import annotations

import math

import numpy as np

from boardreview.calc.base import Key, Marker, Quantity, Result, Verdict, fmt, plot_from_arrays

AN2867 = "ST AN2867 Rev 24 (February 2026), Guidelines for oscillator design on STM8AF/AL/S and STM32 MCUs/MPUs"
AN2867_CL = f"{AN2867} sec. 3.3 p. 12 (CL = CL1*CL2/(CL1 + CL2) + Cs)"
AN2867_GM = (
    f"{AN2867} sec. 3.4 pp. 13 to 14 (gmcrit = 4*ESR*(2*pi*F)^2*(C0 + CL)^2; gainmargin = gm/gmcrit > 5; "
    "or gmcrit below Gm_crit_max)"
)
AN2867_DL = (
    f"{AN2867} sec. 3.5.1 pp. 14 to 15 (DL = ESR*IQ^2) and sec. 3.5.2 p. 16 "
    "(IQ = 2*pi*F*Vrms*Ctot, Vrms = Vpp/(2*sqrt(2)), Ctot = CL1 + Cs/2 + Cprobe)"
)
STM32N6_HSE = "ST DS14791 Rev 9 (STM32N6x5xx/x7xx) p. 160 Table 49, HSE Gmcritmax 1.95 mA/V"


def load_capacitance(
    c1_f: float,
    c2_f: float,
    c_stray_f: float,
    cl_spec_f: float | None = None,
    c0_f: float | None = None,
    c_motional_f: float | None = None,
    tol_frac: float = 0.10,
) -> Result:
    """Load seen by the crystal from the two Pierce capacitors plus stray, against the crystal's CL."""
    cl = c1_f * c2_f / (c1_f + c2_f) + c_stray_f
    outputs = {"cl": Quantity(cl, "F", label="Load capacitance")}
    inputs = {"c1": Quantity(c1_f, "F", label="First load capacitor"),
              "c2": Quantity(c2_f, "F", label="Second load capacitor"),
              "c_stray": Quantity(c_stray_f, "F", label="Stray capacitance")}
    head = (f"The {fmt(c1_f, 'F')} and {fmt(c2_f, 'F')} capacitors in series plus {fmt(c_stray_f, 'F')} of stray "
            f"give the crystal a load of {fmt(cl, 'F')}.")
    key: tuple[Key, ...] = (Key("cl"),)
    if cl_spec_f is None:
        verdict, reason = Verdict.INFO, ""
        summary = f"{head} No load capacitance spec was given to compare with."
    else:
        inputs["cl_spec"] = Quantity(cl_spec_f, "F", label="Crystal's specified load")
        inputs["tol"] = Quantity(tol_frac, "", "allowed CL error", label="Allowed load error")
        err = (cl - cl_spec_f) / cl_spec_f
        outputs["cl_error"] = Quantity(err, "", "relative to CL spec", label="Load error")
        pull = ""
        if c0_f is not None and c_motional_f is not None:
            ppm = 1e6 * c_motional_f / 2.0 * (1.0 / (c0_f + cl) - 1.0 / (c0_f + cl_spec_f))
            outputs["pulling"] = Quantity(ppm, "ppm", "positive means above nominal frequency",
                                          label="Frequency pulling")
            inputs["c0"] = Quantity(c0_f, "F", label="Shunt capacitance")
            inputs["c_motional"] = Quantity(c_motional_f, "F", label="Motional capacitance")
            pull = f" That pulls the frequency by {fmt(ppm, 'ppm')}."
        band = f"{fmt(cl_spec_f * (1 - tol_frac), 'F')} to {fmt(cl_spec_f * (1 + tol_frac), 'F')}"
        key = (Key("cl", band),) + ((Key("pulling"),) if pull else ())
        off, allowed = fmt(100.0 * abs(err), "%"), fmt(100.0 * tol_frac, "%")
        if abs(err) > tol_frac:
            verdict, reason = Verdict.FAIL, f"CL {cl * 1e12:.2f} pF is {err:+.0%} from the {cl_spec_f * 1e12:g} pF spec"
            summary = (f"{head} The crystal is specified at {fmt(cl_spec_f, 'F')}; this is {off} off, more than the "
                       f"{allowed} we allow, so it runs off frequency.{pull}")
        else:
            verdict, reason = Verdict.PASS, f"CL {cl * 1e12:.2f} pF within {tol_frac:.0%} of {cl_spec_f * 1e12:g} pF"
            summary = (f"{head} The crystal is specified at {fmt(cl_spec_f, 'F')}; this is within {allowed} of it, so "
                       f"it runs close to its nominal frequency.{pull}")
    return Result(
        name="crystal load capacitance",
        formula="CL = C1*C2/(C1 + C2) + Cstray; pulling = C1m/2*(1/(C0 + CL) - 1/(C0 + CLspec))",
        inputs=inputs,
        outputs=outputs,
        verdict=verdict,
        reason=reason,
        refs=("series combination of C1 and C2 through ground, plus pin and trace stray", AN2867_CL),
        assumptions=("Cstray includes both oscillator pins and the traces; 2 to 5 pF is typical, measure if it matters",),
        summary=summary,
        key=key,
    )


def oscillation_margin(
    esr_ohm: float,
    f_hz: float,
    c0_f: float,
    cl_f: float,
    gm_a_per_v: float | None = None,
    gm_crit_max_a_per_v: float | None = None,
    min_gain_margin: float = 5.0,
    refs: tuple[str, ...] = (),
) -> Result:
    """Critical transconductance of the crystal against the oscillator gm or the MCU's Gmcritmax."""
    gm_crit = 4.0 * esr_ohm * (2.0 * math.pi * f_hz) ** 2 * (c0_f + cl_f) ** 2
    outputs = {"gm_crit": Quantity(gm_crit, "A/V", label="Transconductance the crystal needs")}
    inputs = {
        "esr": Quantity(esr_ohm, "ohm", "use the max ESR", label="Crystal ESR, maximum"),
        "f": Quantity(f_hz, "Hz", label="Crystal frequency"),
        "c0": Quantity(c0_f, "F", label="Shunt capacitance"),
        "cl": Quantity(cl_f, "F", label="Load capacitance"),
    }
    need = (f"With {fmt(esr_ohm, 'ohm')} ESR at {fmt(f_hz, 'Hz')} and a {fmt(cl_f, 'F')} load, the crystal needs "
            f"{fmt(gm_crit, 'A/V')} of transconductance to start.")
    verdict, reason = Verdict.UNKNOWN, "give the oscillator gm or the MCU Gmcritmax"
    summary = f"{need} Without the oscillator gm or the MCU's Gmcritmax there is nothing to compare it with."
    key: tuple[Key, ...] = (Key("gm_crit"),)
    if gm_crit_max_a_per_v is not None:
        inputs["gm_crit_max"] = Quantity(gm_crit_max_a_per_v, "A/V", label="MCU Gmcritmax")
        ratio = gm_crit_max_a_per_v / gm_crit
        outputs["gm_crit_max_over_gm_crit"] = Quantity(ratio, "", label="Gmcritmax over the needed transconductance")
        mx = fmt(gm_crit_max_a_per_v, "A/V")
        key = (Key("gm_crit", f"{fmt(gm_crit_max_a_per_v / 1.25, 'A/V')} or less"),)
        if gm_crit > gm_crit_max_a_per_v:
            verdict = Verdict.FAIL
            reason = (f"crystal gm_crit {gm_crit * 1e3:.3g} mA/V above Gmcritmax "
                      f"{gm_crit_max_a_per_v * 1e3:.3g} mA/V")
            summary = (f"{need} That is above the {mx} Gmcritmax the MCU allows, so the oscillator may not start, "
                       "or start slowly, on some parts and at cold.")
        elif ratio < 1.25:
            verdict, reason = Verdict.MARGINAL, f"gm_crit within 20 % of Gmcritmax ({ratio:.2f}x)"
            summary = (f"{need} That is within 20% of the {mx} Gmcritmax the MCU allows, so start-up has little "
                       "margin; check it at cold.")
        else:
            verdict, reason = Verdict.PASS, f"Gmcritmax is {ratio:.2f}x the crystal gm_crit"
            summary = f"{need} The MCU allows up to {mx}, {fmt(ratio)} times more, so the oscillator starts reliably."
    if gm_a_per_v is not None:
        inputs["gm"] = Quantity(gm_a_per_v, "A/V", label="Oscillator transconductance")
        inputs["min_gain_margin"] = Quantity(min_gain_margin, "", label="Minimum gain margin")
        margin = gm_a_per_v / gm_crit
        outputs["gain_margin"] = Quantity(margin, "", label="Gain margin")
        gm_text = f"The oscillator's {fmt(gm_a_per_v, 'A/V')} is {fmt(margin)} times what the crystal needs"
        if margin < min_gain_margin:
            verdict, reason = Verdict.FAIL, f"gain margin {margin:.2f} under {min_gain_margin:g}"
            summary = (f"{need} {gm_text}, under the {fmt(min_gain_margin)} times we want, so it may not start at "
                       "cold or with an aged crystal.")
            key = (Key("gain_margin", f"{fmt(min_gain_margin)} or more"), Key("gm_crit"))
        elif verdict is not Verdict.FAIL:
            verdict, reason = Verdict.PASS, f"gain margin {margin:.2f}"
            summary = f"{need} {gm_text}, at least the {fmt(min_gain_margin)} times we want, so it starts reliably."
            key = (Key("gain_margin", f"{fmt(min_gain_margin)} or more"), Key("gm_crit"))
    cl_axis = np.linspace(0.25 * cl_f, 2.5 * cl_f, 181)
    marks = [Marker(f"this design {gm_crit * 1e3:.3g} mA/V", x=cl_f, y=gm_crit, unit="A/V")]
    caption = f"The dot is this design: {fmt(gm_crit, 'A/V')} needed at a {fmt(cl_f, 'F')} load"
    if gm_crit_max_a_per_v is not None:
        marks.append(Marker(f"Gmcritmax {gm_crit_max_a_per_v * 1e3:.3g} mA/V", y=gm_crit_max_a_per_v, unit="A/V"))
        caption += f"; it must sit below the {fmt(gm_crit_max_a_per_v, 'A/V')} Gmcritmax line"
    if gm_a_per_v is not None:
        marks.append(Marker(f"gm / {min_gain_margin:g}", y=gm_a_per_v / min_gain_margin, unit="A/V"))
        caption += f"; and below the gm / {fmt(min_gain_margin)} line"
    plot = plot_from_arrays("Critical gm against load capacitance", "Load capacitance CL", "F", cl_axis,
                            [("Critical gm", "A/V", 4.0 * esr_ohm * (2.0 * math.pi * f_hz) ** 2 * (c0_f + cl_axis) ** 2)],
                            markers=marks, caption=caption + ". A larger load raises the curve.")
    return Result(
        name="crystal oscillation margin",
        formula="gm_crit = 4*ESR*(2*pi*f)^2*(C0 + CL)^2; gain margin = gm/gm_crit >= 5; or gm_crit <= Gmcritmax",
        inputs=inputs,
        outputs=outputs,
        verdict=verdict,
        reason=reason,
        refs=(AN2867_GM,) + tuple(refs),
        assumptions=("ESR at its datasheet maximum", "C0 includes the package shunt capacitance only"),
        plots=(plot,),
        summary=summary,
        key=key,
    )


def drive_level(
    esr_ohm: float,
    dl_max_w: float,
    i_rms_a: float | None = None,
    f_hz: float | None = None,
    c_tot_f: float | None = None,
    v_pp_v: float | None = None,
) -> Result:
    """Power dissipated in the crystal from measured current, or from the voltage swing on the input capacitor."""
    if i_rms_a is not None:
        dl = esr_ohm * i_rms_a**2
        formula = "DL = ESR * Irms^2"
        inputs = {"esr": Quantity(esr_ohm, "ohm", label="Crystal ESR"),
                  "i_rms": Quantity(i_rms_a, "A", label="Crystal current, RMS")}
        source = f"That comes from {fmt(i_rms_a, 'A')} RMS through {fmt(esr_ohm, 'ohm')} of ESR."
    else:
        if f_hz is None or c_tot_f is None or v_pp_v is None:
            raise ValueError("give i_rms_a, or f_hz with c_tot_f and v_pp_v")
        i_rms = 2.0 * math.pi * f_hz * c_tot_f * v_pp_v / (2.0 * math.sqrt(2.0))
        dl = esr_ohm * i_rms**2
        formula = "DL = ESR*(pi*f*Ctot*Vpp)^2/2 (Irms = 2*pi*f*Ctot*Vpp/(2*sqrt(2)), sine at the input pin)"
        inputs = {
            "esr": Quantity(esr_ohm, "ohm", label="Crystal ESR"),
            "f": Quantity(f_hz, "Hz", label="Crystal frequency"),
            "c_tot": Quantity(c_tot_f, "F", "CL1 + Cs/2 + Cprobe at the amplifier input",
                              label="Capacitance at the amplifier input"),
            "v_pp": Quantity(v_pp_v, "V", label="Swing at the input pin, peak to peak"),
        }
        source = (f"That comes from a {fmt(v_pp_v, 'V')} swing on {fmt(c_tot_f, 'F')} at {fmt(f_hz, 'Hz')} "
                  f"through {fmt(esr_ohm, 'ohm')} of ESR.")
    inputs["dl_max"] = Quantity(dl_max_w, "W", label="Rated drive level")
    head = f"The crystal dissipates {fmt(dl, 'W')}"
    if dl > dl_max_w:
        verdict, reason = Verdict.FAIL, f"drive {dl * 1e6:.1f} uW over the {dl_max_w * 1e6:g} uW rating"
        summary = (f"{head}, above its {fmt(dl_max_w, 'W')} rating. {source} Overdrive ages the crystal and can "
                   "crack it; add a series resistor or reduce the swing.")
    elif dl > 0.8 * dl_max_w:
        verdict, reason = Verdict.MARGINAL, f"drive {dl * 1e6:.1f} uW is over 80 % of {dl_max_w * 1e6:g} uW"
        summary = (f"{head}, over 80% of its {fmt(dl_max_w, 'W')} rating. {source} Aging speeds up near the "
                   "rating, so a series resistor footprint is worth having.")
    else:
        verdict, reason = Verdict.PASS, f"drive {dl * 1e6:.1f} uW under {dl_max_w * 1e6:g} uW"
        summary = f"{head}, under 80% of its {fmt(dl_max_w, 'W')} rating. {source}"
    return Result(
        name="crystal drive level",
        formula=formula,
        inputs=inputs,
        outputs={"dl": Quantity(dl, "W", label="Drive level")},
        verdict=verdict,
        reason=reason,
        refs=("P = I^2*R in the motional resistance; current through the input capacitor is the crystal current", AN2867_DL),
        assumptions=("sinusoidal swing", "ESR at its datasheet maximum"),
        summary=summary,
        key=(Key("dl", f"{fmt(0.8 * dl_max_w, 'W')} or less"),),
    )
