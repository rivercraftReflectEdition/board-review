"""I2C bus rise time and pull-up resistor range per the NXP I2C-bus specification."""

from __future__ import annotations

from boardreview.calc.base import Key, Quantity, Result, Verdict, fmt

UM10204 = "NXP UM10204 I2C-bus specification and user manual Rev. 7.0 (1 October 2021)"
K_RISE = 0.8473
MODES = {
    "standard": {"tr_max_s": 1000e-9, "iol_a": 3e-3, "cb_max_f": 400e-12},
    "fast": {"tr_max_s": 300e-9, "iol_a": 3e-3, "cb_max_f": 400e-12},
    "fast_plus": {"tr_max_s": 120e-9, "iol_a": 20e-3, "cb_max_f": 550e-12},
}
MODE_NAME = {"standard": "Standard mode", "fast": "Fast mode", "fast_plus": "Fast-mode Plus"}
REFS = (
    f"{UM10204} p. 43 Table 10 (VOL 0.4 V at IOL 3 mA, 20 mA for Fm+; 0.2 VDD at 2 mA for VDD <= 2 V)",
    f"{UM10204} p. 44 Table 11 (tr max 1000/300/120 ns, Cb max 400/400/550 pF)",
    f"{UM10204} p. 50 sec. 7.1 eq. (1) and (2), tr = 0.8473 RC from 0.3 VDD to 0.7 VDD",
)


def i2c_rise_time(r_pullup_ohm: float, c_bus_f: float, mode: str = "fast", margin_frac: float = 0.10) -> Result:
    """30 % to 70 % rise time of an RC-loaded open-drain line against the mode limit."""
    m = MODES[mode]
    tr = K_RISE * r_pullup_ohm * c_bus_f
    limit, name = fmt(m["tr_max_s"], "s"), MODE_NAME[mode]
    head = f"A {fmt(r_pullup_ohm, 'ohm')} pull-up on {fmt(c_bus_f, 'F')} of bus gives a {fmt(tr, 's')} rise time."
    if tr > m["tr_max_s"]:
        verdict, reason = Verdict.FAIL, f"tr {tr * 1e9:.0f} ns exceeds {mode} limit {m['tr_max_s'] * 1e9:.0f} ns"
        summary = (f"{head} {name} allows {limit}, so the edges are too slow and bits can be read wrong at full "
                   "speed; use a smaller pull-up or less capacitance.")
    elif tr > (1 - margin_frac) * m["tr_max_s"]:
        verdict = Verdict.MARGINAL
        reason = f"tr {tr * 1e9:.0f} ns within {margin_frac:.0%} of {m['tr_max_s'] * 1e9:.0f} ns"
        summary = (f"{head} That is within {fmt(100.0 * margin_frac, '%')} of the {limit} {name} limit, so a little "
                   "more bus capacitance or a high-tolerance resistor pushes it over.")
    else:
        verdict, reason = Verdict.PASS, f"tr {tr * 1e9:.0f} ns under {m['tr_max_s'] * 1e9:.0f} ns"
        summary = f"{head} That is under the {limit} {name} limit, with room for more capacitance on the bus."
    return Result(
        name=f"I2C rise time ({mode})",
        formula="tr = 0.8473 * Rp * Cb",
        inputs={
            "r_pullup": Quantity(r_pullup_ohm, "ohm", label="Pull-up resistor"),
            "c_bus": Quantity(c_bus_f, "F", label="Bus capacitance"),
            "margin_min": Quantity(margin_frac, "", "fraction of tr max", label="Required margin to the limit"),
        },
        outputs={"tr": Quantity(tr, "s", label="Rise time"),
                 "tr_max": Quantity(m["tr_max_s"], "s", label="Rise time limit")},
        verdict=verdict,
        reason=reason,
        refs=REFS,
        assumptions=("Cb includes pins, trace and connector", "no current-source pull-up or bus buffer"),
        summary=summary,
        key=(Key("tr", f"{fmt((1 - margin_frac) * m['tr_max_s'], 's')} or less"),),
    )


def i2c_pullup_range(
    vdd_v: float, c_bus_f: float, mode: str = "fast", r_pullup_ohm: float | None = None
) -> Result:
    """Allowed pull-up range: sink current sets the minimum, rise time sets the maximum."""
    m = MODES[mode]
    vol, iol = (0.4, m["iol_a"]) if vdd_v > 2.0 else (0.2 * vdd_v, 2e-3)
    rp_min = (vdd_v - vol) / iol
    rp_max = m["tr_max_s"] / (K_RISE * c_bus_f)
    lo, hi, name = fmt(rp_min, "ohm"), fmt(rp_max, "ohm"), MODE_NAME[mode]
    bounds = (f"The pull-up must be at least {lo} so the pins can pull the line down to {fmt(vol, 'V')} with "
              f"{fmt(iol, 'A')}, and at most {hi} so it rises in time on {fmt(c_bus_f, 'F')}.")
    window = f"{lo} to {hi}"
    key: tuple[Key, ...] = (Key("rp_min"), Key("rp_max"))
    if c_bus_f > m["cb_max_f"]:
        verdict = Verdict.FAIL
        reason = f"Cb {c_bus_f * 1e12:.0f} pF exceeds {m['cb_max_f'] * 1e12:.0f} pF for {mode}"
        summary = (f"The bus has {fmt(c_bus_f, 'F')} of capacitance, more than the {fmt(m['cb_max_f'], 'F')} "
                   f"{name} allows. No pull-up value fixes that; split the bus, buffer it or use a slower mode.")
        key = (Key("c_bus", f"{fmt(m['cb_max_f'], 'F')} or less"),)
    elif rp_min > rp_max:
        verdict, reason = Verdict.FAIL, f"no valid pull-up: Rp(min) {rp_min:.0f} ohm > Rp(max) {rp_max:.0f} ohm"
        summary = f"{bounds} The minimum is above the maximum, so no value works; reduce the bus capacitance."
    elif r_pullup_ohm is None:
        verdict, reason = Verdict.INFO, f"choose {rp_min:.0f} to {rp_max:.0f} ohm"
        summary = f"{bounds} Any pull-up from {window} works on this bus in {name}."
    elif r_pullup_ohm < rp_min:
        verdict = Verdict.FAIL
        reason = f"{r_pullup_ohm:.0f} ohm needs more than {iol * 1e3:g} mA to reach VOL"
        summary = (f"{bounds} The {fmt(r_pullup_ohm, 'ohm')} pull-up is below that minimum, so a low level does not "
                   f"reach {fmt(vol, 'V')}; use {window}.")
        key = (Key("r_pullup", window),)
    elif r_pullup_ohm > rp_max:
        verdict, reason = Verdict.FAIL, f"{r_pullup_ohm:.0f} ohm is too slow for {c_bus_f * 1e12:.0f} pF"
        summary = (f"{bounds} The {fmt(r_pullup_ohm, 'ohm')} pull-up is above that maximum, so edges rise too "
                   f"slowly for {name}; use {window}.")
        key = (Key("r_pullup", window),)
    else:
        verdict, reason = Verdict.PASS, f"{r_pullup_ohm:.0f} ohm inside {rp_min:.0f} to {rp_max:.0f} ohm"
        summary = f"{bounds} The {fmt(r_pullup_ohm, 'ohm')} pull-up sits inside that window."
        key = (Key("r_pullup", window),)
    inputs = {"vdd": Quantity(vdd_v, "V", label="Bus supply"), "c_bus": Quantity(c_bus_f, "F", label="Bus capacitance")}
    if r_pullup_ohm is not None:
        inputs["r_pullup"] = Quantity(r_pullup_ohm, "ohm", label="Pull-up resistor")
    return Result(
        name=f"I2C pull-up range ({mode})",
        formula="Rp(min) = (VDD - VOL(max))/IOL; Rp(max) = tr/(0.8473 * Cb)",
        inputs=inputs,
        outputs={
            "vol_max": Quantity(vol, "V", label="Highest low level"),
            "iol": Quantity(iol, "A", label="Sink current"),
            "rp_min": Quantity(rp_min, "ohm", label="Smallest pull-up"),
            "rp_max": Quantity(rp_max, "ohm", label="Largest pull-up"),
        },
        verdict=verdict,
        reason=reason,
        refs=REFS,
        assumptions=("resistor tolerance not included; check Rp(min) at -tol and Rp(max) at +tol",),
        summary=summary,
        key=key,
    )
