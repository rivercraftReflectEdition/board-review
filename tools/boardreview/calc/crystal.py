"""Pierce crystal oscillator: load capacitance, pulling, oscillation margin and drive level."""

from __future__ import annotations

import math

from boardreview.calc.base import Quantity, Result, Verdict

AN2867 = "ST AN2867 Oscillator design guide for STM8 and STM32 (gm_crit, gain margin >= 5); revision and page UNSURE, not fetched"
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
    outputs = {"cl": Quantity(cl, "F")}
    inputs = {"c1": Quantity(c1_f, "F"), "c2": Quantity(c2_f, "F"), "c_stray": Quantity(c_stray_f, "F")}
    if cl_spec_f is None:
        verdict, reason = Verdict.INFO, ""
    else:
        inputs["cl_spec"] = Quantity(cl_spec_f, "F")
        err = (cl - cl_spec_f) / cl_spec_f
        outputs["cl_error"] = Quantity(err, "", "relative to CL spec")
        if c0_f is not None and c_motional_f is not None:
            ppm = 1e6 * c_motional_f / 2.0 * (1.0 / (c0_f + cl) - 1.0 / (c0_f + cl_spec_f))
            outputs["pulling"] = Quantity(ppm, "ppm", "positive means above nominal frequency")
            inputs["c0"] = Quantity(c0_f, "F")
            inputs["c_motional"] = Quantity(c_motional_f, "F")
        if abs(err) > tol_frac:
            verdict, reason = Verdict.FAIL, f"CL {cl * 1e12:.2f} pF is {err:+.0%} from the {cl_spec_f * 1e12:g} pF spec"
        else:
            verdict, reason = Verdict.PASS, f"CL {cl * 1e12:.2f} pF within {tol_frac:.0%} of {cl_spec_f * 1e12:g} pF"
    return Result(
        name="crystal load capacitance",
        formula="CL = C1*C2/(C1 + C2) + Cstray; pulling = C1m/2*(1/(C0 + CL) - 1/(C0 + CLspec))",
        inputs=inputs,
        outputs=outputs,
        verdict=verdict,
        reason=reason,
        refs=("series combination of C1 and C2 through ground, plus pin and trace stray", AN2867),
        assumptions=("Cstray includes both oscillator pins and the traces; 2 to 5 pF is typical, measure if it matters",),
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
    outputs = {"gm_crit": Quantity(gm_crit, "A/V")}
    inputs = {
        "esr": Quantity(esr_ohm, "ohm", "use the max ESR"),
        "f": Quantity(f_hz, "Hz"),
        "c0": Quantity(c0_f, "F"),
        "cl": Quantity(cl_f, "F"),
    }
    verdict, reason = Verdict.UNKNOWN, "give the oscillator gm or the MCU Gmcritmax"
    if gm_crit_max_a_per_v is not None:
        inputs["gm_crit_max"] = Quantity(gm_crit_max_a_per_v, "A/V")
        ratio = gm_crit_max_a_per_v / gm_crit
        outputs["gm_crit_max_over_gm_crit"] = Quantity(ratio, "")
        if gm_crit > gm_crit_max_a_per_v:
            verdict, reason = Verdict.FAIL, f"crystal gm_crit {gm_crit * 1e3:.3g} mA/V above Gmcritmax {gm_crit_max_a_per_v * 1e3:.3g} mA/V"
        elif ratio < 1.25:
            verdict, reason = Verdict.MARGINAL, f"gm_crit within 20 % of Gmcritmax ({ratio:.2f}x)"
        else:
            verdict, reason = Verdict.PASS, f"Gmcritmax is {ratio:.2f}x the crystal gm_crit"
    if gm_a_per_v is not None:
        inputs["gm"] = Quantity(gm_a_per_v, "A/V")
        margin = gm_a_per_v / gm_crit
        outputs["gain_margin"] = Quantity(margin, "")
        if margin < min_gain_margin:
            verdict, reason = Verdict.FAIL, f"gain margin {margin:.2f} under {min_gain_margin:g}"
        elif verdict is not Verdict.FAIL:
            verdict, reason = Verdict.PASS, f"gain margin {margin:.2f}"
    return Result(
        name="crystal oscillation margin",
        formula="gm_crit = 4*ESR*(2*pi*f)^2*(C0 + CL)^2; gain margin = gm/gm_crit >= 5; or gm_crit <= Gmcritmax",
        inputs=inputs,
        outputs=outputs,
        verdict=verdict,
        reason=reason,
        refs=(AN2867,) + tuple(refs),
        assumptions=("ESR at its datasheet maximum", "C0 includes the package shunt capacitance only"),
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
        inputs = {"esr": Quantity(esr_ohm, "ohm"), "i_rms": Quantity(i_rms_a, "A")}
    else:
        if f_hz is None or c_tot_f is None or v_pp_v is None:
            raise ValueError("give i_rms_a, or f_hz with c_tot_f and v_pp_v")
        i_rms = 2.0 * math.pi * f_hz * c_tot_f * v_pp_v / (2.0 * math.sqrt(2.0))
        dl = esr_ohm * i_rms**2
        formula = "DL = ESR*(pi*f*Ctot*Vpp)^2/2 (Irms = 2*pi*f*Ctot*Vpp/(2*sqrt(2)), sine at the input pin)"
        inputs = {
            "esr": Quantity(esr_ohm, "ohm"),
            "f": Quantity(f_hz, "Hz"),
            "c_tot": Quantity(c_tot_f, "F", "input-side load capacitor plus stray"),
            "v_pp": Quantity(v_pp_v, "V"),
        }
    inputs["dl_max"] = Quantity(dl_max_w, "W")
    if dl > dl_max_w:
        verdict, reason = Verdict.FAIL, f"drive {dl * 1e6:.1f} uW over the {dl_max_w * 1e6:g} uW rating"
    elif dl > 0.8 * dl_max_w:
        verdict, reason = Verdict.MARGINAL, f"drive {dl * 1e6:.1f} uW is over 80 % of {dl_max_w * 1e6:g} uW"
    else:
        verdict, reason = Verdict.PASS, f"drive {dl * 1e6:.1f} uW under {dl_max_w * 1e6:g} uW"
    return Result(
        name="crystal drive level",
        formula=formula,
        inputs=inputs,
        outputs={"dl": Quantity(dl, "W")},
        verdict=verdict,
        reason=reason,
        refs=("P = I^2*R in the motional resistance; current through the input capacitor is the crystal current", AN2867),
        assumptions=("sinusoidal swing", "ESR at its datasheet maximum"),
    )
