"""I2C bus rise time and pull-up resistor range per the NXP I2C-bus specification."""

from __future__ import annotations

from boardreview.calc.base import Quantity, Result, Verdict

UM10204 = "NXP UM10204 I2C-bus specification and user manual Rev. 7.0 (1 October 2021)"
K_RISE = 0.8473
MODES = {
    "standard": {"tr_max_s": 1000e-9, "iol_a": 3e-3, "cb_max_f": 400e-12},
    "fast": {"tr_max_s": 300e-9, "iol_a": 3e-3, "cb_max_f": 400e-12},
    "fast_plus": {"tr_max_s": 120e-9, "iol_a": 20e-3, "cb_max_f": 550e-12},
}
REFS = (
    f"{UM10204} p. 43 Table 10 (VOL 0.4 V at IOL 3 mA, 20 mA for Fm+; 0.2 VDD at 2 mA for VDD <= 2 V)",
    f"{UM10204} p. 44 Table 11 (tr max 1000/300/120 ns, Cb max 400/400/550 pF)",
    f"{UM10204} p. 50 sec. 7.1 eq. (1) and (2), tr = 0.8473 RC from 0.3 VDD to 0.7 VDD",
)


def i2c_rise_time(r_pullup_ohm: float, c_bus_f: float, mode: str = "fast", margin_frac: float = 0.10) -> Result:
    """30 % to 70 % rise time of an RC-loaded open-drain line against the mode limit."""
    m = MODES[mode]
    tr = K_RISE * r_pullup_ohm * c_bus_f
    if tr > m["tr_max_s"]:
        verdict, reason = Verdict.FAIL, f"tr {tr * 1e9:.0f} ns exceeds {mode} limit {m['tr_max_s'] * 1e9:.0f} ns"
    elif tr > (1 - margin_frac) * m["tr_max_s"]:
        verdict, reason = Verdict.MARGINAL, f"tr {tr * 1e9:.0f} ns within {margin_frac:.0%} of {m['tr_max_s'] * 1e9:.0f} ns"
    else:
        verdict, reason = Verdict.PASS, f"tr {tr * 1e9:.0f} ns under {m['tr_max_s'] * 1e9:.0f} ns"
    return Result(
        name=f"I2C rise time ({mode})",
        formula="tr = 0.8473 * Rp * Cb",
        inputs={"r_pullup": Quantity(r_pullup_ohm, "ohm"), "c_bus": Quantity(c_bus_f, "F")},
        outputs={"tr": Quantity(tr, "s"), "tr_max": Quantity(m["tr_max_s"], "s")},
        verdict=verdict,
        reason=reason,
        refs=REFS,
        assumptions=("Cb includes pins, trace and connector", "no current-source pull-up or bus buffer"),
    )


def i2c_pullup_range(
    vdd_v: float, c_bus_f: float, mode: str = "fast", r_pullup_ohm: float | None = None
) -> Result:
    """Allowed pull-up range: sink current sets the minimum, rise time sets the maximum."""
    m = MODES[mode]
    vol, iol = (0.4, m["iol_a"]) if vdd_v > 2.0 else (0.2 * vdd_v, 2e-3)
    rp_min = (vdd_v - vol) / iol
    rp_max = m["tr_max_s"] / (K_RISE * c_bus_f)
    if c_bus_f > m["cb_max_f"]:
        verdict, reason = Verdict.FAIL, f"Cb {c_bus_f * 1e12:.0f} pF exceeds {m['cb_max_f'] * 1e12:.0f} pF for {mode}"
    elif rp_min > rp_max:
        verdict, reason = Verdict.FAIL, f"no valid pull-up: Rp(min) {rp_min:.0f} ohm > Rp(max) {rp_max:.0f} ohm"
    elif r_pullup_ohm is None:
        verdict, reason = Verdict.INFO, f"choose {rp_min:.0f} to {rp_max:.0f} ohm"
    elif r_pullup_ohm < rp_min:
        verdict, reason = Verdict.FAIL, f"{r_pullup_ohm:.0f} ohm needs more than {iol * 1e3:g} mA to reach VOL"
    elif r_pullup_ohm > rp_max:
        verdict, reason = Verdict.FAIL, f"{r_pullup_ohm:.0f} ohm is too slow for {c_bus_f * 1e12:.0f} pF"
    else:
        verdict, reason = Verdict.PASS, f"{r_pullup_ohm:.0f} ohm inside {rp_min:.0f} to {rp_max:.0f} ohm"
    inputs = {"vdd": Quantity(vdd_v, "V"), "c_bus": Quantity(c_bus_f, "F")}
    if r_pullup_ohm is not None:
        inputs["r_pullup"] = Quantity(r_pullup_ohm, "ohm")
    return Result(
        name=f"I2C pull-up range ({mode})",
        formula="Rp(min) = (VDD - VOL(max))/IOL; Rp(max) = tr/(0.8473 * Cb)",
        inputs=inputs,
        outputs={
            "vol_max": Quantity(vol, "V"),
            "iol": Quantity(iol, "A"),
            "rp_min": Quantity(rp_min, "ohm"),
            "rp_max": Quantity(rp_max, "ohm"),
        },
        verdict=verdict,
        reason=reason,
        refs=REFS,
        assumptions=("resistor tolerance not included; check Rp(min) at -tol and Rp(max) at +tol",),
    )
