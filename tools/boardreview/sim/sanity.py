"""Checks to pass before trusting a simulation. Each rule comes from a real mistake in a past investigation."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from boardreview.calc.base import Quantity, Result, Verdict
from boardreview.sim import measure
from boardreview.sim.netlist import (
    Element,
    Netlist,
    is_encrypted,
    norm_name,
    parse_netlist,
    parse_value,
    resolve_lib,
    subckt_pins_in_file,
    symbol_pins,
)

CRITICAL_PIN = re.compile(r"^(v?fb|rt|ith|comp|run|en|ss|track|vin|sw|boost|bst|von|intvcc|mode|sync|ilim|vc|freq)",
                          re.I)
_DC_OPEN = set("CIGFK")
_TRAN_FLAGS = {"startup", "uic", "steady", "nodiscard", "step", "noopiter"}


@dataclass(frozen=True)
class Issue:
    rule: str
    severity: str
    message: str
    where: str = ""

    def __str__(self) -> str:
        return f"[{self.severity}] {self.rule}: {self.message}"


@dataclass
class SanityReport:
    issues: list[Issue] = field(default_factory=list)
    results: list[Result] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def ok(self) -> bool:
        """No error issue and no failed numeric check."""
        return not self.errors and all(r.verdict is not Verdict.FAIL for r in self.results)

    def rules(self, severity: str | None = None) -> set[str]:
        return {i.rule for i in self.issues if severity is None or i.severity == severity}

    def extend(self, other: SanityReport) -> SanityReport:
        self.issues += other.issues
        self.results += other.results
        return self

    def to_markdown(self) -> str:
        head = "**Simulation sanity**: " + ("pass" if self.ok else "DO NOT TRUST THIS RUN YET")
        lines = [head]
        order = {"error": 0, "warning": 1, "info": 2}
        lines += [f"- {i}" for i in sorted(self.issues, key=lambda i: order.get(i.severity, 3))]
        lines += ["", *[r.to_markdown() for r in self.results]] if self.results else []
        return "\n".join(lines)


def check_netlist(source: str | Path | Netlist, allow_open: tuple[str, ...] | list[str] | set[str] = (),
                  lib_dirs: list[Path] | None = None, expected_fsw_hz: float | None = None) -> SanityReport:
    """Static checks: open terminals, floating subcircuit pins, DC paths, model files, pin counts, time step."""
    nl = source if isinstance(source, Netlist) else parse_netlist(source)
    report = SanityReport()
    lib_issues, pin_info = model_files(nl, lib_dirs)
    nl.elements = [_with_pin_names(e, pin_info) for e in nl.elements]
    dangling, issues = dangling_terminals(nl, allow_open)
    report.issues += issues
    report.issues += shorted_elements(nl)
    report.issues += no_dc_path(nl, skip=dangling)
    report.issues += lib_issues
    if expected_fsw_hz:
        report.issues += tran_resolution(nl, expected_fsw_hz)
    return report


def _with_pin_names(el: Element, pin_info: dict[str, tuple[str | None, ...]]) -> Element:
    if el.kind != "X" or el.pin_names or not el.model or el.model.lower() not in pin_info:
        return el
    names = pin_info[el.model.lower()]
    return replace(el, pin_names=tuple(n or "" for n in names))


def _allowed(el: Element, i: int, node: str, allow: set[str]) -> bool:
    pin = el.pin_names[i].lower() if el.pin_names and i < len(el.pin_names) and el.pin_names[i] else None
    name = norm_name(el.name).lower()
    keys = {node.lower(), f"{name}.{i + 1}"}
    if pin:
        keys |= {pin, f"{name}.{pin}"}
    return bool(keys & allow)


def dangling_terminals(nl: Netlist, allow_open: tuple[str, ...] | list[str] | set[str] = ()) -> tuple[set[str], list[Issue]]:
    """Every terminal must reach at least one other element. MP_ nodes are LTspice's internally tied duplicates."""
    allow = {a.replace("§", "").lower() for a in allow_open}
    issues: list[Issue] = []
    dangling: set[str] = set()
    for node, terms in nl.node_map().items():
        if nl.is_ground(node) or len({t[0].name for t in terms}) > 1:
            continue
        el = terms[0][0]
        if el.kind == "X" and node.startswith("mp_"):
            continue
        dangling.add(node)
        pins = [i for _, i in terms]
        shown = el.nodes[pins[0]]
        if all(_allowed(el, i, node, allow) for i in pins):
            issues.append(Issue("open-pin", "info", f"{_pin_list(el, pins)} on {shown} is declared open", el.name))
        else:
            issues.append(Issue("open-pin", "error", _open_message(el, pins, shown), el.name))
    return dangling, issues


def _pin_list(el: Element, pins: list[int]) -> str:
    sensed = " (and read in its expression)" if -1 in pins else ""
    pins = [i for i in pins if i >= 0]
    if not pins:
        return f"{el.name} expression"
    if el.kind == "X":
        return f"{el.name} " + ", ".join(el.pin_label(i) for i in pins) + sensed
    return f"{el.name} terminal " + ", ".join(str(i + 1) for i in pins) + sensed


def _open_message(el: Element, pins: list[int], node: str) -> str:
    msg = f"{_pin_list(el, pins)} is on node {node}, which reaches no other element"
    if node.lower().startswith("nc_"):
        msg += " (LTspice names an unconnected pin NC_)"
    names = [el.pin_names[i] for i in pins if el.pin_names and i < len(el.pin_names) and el.pin_names[i]]
    critical = [n for n in names if CRITICAL_PIN.match(n)]
    if el.kind == "X" and critical and re.match(r"^(rt|freq)", critical[0], re.I):
        msg += (f". {critical[0]} sets the switching frequency; an RT wire that missed its pin once ran a model at"
                " 747 kHz instead of 1.187 MHz")
    elif el.kind == "X" and critical:
        msg += (f". {critical[0]} sets how the model behaves; floating second-channel pins once gave a false"
                " 'oscillates' result")
    elif el.kind in "RCL":
        msg += (". The part is not in the circuit; a timing resistor drawn short of its pin once ran a model at"
                " 747 kHz instead of 1.187 MHz")
    return msg + ". Connect it or declare it open."


def shorted_elements(nl: Netlist) -> list[Issue]:
    """Two-terminal parts with both ends on one node do nothing."""
    out = []
    for el in nl.elements:
        if el.kind in "RCLDVI" and len(el.nodes) == 2 and el.nodes[0].lower() == el.nodes[1].lower():
            out.append(Issue("shorted-part", "warning", f"{el.name} has both terminals on {el.nodes[0]}", el.name))
    return out


def no_dc_path(nl: Netlist, skip: set[str] | None = None) -> list[Issue]:
    """Nodes that reach ground only through capacitors or current sources float at DC."""
    parent: dict[str, str] = {}

    def find(a: str) -> str:
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    nodes = nl.node_map()
    for n in nodes:
        find(n)
        if nl.is_ground(n):
            union(n, "0")
    find("0")
    for el in nl.elements:
        conducting = list(el.nodes)
        if el.kind in _DC_OPEN:
            continue
        if el.kind in "EH":
            conducting = list(el.nodes[:2])
        if el.kind == "B" and "i" in el.params:
            continue
        for a in conducting[1:]:
            union(conducting[0].lower(), a.lower())
    ground = find("0")
    floating = sorted(n for n in nodes if find(n) != ground and n not in (skip or set()))
    if not floating:
        return []
    return [Issue("no-dc-path", "warning",
                  "no DC path to ground (only capacitors or current sources): " + ", ".join(floating), "")]


def model_files(nl: Netlist, lib_dirs: list[Path] | None = None) -> tuple[list[Issue], dict[str, tuple[str | None, ...]]]:
    """Every .lib/.include must exist, and every X line must match its subcircuit's pin count."""
    issues: list[Issue] = []
    base = nl.path.parent if nl.path else None
    plain: list[Path] = []
    encrypted: list[Path] = []
    for line_no, name in nl.libs:
        p = resolve_lib(name, base, lib_dirs)
        if p is None:
            issues.append(Issue("model-file", "error",
                                f"line {line_no}: {name} not found next to the netlist or in LTspice lib/sub, lib/cmp",
                                name))
        elif is_encrypted(p):
            encrypted.append(p)
        else:
            plain.append(p)
    pin_info: dict[str, tuple[str | None, ...]] = {}
    for el in nl.elements:
        if el.kind != "X" or not el.model:
            continue
        pins, source = _subckt_pins(nl, el.model, plain, lib_dirs)
        if pins is None:
            sev = "warning" if encrypted or not nl.libs else "error"
            issues.append(Issue("subckt-pins", sev, f"{el.name}: cannot find subcircuit {el.model} to check its pins",
                                el.name))
            continue
        pin_info[el.model.lower()] = pins
        if len(pins) != len(el.nodes):
            issues.append(Issue("subckt-pins", "error",
                                f"{el.name} has {len(el.nodes)} nodes but {el.model} has {len(pins)} pins ({source})",
                                el.name))
        if el.pin_names and len(el.pin_names) != len(el.nodes):
            issues.append(Issue("subckt-pins", "error",
                                f"{el.name}: back-annotated pin list has {len(el.pin_names)} names for "
                                f"{len(el.nodes)} nodes", el.name))
    for p in encrypted:
        issues.append(Issue("model-file", "info", f"{p.name} is encrypted; pin counts come from the symbol", str(p)))
    return issues, pin_info


def _subckt_pins(nl: Netlist, name: str, plain: list[Path],
                 lib_dirs: list[Path] | None) -> tuple[tuple[str | None, ...] | None, str]:
    sub = nl.subckts.get(name.lower())
    if sub is not None:
        return sub.pins, "defined in the netlist"
    for p in plain:
        pins = subckt_pins_in_file(p, name)
        if pins is not None:
            return pins, f"from {p.name}"
    found = symbol_pins(name, lib_dirs)
    if found is not None and found[1]:
        return found[1], f"from symbol {found[0].name}"
    return None, ""


def tran_time_args(nl: Netlist) -> dict[str, float] | None:
    """Numbers of the first .tran: tstep, tstop, tstart, dtmax (missing ones are absent)."""
    trans = nl.directive(".tran")
    if not trans:
        return None
    toks = [t for t in trans[0].split()[1:] if t.lower() not in _TRAN_FLAGS]
    vals = [parse_value(t) for t in toks]
    vals = [v for v in vals if v is not None]
    if len(vals) == 1:
        return {"tstop": vals[0]}
    keys = ("tstep", "tstop", "tstart", "dtmax")
    return dict(zip(keys, vals))


def tran_resolution(nl: Netlist, fsw_hz: float, points_per_period: int = 20) -> list[Issue]:
    """A switching transient needs a max time step of at most 1/20 of the switching period."""
    args = tran_time_args(nl)
    if args is None:
        return []
    limit = 1.0 / (fsw_hz * points_per_period)
    if "dtmax" not in args:
        return [Issue("tran-step", "warning",
                      f".tran has no max step; set one at or below {limit:.3g} s for {fsw_hz:.4g} Hz switching", "")]
    if args["dtmax"] > limit:
        return [Issue("tran-step", "warning",
                      f".tran max step {args['dtmax']:.3g} s is coarser than {limit:.3g} s (1/{points_per_period} "
                      f"of the switching period)", "")]
    return []


def up_slew(vin_v: float, d_max: float, vout_v: float, l_h: float) -> float:
    """Largest inductor current up-slope, A/s: (VIN Dmax - VOUT) / L."""
    return (vin_v * d_max - vout_v) / l_h


def slew_limited_amplitude(slew_a_per_s: float, f_hz: float, c_out_f: float) -> float:
    """Largest output sine amplitude the inductor can follow: S / ((2 pi f)^2 C)."""
    return slew_a_per_s / ((2 * math.pi * f_hz) ** 2 * c_out_f)


def injection_slew_check(amplitude_v: float, f_hz: float, slew_a_per_s: float, c_out_f: float,
                         margin: float = 0.5) -> Result:
    """An injected or measured output sine above S/((2 pi f)^2 C) slew-limits the inductor and fakes the loop gain."""
    a_max = slew_limited_amplitude(slew_a_per_s, f_hz, c_out_f)
    ratio = amplitude_v / a_max
    if ratio > 1:
        verdict, reason = Verdict.FAIL, f"{amplitude_v * 1e3:.3g} mV exceeds the {a_max * 1e3:.3g} mV slew limit"
    elif ratio > margin:
        verdict, reason = Verdict.MARGINAL, f"{ratio:.0%} of the slew limit; halve the amplitude to be safe"
    else:
        verdict, reason = Verdict.PASS, f"{ratio:.0%} of the slew limit"
    return Result(
        name="injection amplitude vs inductor slew",
        formula="A_max = S_up / ((2 pi f)^2 C_out); S_up = (VIN Dmax - VOUT) / L",
        inputs={"A": Quantity(amplitude_v, "V"), "f": Quantity(f_hz, "Hz"),
                "S_up": Quantity(slew_a_per_s, "A/s"), "C_out": Quantity(c_out_f, "F")},
        outputs={"A_max": Quantity(a_max, "V"), "A/A_max": Quantity(ratio, "")},
        verdict=verdict,
        reason=reason,
        assumptions=("the output sine is carried by C_out alone", "S_up is the inductor's largest up-slope"),
    )


def switching_frequency_check(t: np.ndarray, v_sw: np.ndarray, expected_hz: float, tol: float = 0.05,
                              t_start_s: float | None = None, label: str = "SW") -> Result:
    """Measured switching frequency against the value the RT/ FREQ network should give."""
    sw = measure.switching_frequency(t, v_sw, t_start_s=t_start_s)
    err = sw.f_hz / expected_hz - 1
    if abs(err) > tol:
        verdict = Verdict.FAIL
        reason = (f"{sw.f_hz / 1e3:.1f} kHz is {err:+.1%} from {expected_hz / 1e3:.1f} kHz; check the RT/FREQ "
                  "network wiring before reading anything else from this run")
    elif not sw.regular:
        verdict = Verdict.MARGINAL
        reason = f"period varies {sw.period_cv:.0%}: pulse skipping, burst or a limit cycle"
    else:
        verdict, reason = Verdict.PASS, f"{err:+.1%} from expected"
    return Result(
        name=f"switching frequency at {label}",
        formula="f_sw = (N_edges - 1) / (t_last - t_first), rising crossings of the mid level",
        inputs={"expected": Quantity(expected_hz, "Hz"), "tol": Quantity(tol, "")},
        outputs={"f_sw": Quantity(sw.f_hz, "Hz"), "error": Quantity(err, ""),
                 "period_cv": Quantity(sw.period_cv, ""), "duty": Quantity(sw.duty, ""),
                 "edges": Quantity(sw.n_edges, "")},
        verdict=verdict,
        reason=reason,
    )


def edge_resolution_check(t: np.ndarray, v_sw: np.ndarray, t_start_s: float | None = None,
                          max_frac: float = 2e-3, label: str = "SW") -> Result:
    """Switch edges must be resolved in time; a PWM edge pinned to the max time step quantizes the duty cycle."""
    unc, period = measure.edge_timing_uncertainty(t, v_sw, t_start_s)
    frac = unc / period if period and period == period else float("nan")
    if frac != frac:
        verdict, reason = Verdict.UNKNOWN, "no regular edges to measure"
    elif frac > max_frac:
        verdict = Verdict.MARGINAL
        reason = (f"edges land on a {unc * 1e9:.3g} ns time grid, {frac:.2%} of the period: the duty cycle is "
                  "quantized, so modulator gain and loop gain are not trustworthy. Lower the max step or let the "
                  "model place its own breakpoints")
    else:
        verdict, reason = Verdict.PASS, f"edge timing within {frac:.3%} of the period"
    return Result(
        name=f"switch edge resolution at {label}",
        formula="u = time step at edges that jump between two samples; u / T_sw <= 0.2 percent",
        inputs={"T_sw": Quantity(period, "s")},
        outputs={"u": Quantity(unc, "s"), "u/T_sw": Quantity(frac, "")},
        verdict=verdict,
        reason=reason,
    )


def check_log(run) -> SanityReport:
    """Errors, warnings and notes from a RunResult's log, and libraries the netlist named but the run did not load."""
    report = SanityReport()
    for p in run.problems():
        report.issues.append(Issue("run", "error", p, run.netlist.name))
    for w in run.log.warnings:
        report.issues.append(Issue("log", "warning", w, run.netlist.name))
    for n in run.log.notes:
        report.issues.append(Issue("log", "info", n, run.netlist.name))
    if run.log.files_loaded and run.netlist.exists():
        loaded = {Path(f).name.lower() for f in run.log.files_loaded}
        for _, name in parse_netlist(run.netlist).libs:
            if Path(name).name.lower() not in loaded:
                report.issues.append(Issue("model-file", "warning", f"{name} is in the netlist but not in the log's "
                                           "'Files loaded' list", name))
    return report


def check_run(run, sw_node: str | None = None, expected_fsw_hz: float | None = None,
              t_start_s: float | None = None, fsw_tol: float = 0.05) -> SanityReport:
    """Log checks plus the switching frequency of every step of a transient run."""
    report = check_log(run)
    if not run.ok or not (sw_node and expected_fsw_hz):
        return report
    raw = run.raw()
    if "transient" not in raw.plotname.lower():
        return report
    for k in range(raw.n_steps):
        label = sw_node if raw.n_steps == 1 else f"{sw_node}, step {k + 1} {raw.step_params[k] if raw.step_params else ''}"
        t, v = raw.axis(step=k), raw.get(sw_node, step=k)
        try:
            report.results.append(switching_frequency_check(t, v, expected_fsw_hz, fsw_tol, t_start_s, label.strip()))
        except ValueError as exc:
            report.issues.append(Issue("fsw", "error", f"{label}: {exc}", sw_node))
            continue
        res = edge_resolution_check(t, v, t_start_s, label=label.strip())
        if res.verdict is not Verdict.PASS:
            report.results.append(res)
    return report
