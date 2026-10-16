"""Ferrite bead plus decoupling capacitor as an LC filter: transfer, output impedance, peaking near switchers, damping."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, Sequence

import numpy as np

from boardreview.calc.base import Key, Marker, Quantity, Result, Verdict, fmt, plot_from_arrays, si_text
from boardreview.calc.curves import find_column, parse_csv_table, unit_scale

TWO_PI = 2.0 * math.pi
ERICKSON = (
    "Erickson and Maksimovic, Fundamentals of Power Electronics, 2nd ed., Rf-Cb parallel damping "
    "(sec. 10.4.1, section number UNSURE; Rd_opt and Zout_peak verified numerically in tests)"
)


class Bead(Protocol):
    note: str

    def z(self, f_hz: np.ndarray) -> np.ndarray: ...

    def l_low_h(self) -> float: ...

    def uncharacterized(self, f_hz: np.ndarray) -> np.ndarray: ...

    def params(self) -> dict[str, Quantity]: ...


@dataclass(frozen=True)
class BeadRLC:
    """Rdc in series with L || R_ac || C_par; assumed=True when the values are not from vendor data."""

    l_h: float
    rdc_ohm: float
    r_ac_ohm: float = math.inf
    c_par_f: float = 0.0
    note: str = ""
    assumed: bool = False

    def z(self, f_hz):
        s = 1j * TWO_PI * np.asarray(f_hz, dtype=float)
        y = 1.0 / (s * self.l_h) + s * self.c_par_f
        if math.isfinite(self.r_ac_ohm):
            y = y + 1.0 / self.r_ac_ohm
        return self.rdc_ohm + 1.0 / y

    def l_low_h(self):
        return self.l_h

    def uncharacterized(self, f_hz):
        return np.full(np.shape(f_hz), self.assumed)

    def params(self):
        return {
            "l": Quantity(self.l_h, "H", label="Bead inductance"),
            "rdc": Quantity(self.rdc_ohm, "ohm", label="Bead DC resistance"),
            "r_ac": Quantity(self.r_ac_ohm, "ohm", label="Bead loss resistance"),
            "c_par": Quantity(self.c_par_f, "F", label="Bead parallel capacitance"),
        }


@dataclass(frozen=True)
class BeadCurve:
    """Vendor R(f) and X(f) table on log frequency; R is the total series resistance, RDC included."""

    f_hz: tuple[float, ...]
    r_ohm: tuple[float, ...]
    x_ohm: tuple[float, ...]
    rdc_ohm: float = 0.0
    note: str = ""

    def z(self, f_hz):
        f = np.asarray(f_hz, dtype=float)
        lf, lf0 = np.log10(f), np.log10(np.asarray(self.f_hz))
        r = np.interp(lf, lf0, self.r_ohm)
        x = np.interp(lf, lf0, self.x_ohm)
        below = f < self.f_hz[0]
        r_low = min(self.rdc_ohm, self.r_ohm[0]) if self.rdc_ohm > 0 else self.r_ohm[0]
        r = np.where(below, r_low, r)
        x = np.where(below, self.x_ohm[0] * f / self.f_hz[0], x)
        return r + 1j * x

    def l_low_h(self):
        return self.x_ohm[0] / (TWO_PI * self.f_hz[0])

    def uncharacterized(self, f_hz):
        f = np.asarray(f_hz, dtype=float)
        return (f < self.f_hz[0]) | (f > self.f_hz[-1])

    def params(self):
        return {
            "f_first": Quantity(self.f_hz[0], "Hz", label="Bead curve, first frequency"),
            "f_last": Quantity(self.f_hz[-1], "Hz", label="Bead curve, last frequency"),
            "points": Quantity(len(self.f_hz), "count", label="Bead curve points"),
            "rdc": Quantity(self.rdc_ohm, "ohm", "used below the first point only", "Bead DC resistance"),
        }


@dataclass(frozen=True)
class Cap:
    """Capacitor or RC damper leg: ESR (plus any series resistor) + ESL + C."""

    c_f: float
    esr_ohm: float = 0.0
    esl_h: float = 0.0

    def z(self, f_hz):
        s = 1j * TWO_PI * np.asarray(f_hz, dtype=float)
        return self.esr_ohm + s * self.esl_h + 1.0 / (s * self.c_f)


def bead_from_spec(z_ohm: float, f_hz: float, rdc_ohm: float, part: str = "") -> BeadRLC:
    """R-L bead model from one datasheet impedance point, taking that point as the R = X crossover."""
    r = z_ohm * math.sqrt(2.0)
    note = (
        f"{part} modeled from |Z| = {z_ohm:g} ohm at {f_hz:g} Hz as an R = X crossover: "
        f"L = {r / (TWO_PI * f_hz):.4g} H, R = {r:.4g} ohm. UNSURE until the vendor R/X curve is loaded"
    ).strip()
    return BeadRLC(l_h=r / (TWO_PI * f_hz), rdc_ohm=rdc_ohm, r_ac_ohm=r, note=note, assumed=True)


def parse_bead_csv(text: str, rdc_ohm: float = 0.0, part: str = "") -> BeadCurve:
    """Bead curve from a vendor export with frequency, R and X columns; R as exported, RDC included."""
    headers, data = parse_csv_table(text)
    i_f = find_column(headers, "freq")
    i_r = next(i for i, h in enumerate(headers) if h.strip().upper().startswith("R"))
    i_x = next(i for i, h in enumerate(headers) if h.strip().upper().startswith("X"))
    f = data[:, i_f] * unit_scale(headers[i_f], "Hz")
    order = np.argsort(f)
    r = data[order, i_r] * unit_scale(headers[i_r], "Ohm")
    note = f"{part} from vendor R/X curve, {f[order][0]:g} to {f[order][-1]:g} Hz, R includes RDC".strip()
    if rdc_ohm > 0 and r.min() < rdc_ohm:
        note += f"; R falls to {r.min():.4g} ohm, below RDC {rdc_ohm:g} ohm: check whether the export subtracts RDC"
    return BeadCurve(
        tuple(f[order]),
        tuple(r),
        tuple(data[order, i_x] * unit_scale(headers[i_x], "Ohm")),
        rdc_ohm,
        note,
    )


def damping_options(l_h: float, c_f: float, n: float = 4.0) -> Result:
    """Series-R and RC-shunt damping values for an LC with characteristic impedance sqrt(L/C)."""
    r0 = math.sqrt(l_h / c_f)
    k = math.sqrt((2 + n) * (4 + 3 * n) / (2 * n * n * (4 + n)))
    z_pk = r0 * math.sqrt(2 * (2 + n)) / n
    summary = (f"The filter's characteristic impedance is {fmt(r0, 'ohm')}. A {fmt(n * c_f, 'F')} capacitor with "
               f"{fmt(k * r0, 'ohm')} in series across the output holds the impedance peak near {fmt(z_pk, 'ohm')}. "
               f"A series resistor of {fmt(r0, 'ohm')} instead gives a Q of about 1.")
    return Result(
        name="LC damping options",
        formula=(
            "R0 = sqrt(L/C); series R = R0 (Q about 1) or 2 R0 (Q = 0.5); Cd = n C; "
            "Rd_opt = R0*sqrt((2+n)(4+3n)/(2 n^2 (4+n))); Zout_peak = R0*sqrt(2(2+n))/n"
        ),
        inputs={"l": Quantity(l_h, "H", label="Filter inductance"), "c": Quantity(c_f, "F", label="Filter capacitance"),
                "n": Quantity(n, "", "Cd/C", "Damper to filter capacitance ratio")},
        outputs={
            "r0": Quantity(r0, "ohm", "sqrt(L/C)", "Characteristic impedance"),
            "r_series_q1": Quantity(r0, "ohm", "series R = sqrt(L/C), Q about 1", "Series resistor for a Q of 1"),
            "r_series_critical": Quantity(2.0 * r0, "ohm", "series R = 2 sqrt(L/C), Q = 0.5",
                                          "Series resistor for a Q of 0.5"),
            "cd": Quantity(n * c_f, "F", f"Cd = {n:g} C", "Damper capacitor"),
            "rd_opt": Quantity(k * r0, "ohm", f"optimum Rd for Cd = {n:g} C", "Damper resistor"),
            "zout_peak_opt": Quantity(z_pk, "ohm", "peak Zout with that damper", "Impedance peak with the damper"),
        },
        verdict=Verdict.INFO,
        refs=(ERICKSON,),
        assumptions=("lossless L and C apart from the damper",),
        summary=summary,
        key=(Key("r0"), Key("cd"), Key("rd_opt")),
    )


def _shunt(cap: Cap, dampers: Sequence[Cap], r_load_ohm: float, f: np.ndarray) -> np.ndarray:
    y = 1.0 / cap.z(f)
    for d in dampers:
        y = y + 1.0 / d.z(f)
    if math.isfinite(r_load_ohm):
        y = y + 1.0 / r_load_ohm
    return 1.0 / y


def filter_response(
    bead: Bead, cap: Cap, f_hz, dampers: Sequence[Cap] = (), z_source_ohm: float = 0.0, r_load_ohm: float = math.inf
) -> tuple[np.ndarray, np.ndarray]:
    """Source-to-load transfer H and the impedance seen from the load, as complex arrays."""
    f = np.atleast_1d(np.asarray(f_hz, dtype=float))
    zsh = _shunt(cap, dampers, r_load_ohm, f)
    zser = z_source_ohm + bead.z(f)
    return zsh / (zser + zsh), zser * zsh / (zser + zsh)


def _damping_q(bead: Bead, cap: Cap, f0_hz: float, r0_ohm: float, dampers: Sequence[Cap], z_source_ohm: float,
               r_load_ohm: float) -> tuple[float, float, list[str]]:
    """(Q = sqrt(L/C)/R_total, R_total at f0, what else damps it); with a damper or a load, Q is an upper bound."""
    r_total = float(np.real(bead.z(np.array([f0_hz]))[0])) + cap.esr_ohm + z_source_ohm
    extra = (["an RC damper"] if dampers else []) + (["the load resistor"] if r_load_ohm < 1e3 * r0_ohm else [])
    return (r0_ohm / r_total if r_total > 0 else math.inf), r_total, extra


def lc_filter(
    bead: Bead,
    cap: Cap,
    f_switch_hz: Sequence[float] = (),
    harmonics: int = 5,
    dampers: Sequence[Cap] = (),
    z_source_ohm: float = 0.0,
    r_load_ohm: float = math.inf,
    peak_limit_db: float = 6.0,
    window_frac: float = 0.30,
    f_min_hz: float = 1e3,
    f_max_hz: float = 1e9,
    points_per_decade: int = 400,
    refs: tuple[str, ...] = (),
) -> Result:
    """Peaking of a bead-capacitor filter, flagged when it lands within +-window of a switching harmonic."""
    n = int(round(math.log10(f_max_hz / f_min_hz) * points_per_decade)) + 1
    f = np.logspace(math.log10(f_min_hz), math.log10(f_max_hz), n)
    h, zout = filter_response(bead, cap, f, dampers, z_source_ohm, r_load_ohm)
    h_db = 20.0 * np.log10(np.abs(h))
    i_pk = int(np.argmax(h_db))
    i_z = int(np.argmax(np.abs(zout)))
    l_low = bead.l_low_h()
    f0 = 1.0 / (TWO_PI * math.sqrt(l_low * cap.c_f))
    opts = {k: q.value for k, q in damping_options(l_low, cap.c_f).outputs.items()}
    hits = []
    for fs in f_switch_hz:
        for k in range(1, harmonics + 1):
            fk = k * fs
            m = (f >= fk * (1 - window_frac)) & (f <= fk * (1 + window_frac))
            if m.any():
                j = int(np.argmax(np.where(m, h_db, -np.inf)))
                hits.append((h_db[j], fk, f[j], k, fs))
    worst = max(hits) if hits else None
    edges = (1 - window_frac, 1 + window_frac)
    checked = [f0, float(f[i_pk])] + [fs * k * e for fs in f_switch_hz for k in range(1, harmonics + 1) for e in edges]
    modeled = [fx for fx in checked if bool(bead.uncharacterized(np.array([fx]))[0])]
    gap = ""
    if modeled:
        span = f"{min(modeled):.4g} Hz" if len(modeled) == 1 else f"{min(modeled):.4g} to {max(modeled):.4g} Hz"
        gap = f"bead not characterized at {span}; the vendor R/X curve over that range, or a measurement, settles it"
    peak_db, f_pk = float(h_db[i_pk]), float(f[i_pk])
    gain_pk, q_limit = 10.0 ** (peak_db / 20.0), 10.0 ** (peak_limit_db / 20.0)
    q, r_total, extra = _damping_q(bead, cap, f0, opts["r0"], dampers, z_source_ohm, r_load_ohm)
    if extra:
        q_note = f"upper bound: {' and '.join(extra)} add damping that sqrt(L/C)/R_total leaves out"
        damped_by_bound = math.isfinite(q) and q <= q_limit
        underdamped = not damped_by_bound and peak_db > peak_limit_db
    else:
        q_note = "sqrt(L/C)/R_total; holds for a series LC with an open load and no damper"
        underdamped = q > q_limit
    outputs = {
        "f0": Quantity(f0, "Hz", "1/(2 pi sqrt(L C)) with low-frequency bead L", "Resonance"),
        "peak": Quantity(peak_db, "dB", label="Peak gain"),
        "f_peak": Quantity(f_pk, "Hz", label="Peak frequency"),
        "peak_gain_linear": Quantity(gain_pk, "", "10^(peak/20); near Q only for a lightly damped LC",
                                     "Peak gain, linear"),
        "q_damping": Quantity(q, "", q_note, "Damping Q"),
        "r_total": Quantity(r_total, "ohm", "bead R at resonance + capacitor ESR + source",
                            "Series resistance at resonance"),
        "zout_peak": Quantity(abs(zout[i_z]), "ohm", label="Impedance peak seen from the load"),
        "f_zout_peak": Quantity(f[i_z], "Hz", label="Impedance peak frequency"),
        "r0": Quantity(opts["r0"], "ohm", "sqrt(L/C)", "Characteristic impedance"),
        "r_series_q1": Quantity(opts["r_series_q1"], "ohm", "series R = sqrt(L/C), Q about 1",
                                "Series resistor for a Q of 1"),
        "r_series_critical": Quantity(opts["r_series_critical"], "ohm", "series R = 2 sqrt(L/C), Q = 0.5",
                                      "Series resistor for a Q of 0.5"),
        "rc_damper_cd": Quantity(opts["cd"], "F", "Cd = 4 C", "Damper capacitor"),
        "rc_damper_rd": Quantity(opts["rd_opt"], "ohm", "optimum Rd for Cd = 4 C", "Damper resistor"),
        "rc_damper_zout_peak": Quantity(opts["zout_peak_opt"], "ohm", "peak Zout with that damper",
                                        "Impedance peak with the damper"),
    }
    if worst is not None:
        outputs["peak_near_switcher"] = Quantity(worst[0], "dB", f"at {worst[2]:.4g} Hz, harmonic {worst[3]} of {worst[4]:.4g} Hz",
                                                 "Gain near a switching harmonic")
    if worst is not None and worst[0] > peak_limit_db:
        verdict = Verdict.FAIL
        reason = (
            f"{worst[0]:.1f} dB of gain at {worst[2] / 1e6:.3g} MHz, within {window_frac:.0%} of harmonic {worst[3]} "
            f"of the {worst[4] / 1e6:.4g} MHz switcher; add Cd >= {opts['cd'] * 1e9:.3g} nF with Rd about {opts['rd_opt']:.2g} ohm"
        )
    elif underdamped:
        verdict = Verdict.MARGINAL
        reason = (f"damping Q {q:.3g} above {q_limit:.3g}" + ("" if not extra else f" or peak above {peak_limit_db:g} dB")
                  + f"; {h_db[i_pk]:.1f} dB peak at {f[i_pk] / 1e6:.3g} MHz, away from the given switching frequencies")
    elif modeled:
        verdict = Verdict.MARGINAL
        reason = f"peak {h_db[i_pk]:.1f} dB under the {peak_limit_db:g} dB limit only for the assumed bead model"
    else:
        verdict, reason = Verdict.PASS, f"peak {h_db[i_pk]:.1f} dB under the {peak_limit_db:g} dB limit"
    if gap:
        reason += f"; {gap}"
    fs_text = ", ".join(fmt(fs, "Hz") for fs in f_switch_hz)
    q_text = (f"the damping Q is {fmt(q)}" + (", an upper bound" if extra else "") if math.isfinite(q)
              else "nothing in series damps it")
    if peak_db >= 1.0:
        text = [f"The bead and the {fmt(cap.c_f, 'F')} capacitor resonate near {fmt(f0, 'Hz')} and peak at "
                f"{fmt(peak_db, 'dB')} at {fmt(f_pk, 'Hz')}; {q_text}."]
    else:
        text = [f"The bead and the {fmt(cap.c_f, 'F')} capacitor have no resonant peak: the most gain anywhere is "
                f"{fmt(peak_db, 'dB')}, at {fmt(f_pk, 'Hz')}, and {q_text}."]
    want_q = (Key("q_damping", f"{fmt(q_limit)} or less"),) if math.isfinite(q) else ()
    if worst is not None and worst[0] > peak_limit_db:
        text.append(f"Near harmonic {worst[3]} of the {fmt(worst[4], 'Hz')} switcher the gain is "
                    f"{fmt(worst[0], 'dB')}, so switching noise is amplified, not filtered.")
        text.append(f"We want {fmt(peak_limit_db, 'dB')} or less there; a {fmt(opts['cd'], 'F')} capacitor with "
                    f"{fmt(opts['rd_opt'], 'ohm')} in series damps it.")
        key = (Key("peak_near_switcher", f"{fmt(peak_limit_db, 'dB')} or less"), Key("peak")) + want_q
    elif underdamped:
        where = (f"The peak is away from the {fs_text} switching frequencies" if f_switch_hz
                 else "No switching frequencies were given")
        text.append(f"{where}, but we want a damping Q of {fmt(q_limit)} or less ({fmt(peak_limit_db, 'dB')}), so the "
                    f"filter needs damping. It will ring on load steps and amplify noise near {fmt(f_pk, 'Hz')}.")
        key = want_q + (Key("peak", f"{fmt(peak_limit_db, 'dB')} or less"), Key("f_peak"))
    else:
        if modeled:
            span = (fmt(min(modeled), "Hz") if len(modeled) == 1
                    else f"{fmt(min(modeled), 'Hz')} to {fmt(max(modeled), 'Hz')}")
            text.append(f"That is under the {fmt(peak_limit_db, 'dB')} limit only for the assumed bead model. The "
                        f"bead is not characterized at {span}; the vendor R/X curve or a measurement settles it.")
        else:
            text.append(f"That stays under the {fmt(peak_limit_db, 'dB')} limit"
                        + (f", with switching at {fs_text}." if f_switch_hz else "."))
        key = (Key("peak", f"{fmt(peak_limit_db, 'dB')} or less"), Key("f_peak")) + want_q
    inputs = {
        "bead_l_low": Quantity(l_low, "H", label="Bead inductance at low frequency"),
        "c": Quantity(cap.c_f, "F", "use the DC-bias derated value", "Capacitance"),
        "c_esr": Quantity(cap.esr_ohm, "ohm", label="Capacitor ESR"),
        "c_esl": Quantity(cap.esl_h, "H", label="Capacitor ESL"),
        "z_source": Quantity(z_source_ohm, "ohm", label="Source impedance"),
        "r_load": Quantity(r_load_ohm, "ohm", label="Load resistance"),
        "peak_limit": Quantity(peak_limit_db, "dB", label="Peak limit"),
        "harmonics": Quantity(harmonics, "count", label="Harmonics checked"),
        "window": Quantity(window_frac, "", "fraction of each harmonic", "Window around each harmonic"),
        "f_min": Quantity(f_min_hz, "Hz", label="Sweep start"),
        "f_max": Quantity(f_max_hz, "Hz", label="Sweep stop"),
        "points_per_decade": Quantity(points_per_decade, "count", label="Points per decade"),
        **{f"bead_{k}": q for k, q in bead.params().items()},
    }
    for i, d in enumerate(dampers):
        inputs[f"damper{i + 1}_r"] = Quantity(d.esr_ohm, "ohm", label=f"Damper {i + 1} resistance")
        inputs[f"damper{i + 1}_c"] = Quantity(d.c_f, "F", label=f"Damper {i + 1} capacitance")
        inputs[f"damper{i + 1}_esl"] = Quantity(d.esl_h, "H", label=f"Damper {i + 1} ESL")
    for i, fs in enumerate(f_switch_hz):
        inputs[f"f_switch{i + 1}"] = Quantity(fs, "Hz", label="Switching frequency" + (f" {i + 1}" if len(f_switch_hz) > 1
                                                                                         else ""))
    assumptions = [
        "source is an ideal voltage behind z_source; load is a resistor (or open)",
        "flag window is +-30 % around each switching harmonic" if window_frac == 0.30 else f"flag window +-{window_frac:.0%}",
    ]
    if bead.note:
        assumptions.insert(0, bead.note)
    fsw_marks = [Marker(f"fsw {si_text(fs, 'Hz')}", x=fs) for fs in f_switch_hz]
    h_marks = [Marker(f"limit {peak_limit_db:g} dB", y=peak_limit_db, unit="dB"),
               Marker(f"peak {h_db[i_pk]:.1f} dB", x=float(f[i_pk]), y=float(h_db[i_pk]), unit="dB")]
    if worst is not None and worst[2] != f[i_pk]:
        h_marks.append(Marker(f"{worst[0]:.1f} dB at harmonic {worst[3]}", x=float(worst[2]), y=float(worst[0]),
                              unit="dB"))
    z_mag = np.abs(zout)
    h_caption = (f"Look at the peak: {fmt(peak_db, 'dB')} at {fmt(f_pk, 'Hz')} against the "
                 f"{fmt(peak_limit_db, 'dB')} limit line"
                 + (f"; the vertical lines mark the switching frequencies, {fs_text}." if f_switch_hz else "."))
    z_caption = (f"The impedance seen from the load peaks at {fmt(float(z_mag[i_z]), 'ohm')} at {fmt(float(f[i_z]), 'Hz')}"
                 + (" with the damper fitted." if dampers else
                    f"; a {fmt(opts['cd'], 'F')} and {fmt(opts['rd_opt'], 'ohm')} damper would hold it near "
                    f"{fmt(opts['zout_peak_opt'], 'ohm')}."))
    plots = (
        plot_from_arrays("Filter transfer, source to load", "Frequency", "Hz", f, [("Transfer", "dB", h_db)],
                         x_log=True, markers=fsw_marks + h_marks, caption=h_caption),
        plot_from_arrays("Impedance seen from the load", "Frequency", "Hz", f, [("|Zout|", "ohm", z_mag)],
                         x_log=True, y_log=True,
                         markers=fsw_marks + [Marker(f"peak {si_text(float(z_mag[i_z]), 'ohm')}", x=float(f[i_z]),
                                                     y=float(z_mag[i_z]), unit="ohm")], caption=z_caption),
    )
    return Result(
        name="bead + capacitor filter",
        formula=(
            "H = Zsh/(Zs + Zbead + Zsh), Zsh = Zc || dampers || Rload; Zout = (Zs + Zbead) || Zsh; "
            "f0 = 1/(2 pi sqrt(L C)); R0 = sqrt(L/C); Q = R0/R_total, R_total = Re Zbead(f0) + ESR + Zs; Rd_opt = R0*sqrt((2+n)(4+3n)/(2 n^2 (4+n))), "
            "Zout_peak = R0*sqrt(2(2+n))/n, n = Cd/C"
        ),
        inputs=inputs,
        outputs=outputs,
        verdict=verdict,
        reason=reason,
        refs=(ERICKSON,) + tuple(refs),
        assumptions=tuple(assumptions),
        plots=plots,
        summary=" ".join(text),
        key=key,
    )
