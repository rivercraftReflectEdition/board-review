"""Junction temperature from dissipation and theta-JA, the internal loss of a monolithic buck, thermal vias."""

from __future__ import annotations

import math

from boardreview.calc.base import Key, Quantity, Result, Verdict, fmt

LTC3633A = "LTC3633A/LTC3633A-1 data sheet Rev B (3633a1fb)"


def junction_temp(
    p_w: float,
    theta_ja_c_per_w: float,
    t_ambient_c: float,
    tj_max_c: float,
    margin_c: float = 20.0,
    refs: tuple[str, ...] = (),
) -> Result:
    """Tj = Ta + P*thetaJA against the maximum junction temperature less a margin."""
    tj = t_ambient_c + p_w * theta_ja_c_per_w
    if tj > tj_max_c:
        verdict, reason = Verdict.FAIL, f"Tj {tj:.1f} C above Tj max {tj_max_c:g} C"
    elif tj > tj_max_c - margin_c:
        verdict, reason = Verdict.MARGINAL, f"Tj {tj:.1f} C within {margin_c:g} C of Tj max {tj_max_c:g} C"
    else:
        verdict, reason = Verdict.PASS, f"Tj {tj:.1f} C, {tj_max_c - tj:.1f} C below Tj max"
    rise = tj - t_ambient_c
    text = [f"{fmt(p_w, 'W')} through {fmt(theta_ja_c_per_w, 'C/W')} raises the junction {fmt(rise, 'C')} above the "
            f"{fmt(t_ambient_c, 'C')} ambient, to {fmt(tj, 'C')}."]
    if verdict is Verdict.FAIL:
        text.append(f"That is above the {fmt(tj_max_c, 'C')} maximum, so the part overheats and may shut down.")
    elif verdict is Verdict.MARGINAL:
        text.append(f"That is within {fmt(margin_c, 'C')} of the {fmt(tj_max_c, 'C')} maximum, closer than we want.")
    else:
        text.append(f"That leaves {fmt(tj_max_c - tj, 'C')} below the {fmt(tj_max_c, 'C')} maximum.")
    return Result(
        name="junction temperature",
        formula="Tj = Ta + P * thetaJA",
        inputs={
            "p": Quantity(p_w, "W", label="Power dissipated"),
            "theta_ja": Quantity(theta_ja_c_per_w, "C/W", label="Junction to ambient resistance"),
            "t_ambient": Quantity(t_ambient_c, "C", label="Ambient temperature"),
            "tj_max": Quantity(tj_max_c, "C", label="Maximum junction temperature"),
            "margin_min": Quantity(margin_c, "C", "below Tj max", "Margin wanted below the maximum"),
        },
        outputs={"tj": Quantity(tj, "C", label="Junction temperature"),
                 "rise": Quantity(rise, "C", label="Rise above ambient")},
        summary=" ".join(text),
        key=(Key("tj", f"{fmt(tj_max_c - margin_c, 'C')} or less"), Key("rise")),
        verdict=verdict,
        reason=reason,
        refs=(f"{LTC3633A} p. 4 Note 1 and p. 20 (TJ = TA + PD*thetaJA)",) + tuple(refs),
        assumptions=(
            "thetaJA is the vendor's test-board number; less copper or fewer vias under the exposed pad raises it",
            "in vacuum there is no convection, so a datasheet thetaJA is optimistic; use the board conduction path",
        ),
    )


def buck_ic_dissipation(
    vin_v: float,
    vout_v: float,
    iout_a: float,
    r_top_ohm: float,
    r_bot_ohm: float,
    f_hz: float,
    q_gate_c: float,
    i_q_a: float,
) -> Result:
    """Loss inside a monolithic synchronous buck: switch conduction plus gate drive and quiescent from VIN."""
    d = vout_v / vin_v
    r_sw = r_top_ohm * d + r_bot_ohm * (1 - d)
    p_cond = iout_a**2 * r_sw
    p_ldo = vin_v * (f_hz * q_gate_c + i_q_a)
    summary = (f"At {fmt(iout_a, 'A')} out from {fmt(vin_v, 'V')} to {fmt(vout_v, 'V')}, the switches lose "
               f"{fmt(p_cond, 'W')} and the gate drive and quiescent current {fmt(p_ldo, 'W')}, "
               f"{fmt(p_cond + p_ldo, 'W')} in the part. Use that with the package's thermal resistance for the "
               "junction temperature.")
    return Result(
        name="buck IC dissipation",
        formula="RSW = Rtop*D + Rbot*(1 - D); PD = IOUT^2*RSW + VIN*(f*(QT + QB) + IQ)",
        inputs={
            "vin": Quantity(vin_v, "V", label="Input voltage"),
            "vout": Quantity(vout_v, "V", label="Output voltage"),
            "iout": Quantity(iout_a, "A", label="Output current"),
            "r_top": Quantity(r_top_ohm, "ohm", label="Top switch resistance"),
            "r_bot": Quantity(r_bot_ohm, "ohm", label="Bottom switch resistance"),
            "f": Quantity(f_hz, "Hz", label="Switching frequency"),
            "q_gate": Quantity(q_gate_c, "coulomb", "QT + QB", "Gate charge, both switches"),
            "i_q": Quantity(i_q_a, "A", label="Quiescent current"),
        },
        outputs={
            "r_sw": Quantity(r_sw, "ohm", label="Switch resistance, duty weighted"),
            "p_conduction": Quantity(p_cond, "W", label="Conduction loss"),
            "p_gate_and_iq": Quantity(p_ldo, "W", label="Gate drive and quiescent loss"),
            "p_total": Quantity(p_cond + p_ldo, "W", label="Total loss in the part"),
        },
        summary=summary,
        key=(Key("p_total"), Key("p_conduction"), Key("p_gate_and_iq")),
        verdict=Verdict.INFO,
        refs=(f"{LTC3633A} pp. 19 to 20, Efficiency and Thermal Considerations (worked example)",),
        assumptions=("transition and core losses ignored (under 2 % per the LTC3633A data sheet)", "RDS(on) at the expected Tj"),
    )


def via_resistance(n_vias: int, drill_d_m: float, plating_t_m: float, length_m: float,
                   k_cu_w_per_mk: float = 390.0, k_fill_w_per_mk: float = 0.0) -> Result:
    """Thermal resistance of n plated vias in parallel, conduction along the barrel (and fill) only."""
    r_out = drill_d_m / 2.0
    r_in = max(r_out - plating_t_m, 0.0)
    g_one = (k_cu_w_per_mk * math.pi * (r_out**2 - r_in**2) + k_fill_w_per_mk * math.pi * r_in**2) / length_m
    r_one, r_total = 1.0 / g_one, 1.0 / (g_one * n_vias)
    fill = "filled" if k_fill_w_per_mk else "open"
    summary = (f"{n_vias} {fill} vias of {fmt(drill_d_m, 'm')} drill with {fmt(plating_t_m, 'm')} plating through "
               f"{fmt(length_m, 'm')} of board conduct with {fmt(r_total, 'C/W')} together, {fmt(r_one, 'C/W')} each. "
               "Spreading in the planes adds to this.")
    return Result(
        name="thermal via resistance",
        formula="R1 = L / (k_Cu*pi*(r^2 - (r - t)^2) + k_fill*pi*(r - t)^2), r = drill/2; R = R1/n",
        inputs={
            "n": Quantity(n_vias, "count", label="Number of vias"),
            "drill_d": Quantity(drill_d_m, "m", "plating grows inward from the drilled wall", "Drill diameter"),
            "plating_t": Quantity(plating_t_m, "m", label="Plating thickness"),
            "length": Quantity(length_m, "m", "board thickness between the layers", "Via length"),
            "k_cu": Quantity(k_cu_w_per_mk, "W/(m K)", label="Copper conductivity"),
            "k_fill": Quantity(k_fill_w_per_mk, "W/(m K)", "0 for an open via", "Fill conductivity"),
        },
        outputs={"r_one": Quantity(r_one, "C/W", label="One via"),
                 "r_total": Quantity(r_total, "C/W", label="All vias in parallel")},
        summary=summary,
        key=(Key("r_total"), Key("r_one")),
        verdict=Verdict.INFO,
        refs=("Fourier conduction R = L/(k A) along the barrel; vias in parallel",),
        assumptions=("spreading in the planes, the pad and solder interface are not included",
                     "k_Cu 390 W/(m K) is bulk copper; plated copper is often lower, so this is optimistic"),
    )
