"""Ready setups a reviewer fills in: loop gain by injection, load step, start-up ramp, PDN or filter impedance."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from boardreview.calc.base import Quantity, Result, Verdict
from boardreview.sim import measure
from boardreview.sim.netlist import GROUND, Element, norm_name, parse_netlist, read_netlist_text
from boardreview.sim.runner import RunResult, run, run_many
from boardreview.sim.sanity import (
    Issue,
    SanityReport,
    check_netlist,
    check_run,
    injection_slew_check,
    trusted_verdict,
    verdict_line,
    worst,
)

ANALYSES = (".tran", ".ac", ".op", ".dc", ".noise", ".tf", ".four", ".fra", ".end", ".backanno", ".step", ".meas",
            ".measure", ".save", ".wave")
INJ_NODE = "lg_a"
INJ_SOURCE = "Vbr_inj"
STEP_SOURCE = "Ibr_step"
RAMP_SOURCE = "Vbr_ramp"


def body_from_netlist(source: str | Path) -> str:
    """Circuit lines of a netlist without its title, analyses, .step, .meas, .save and .end (models and .lib stay)."""
    is_file = isinstance(source, Path) or ("\n" not in str(source) and Path(str(source)).exists())
    text = read_netlist_text(source) if is_file else str(source)
    lines = text.replace("\r\n", "\n").split("\n")[1:]
    out = []
    skipping = False
    for line in lines:
        s = line.strip()
        word = s.split()[0].lower() if s else ""
        if s.startswith("+") and skipping:
            continue
        skipping = word in ANALYSES
        if not skipping:
            out.append(line)
    return "\n".join(out).strip("\n")


def _find_line(lines: list[str], element: str) -> int:
    key = norm_name(element)
    hits = [i for i, ln in enumerate(lines) if ln.strip() and norm_name(ln.split()[0]) == key]
    if len(hits) != 1:
        raise KeyError(f"element {element} found {len(hits)} times in the body")
    return hits[0]


def replace_node(body: str, element: str, old_node: str, new_node: str) -> str:
    """Move the terminal of a two-terminal element that sits on old_node to new_node."""
    lines = body.split("\n")
    i = _find_line(lines, element)
    toks = lines[i].split()
    pos = [k for k in (1, 2) if k < len(toks) and toks[k].lower() == old_node.lower()]
    if len(pos) != 1:
        raise ValueError(f"{element} must have exactly one terminal on {old_node}: {lines[i].strip()}")
    toks[pos[0]] = new_node
    lines[i] = " ".join(toks)
    return "\n".join(lines)


def remove_element(body: str, element: str) -> tuple[str, list[str]]:
    """Drop one element line (and its + continuations); return the body and the element's tokens."""
    lines = body.split("\n")
    i = _find_line(lines, element)
    toks = lines[i].split()
    j = i + 1
    while j < len(lines) and lines[j].strip().startswith("+"):
        j += 1
    return "\n".join(lines[:i] + lines[j:]), toks


def _is_branch(el: Element) -> bool:
    return len(el.nodes) == 2 and el.kind in "RCLDX"


def feedback_branches(body: str, top_resistor: str, out_node: str) -> tuple[str, list[str], list[str]]:
    """Feedback node, two-terminal parts joining out_node to the feedback network, and other paths between them."""
    nl = parse_netlist("* body\n" + body)
    out = out_node.lower()
    top = [e for e in nl.elements if norm_name(e.name) == norm_name(top_resistor)]
    if len(top) != 1 or len(top[0].nodes) != 2 or [n.lower() for n in top[0].nodes].count(out) != 1:
        raise ValueError(f"{top_resistor} must be one two-terminal part with one end on {out_node}")
    fb = next(n.lower() for n in top[0].nodes if n.lower() != out)
    nodes = nl.node_map()
    reached, todo = {fb}, [fb]
    while todo:
        for el, i in nodes.get(todo.pop(), []):
            if i < 0 or not _is_branch(el):
                continue
            for n in (m.lower() for m in el.nodes):
                if n not in reached and n != out and n not in GROUND:
                    reached.add(n)
                    todo.append(n)
    moves, blockers = [], []
    for el in nl.elements:
        pins = {n.lower() for n in el.nodes}
        touched = pins | {n.lower() for n in el.sensed}
        if out not in touched or not touched & reached:
            continue
        if _is_branch(el) and out in pins:
            moves.append(el.name)
        elif not (el.kind == "X" and len(el.nodes) > 2):
            blockers.append(el.name)
    return fb, moves, blockers


def _check_free(body: str, *names: str) -> None:
    """Refuse to add an element whose name the reviewer's body already uses."""
    taken = {norm_name(ln.split()[0]) for ln in body.split("\n")
             if ln.strip() and not ln.strip().startswith(("*", ".", "+", ";"))}
    clash = [n for n in names if norm_name(n) in taken]
    if clash:
        raise ValueError(f"the body already has {', '.join(clash)}; rename it")


def _fmt(x: float) -> str:
    return f"{x:.6g}"


def _tran(t_stop_s: float, max_step_s: float, flags: str = "") -> str:
    return f".tran 0 {_fmt(t_stop_s)} 0 {_fmt(max_step_s)} {flags}".rstrip()


def _save(nodes: list[str | None]) -> str:
    seen = []
    for n in nodes:
        if n and n.lower() not in [s.lower() for s in seen]:
            seen.append(n)
    return ".save " + " ".join(f"V({n})" for n in seen)


def injection_frequencies(f_start_hz: float, f_stop_hz: float, n: int, fsw_hz: float,
                          min_frac: float = 0.25) -> list[float]:
    """Log-spaced injection frequencies moved off f = fsw/k, where the converter can lock to the injection."""
    out = [_off_subharmonic(float(f), fsw_hz, min_frac)
           for f in np.logspace(math.log10(f_start_hz), math.log10(f_stop_hz), n)]
    return sorted(set(out))


def subharmonic_fraction(f_hz: float, fsw_hz: float) -> float:
    """Distance of fsw/f from the nearest integer (0 means f = fsw/k exactly)."""
    x = fsw_hz / f_hz
    return abs(x - round(x))


@dataclass
class LoopGainSetup:
    """Middlebrook injection in series with the top feedback resistor: T = -V(b)/V(a), a = lg_a, b = output."""

    body: str
    top_resistor: str
    out_node: str
    fsw_hz: float
    c_out_f: float
    slew_a_per_s: float
    sw_node: str | None = None
    amplitude_v: float = 2e-3
    t_settle_s: float = 300e-6
    n_settle_periods: int = 3
    n_meas_periods: int = 6
    max_step_s: float | None = None
    tran_flags: str = "startup"
    extra: str = ""
    allow_open: tuple[str, ...] = ()
    save: tuple[str, ...] = ()

    @property
    def dtmax(self) -> float:
        return self.max_step_s or 1.0 / (50.0 * self.fsw_hz)

    def t_stop(self, f_hz: float) -> float:
        return self.t_settle_s + (self.n_settle_periods + self.n_meas_periods) / f_hz

    def branches(self) -> list[str]:
        """Parts moved from out_node to the injection node: top_resistor and every other feedback branch."""
        fb, moves, blockers = feedback_branches(self.body, self.top_resistor, self.out_node)
        if blockers:
            raise ValueError(f"{', '.join(blockers)} joins {self.out_node} to the feedback network at {fb} without "
                             f"passing the injection point, so the measured T would not be the loop gain. Move its "
                             f"{self.out_node} side to {INJ_NODE} by hand or inject elsewhere")
        return moves

    def _opened(self) -> str:
        _check_free(self.body, INJ_SOURCE)
        body = self.body
        for name in self.branches():
            body = replace_node(body, name, self.out_node, INJ_NODE)
        return body

    def netlist(self, f_hz: float) -> str:
        """Transient netlist with a sine of amplitude_v at f_hz switched on at t_settle_s."""
        sine = f"SINE(0 {_fmt(self.amplitude_v)} {_fmt(f_hz)} {_fmt(self.t_settle_s)})"
        return "\n".join([
            f"* loop gain injection at {_fmt(f_hz)} Hz, T = -V({self.out_node})/V({INJ_NODE})",
            self._opened(),
            f"{INJ_SOURCE} {INJ_NODE} {self.out_node} {sine}",
            self.extra,
            _save([INJ_NODE, self.out_node, self.sw_node, *self.save]),
            ".options plotwinsize=0",
            _tran(self.t_stop(f_hz), self.dtmax, self.tran_flags),
            ".end",
        ])

    def ac_netlist(self, f_start_hz: float, f_stop_hz: float, points_per_decade: int = 20) -> str:
        """Small-signal version for averaged or linear models: AC 1 V injection, same nodes."""
        return "\n".join([
            f"* loop gain, AC injection, T = -V({self.out_node})/V({INJ_NODE})",
            self._opened(),
            f"{INJ_SOURCE} {INJ_NODE} {self.out_node} AC 1",
            self.extra,
            f".ac dec {points_per_decade} {_fmt(f_start_hz)} {_fmt(f_stop_hz)}",
            ".end",
        ])

    def check(self, freqs: list[float]) -> SanityReport:
        """Static checks before a sweep: netlist, injection slew limit, f = fsw/k, and f against fsw."""
        rep = check_netlist(self.netlist(freqs[0]), allow_open=self.allow_open, expected_fsw_hz=self.fsw_hz)
        rep.issues.append(Issue("injection", "info", f"moved to {INJ_NODE}: {', '.join(self.branches())}"))
        for f in freqs:
            res = injection_slew_check(self.amplitude_v, f, self.slew_a_per_s, self.c_out_f)
            if res.verdict is not Verdict.PASS:
                rep.results.append(res)
            if subharmonic_fraction(f, self.fsw_hz) < 0.1:
                rep.issues.append(Issue("injection", "warning",
                                        f"{f:.4g} Hz is within 10 percent of fsw/{round(self.fsw_hz / f)}; the "
                                        "converter can lock to the injection"))
            if f > self.fsw_hz / 5:
                rep.issues.append(Issue("injection", "warning",
                                        f"{f:.4g} Hz is above fsw/5; a switching loop gain is not meaningful there"))
        return rep


@dataclass(frozen=True)
class LoopGainPoint:
    f_hz: float
    t: complex
    va: complex
    vb: complex
    fsw_hz: float | None

    @property
    def mag_db(self) -> float:
        return 20 * math.log10(abs(self.t))

    @property
    def phase_deg(self) -> float:
        return math.degrees(np.angle(self.t))


@dataclass
class LoopGainResult:
    points: list[LoopGainPoint]
    margins: measure.LoopMargins | None
    report: SanityReport
    runs: list[RunResult] = field(default_factory=list)

    @property
    def f_hz(self) -> np.ndarray:
        return np.array([p.f_hz for p in self.points])

    @property
    def t(self) -> np.ndarray:
        return np.array([p.t for p in self.points])

    def margins_result(self, pm_min_deg: float = 45.0, gm_min_db: float = 6.0) -> Result | None:
        if self.margins is None:
            return None
        return measure.margins_result(self.margins, pm_min_deg, gm_min_db,
                                      f"{len(self.points)} injection points, transient")

    @property
    def results(self) -> list[Result]:
        """Measured results: the loop margins, or why there are none."""
        mr = self.margins_result()
        if mr is not None:
            return [mr]
        return [Result(name="loop margins", formula="needs T at two or more frequencies", inputs={}, outputs={},
                       verdict=Verdict.UNKNOWN, reason=f"{len(self.points)} measured point(s)")]

    @property
    def measured(self) -> Verdict:
        return worst((r.verdict for r in self.results), default=Verdict.UNKNOWN)

    @property
    def verdict(self) -> Verdict:
        return trusted_verdict(self.report.verdict, self.measured)

    def to_markdown(self) -> str:
        lines = ["| f (Hz) | abs T (dB) | angle T (deg) | V(b) amplitude (mV) | fsw (kHz) |", "|---|---|---|---|---|"]
        for p in self.points:
            fsw = f"{p.fsw_hz / 1e3:.1f}" if p.fsw_hz else "-"
            lines.append(f"| {p.f_hz:.4g} | {p.mag_db:.1f} | {p.phase_deg:.0f} | {abs(p.vb) * 1e3:.3g} | {fsw} |")
        for r in self.results:
            lines += ["", r.to_markdown()]
        fc = self.margins.crossover_hz if self.margins is not None else None
        if fc is not None:
            below = max((p.f_hz for p in self.points if p.f_hz <= fc), default=None)
            above = min((p.f_hz for p in self.points if p.f_hz >= fc), default=None)
            if below is not None and above is not None:
                lines.append(f"- f_c interpolated between measured points at {below:.4g} and {above:.4g} Hz")
        lines += ["", self.report.to_markdown(), "", verdict_line(self.report.verdict, self.measured)]
        return "\n".join(lines)


def measure_loop_gain_point(run_result: RunResult, setup: LoopGainSetup, f_hz: float,
                            report: SanityReport | None = None) -> LoopGainPoint:
    """Average one switching period, then lock in on f over whole periods after the settling periods."""
    raw = run_result.raw()
    t = raw.axis()
    fsw = setup.fsw_hz
    fsw_meas = None
    if setup.sw_node:
        try:
            fsw_meas = measure.switching_frequency(t, raw[setup.sw_node], t_start_s=setup.t_settle_s).f_hz
            fsw = fsw_meas
        except ValueError:
            fsw_meas = None
    t0 = setup.t_settle_s + setup.n_settle_periods / f_hz
    keep = t >= t0 - 2.0 / fsw
    ta, va = measure.box_average(t[keep], raw[INJ_NODE][keep], 1.0 / fsw)
    tb, vb = measure.box_average(t[keep], raw[setup.out_node][keep], 1.0 / fsw)
    xa = measure.lockin(ta, va, f_hz, t_start_s=t0)
    xb = measure.lockin(tb, vb, f_hz, t_start_s=t0)
    if report is not None:
        res = injection_slew_check(abs(xb), f_hz, setup.slew_a_per_s, setup.c_out_f)
        if res.verdict is not Verdict.PASS:
            report.results.append(res)
    return LoopGainPoint(f_hz=f_hz, t=-xb / xa, va=xa, vb=xb, fsw_hz=fsw_meas)


def run_loop_gain(setup: LoopGainSetup, freqs: list[float], workdir: str | Path, max_workers: int = 2,
                  timeout_s: float = 3600.0, force: bool = False, refine: int = 0, linearity: bool = False,
                  **run_kwargs: object) -> LoopGainResult:
    """Checked transients per frequency, margins, optional refinement at crossings and a linearity rerun."""
    report = setup.check(freqs)
    if report.failed and not force:
        raise ValueError("fix the setup before running (or pass force=True):\n" + report.to_markdown())
    points: list[LoopGainPoint] = []
    runs: list[RunResult] = []
    todo = list(freqs)
    for _ in range(2 if refine else 1):
        names = [f"lg_{len(runs) + i:02d}_{f:.0f}Hz" for i, f in enumerate(todo)]
        batch = run_many([setup.netlist(f) for f in todo], workdir, names, max_workers=max_workers,
                         timeout_s=timeout_s, **run_kwargs)
        for f, r in zip(todo, batch):
            report.extend(check_run(r, setup.sw_node, setup.fsw_hz, t_start_s=setup.t_settle_s))
            if r.ok:
                points.append(measure_loop_gain_point(r, setup, f, report))
        runs += batch
        points.sort(key=lambda p: p.f_hz)
        todo = refine_frequencies(points, refine, setup.fsw_hz)
        if not todo:
            break
    margins = measure.loop_margins([p.f_hz for p in points], [p.t for p in points]) if len(points) > 1 else None
    report.issues += _loop_plausibility(points)
    if linearity and margins is not None and margins.crossover_hz is not None:
        f_lin = _off_subharmonic(margins.crossover_hz, setup.fsw_hz)
        report.results.append(linearity_check(setup, f_lin, workdir, max_workers=max_workers, timeout_s=timeout_s,
                                              **run_kwargs))
    return LoopGainResult(points, margins, report, runs)


def linearity_check(setup: LoopGainSetup, f_hz: float, workdir: str | Path, ratio: float = 0.5,
                    max_db: float = 0.5, max_deg: float = 3.0, **run_kwargs: object) -> Result:
    """Rerun one frequency at a smaller amplitude; a small-signal T does not depend on the amplitude."""
    small = replace(setup, amplitude_v=setup.amplitude_v * ratio)
    runs = run_many([setup.netlist(f_hz), small.netlist(f_hz)], workdir,
                    [f"lin_full_{f_hz:.0f}Hz", f"lin_small_{f_hz:.0f}Hz"], **run_kwargs)
    if not all(r.ok for r in runs):
        return Result(name="loop gain linearity", formula="T(A) vs T(A ratio)", inputs={}, outputs={},
                      verdict=Verdict.UNKNOWN, reason="; ".join(p for r in runs for p in r.problems()))
    a = measure_loop_gain_point(runs[0], setup, f_hz)
    b = measure_loop_gain_point(runs[1], small, f_hz)
    d_db = b.mag_db - a.mag_db
    d_deg = (b.phase_deg - a.phase_deg + 180.0) % 360.0 - 180.0
    ok = abs(d_db) <= max_db and abs(d_deg) <= max_deg
    return Result(
        name="loop gain linearity",
        formula="dT = T(A ratio) / T(A); small signal if |dT| <= 0.5 dB and angle <= 3 deg",
        inputs={"f": Quantity(f_hz, "Hz"), "A": Quantity(setup.amplitude_v, "V"), "ratio": Quantity(ratio, "")},
        outputs={"d_mag": Quantity(d_db, "dB"), "d_phase": Quantity(d_deg, "deg")},
        verdict=Verdict.PASS if ok else Verdict.FAIL,
        reason="T does not depend on the amplitude" if ok else
        "T changes with the amplitude: slew limit, clipping or locking; lower the amplitude",
    )


def refine_frequencies(points: list[LoopGainPoint], n: int, fsw_hz: float) -> list[float]:
    """n new frequencies inside each interval whose ends straddle 0 dB or -180 deg, kept off fsw/k."""
    if n <= 0 or len(points) < 2:
        return []
    f = np.array([p.f_hz for p in points])
    mag = np.array([p.mag_db for p in points])
    ph = np.degrees(np.unwrap(np.angle([p.t for p in points])))
    ph -= 360.0 * np.round(ph[0] / 360.0)
    out: list[float] = []
    for i in range(len(f) - 1):
        if np.sign(mag[i]) != np.sign(mag[i + 1]) or np.sign(ph[i] + 180) != np.sign(ph[i + 1] + 180):
            inner = np.geomspace(f[i], f[i + 1], n + 2)[1:-1]
            out += [_off_subharmonic(x, fsw_hz) for x in inner]
    return sorted(set(out))


def _off_subharmonic(f_hz: float, fsw_hz: float, min_frac: float = 0.25) -> float:
    x = fsw_hz / f_hz
    k = math.floor(x)
    frac = x - k
    if k >= 1 and (frac < min_frac or frac > 1 - min_frac):
        return fsw_hz / (k + 0.5)
    return f_hz


def loop_gain_from_ac(run_result: RunResult, out_node: str, step: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """T = -V(b)/V(a) from an AC injection run of LoopGainSetup.ac_netlist."""
    raw = run_result.raw()
    return raw.axis(step), -raw.get(out_node, step) / raw.get(INJ_NODE, step)


def _loop_plausibility(points: list[LoopGainPoint]) -> list[Issue]:
    if not points:
        return [Issue("loop-gain", "error", "no injection run produced data")]
    low = min(points, key=lambda p: p.f_hz)
    out = []
    if abs(low.t) < 1:
        out.append(Issue("loop-gain", "warning", f"|T| is below 1 at the lowest frequency {low.f_hz:.4g} Hz; "
                         "start the sweep lower to see the crossover"))
    if not -200 <= low.phase_deg <= 20:
        out.append(Issue("loop-gain", "error", f"angle T is {low.phase_deg:.0f} deg at {low.f_hz:.4g} Hz; expected "
                         "0 to -180 below crossover. Check the sign (T = -V(b)/V(a)) and the injection nodes"))
    return out


@dataclass
class LoadStepSetup:
    """Load current step on the output with a set edge time; optional step back."""

    body: str
    out_node: str
    i_from_a: float
    i_to_a: float
    t_step_s: float
    t_stop_s: float
    edge_s: float = 1e-6
    t_back_s: float | None = None
    fsw_hz: float | None = None
    sw_node: str | None = None
    max_step_s: float | None = None
    tran_flags: str = "startup"
    extra: str = ""
    allow_open: tuple[str, ...] = ()
    dev_max_v: float | None = None
    settle_max_s: float | None = None

    def netlist(self) -> str:
        pts = [(0.0, self.i_from_a), (self.t_step_s, self.i_from_a), (self.t_step_s + self.edge_s, self.i_to_a)]
        if self.t_back_s is not None:
            pts += [(self.t_back_s, self.i_to_a), (self.t_back_s + self.edge_s, self.i_from_a)]
        pwl = " ".join(f"{_fmt(t)} {_fmt(i)}" for t, i in pts)
        dt = self.max_step_s or (1.0 / (50.0 * self.fsw_hz) if self.fsw_hz else self.t_stop_s / 5000)
        _check_free(self.body, STEP_SOURCE)
        return "\n".join([
            f"* load step {self.i_from_a} A -> {self.i_to_a} A, edge {_fmt(self.edge_s)} s",
            self.body,
            f"{STEP_SOURCE} {self.out_node} 0 PWL({pwl})",
            self.extra,
            ".options plotwinsize=0",
            _tran(self.t_stop_s, dt, self.tran_flags),
            ".end",
        ])


def step_results(sr: measure.StepResponse, dev_max_v: float | None = None,
                 settle_max_s: float | None = None) -> list[Result]:
    """Measured results of one edge: peak deviation, settling and ring-down."""
    return [measure.deviation_result(sr, dev_max_v), measure.settling_result(sr, settle_max_s),
            measure.ring_result(sr)]


@dataclass
class LoadStepResult:
    run: RunResult
    report: SanityReport
    steps: list[measure.StepResponse]
    results: list[Result] = field(default_factory=list)

    @property
    def measured(self) -> Verdict:
        return worst((r.verdict for r in self.results), default=Verdict.UNKNOWN)

    @property
    def verdict(self) -> Verdict:
        return trusted_verdict(self.report.verdict, self.measured)

    def to_markdown(self) -> str:
        lines = []
        per_edge = len(self.results) // len(self.steps) if self.steps else 0
        for k, sr in enumerate(self.steps):
            settle = f"settles in {sr.settle_s * 1e6:.1f} us" if sr.settle_s is not None else "not settled in window"
            lines.append(f"**edge {k + 1} at {sr.t_step_s * 1e6:.1f} us**: peak deviation "
                         f"{sr.peak_dev * 1e3:.1f} mV, {settle}")
            lines += [r.to_markdown() for r in self.results[k * per_edge:(k + 1) * per_edge]]
        lines += ["", self.report.to_markdown(), "", verdict_line(self.report.verdict, self.measured)]
        return "\n".join(lines)


def run_load_step(setup: LoadStepSetup, workdir: str | Path, name: str = "load_step", force: bool = False,
                  **run_kwargs: object) -> LoadStepResult:
    """Run the step, check the run, and measure each edge after averaging one switching period."""
    report = check_netlist(setup.netlist(), allow_open=setup.allow_open, expected_fsw_hz=setup.fsw_hz)
    if report.failed and not force:
        raise ValueError("fix the setup before running (or pass force=True):\n" + report.to_markdown())
    r = run(setup.netlist(), workdir, name, **run_kwargs)
    report.extend(check_run(r, setup.sw_node, setup.fsw_hz, t_start_s=0.5 * setup.t_step_s))
    steps = []
    if r.ok:
        raw = r.raw()
        t, v = raw.axis(), raw[setup.out_node]
        smooth = 1.0 / setup.fsw_hz if setup.fsw_hz else None
        edges = [setup.t_step_s] + ([setup.t_back_s] if setup.t_back_s is not None else [])
        ends = edges[1:] + [t[-1]]
        for t0, t1 in zip(edges, ends):
            steps.append(measure.step_response(t, v, t0, t_end_s=t1, smooth_period_s=smooth))
    results = [x for sr in steps for x in step_results(sr, setup.dev_max_v, setup.settle_max_s)]
    return LoadStepResult(r, report, steps, results)


@dataclass
class StartupSetup:
    """Input ramp from 0 V; the existing input source (if named) is replaced by the ramp on the same node."""

    body: str
    in_node: str
    out_node: str
    vin_v: float
    ramp_s: float
    t_stop_s: float
    v_target_v: float
    input_source: str | None = None
    source_r_ohm: float = 0.0
    fsw_hz: float | None = None
    sw_node: str | None = None
    max_step_s: float | None = None
    extra: str = ""
    allow_open: tuple[str, ...] = ()
    overshoot_max_pct: float = 10.0

    def netlist(self) -> str:
        body = self.body
        if self.input_source:
            body, _ = remove_element(body, self.input_source)
        _check_free(body, RAMP_SOURCE, "Rbr_source")
        src = []
        if self.source_r_ohm > 0:
            src.append(f"{RAMP_SOURCE} br_ramp 0 PWL(0 0 {_fmt(self.ramp_s)} {_fmt(self.vin_v)})")
            src.append(f"Rbr_source br_ramp {self.in_node} {_fmt(self.source_r_ohm)}")
        else:
            src.append(f"{RAMP_SOURCE} {self.in_node} 0 PWL(0 0 {_fmt(self.ramp_s)} {_fmt(self.vin_v)})")
        dt = self.max_step_s or (1.0 / (50.0 * self.fsw_hz) if self.fsw_hz else self.t_stop_s / 5000)
        return "\n".join([f"* start-up, input ramp 0 -> {self.vin_v} V in {_fmt(self.ramp_s)} s", body, *src,
                          self.extra, ".options plotwinsize=0", _tran(self.t_stop_s, dt), ".end"])


@dataclass(frozen=True)
class Startup:
    t_reg_s: float | None
    overshoot_pct: float
    restarts: int
    final_v: float
    vin_min_after_ramp_v: float
    monotonic: bool


def startup_metrics(t: np.ndarray, vout: np.ndarray, vin: np.ndarray, v_target_v: float, ramp_s: float,
                    band: float = 0.02, smooth_period_s: float | None = None) -> Startup:
    """Time to regulation, overshoot, restarts (hiccup), input sag after the ramp, monotonic rise."""
    t = np.asarray(t, dtype=float)
    tv, v = (measure.box_average(t, vout, smooth_period_s) if smooth_period_s else (t, np.asarray(vout, float)))
    inside = np.abs(v - v_target_v) <= band * v_target_v
    out_idx = np.nonzero(~inside)[0]
    t_reg = None
    if inside[-1]:
        t_reg = float(tv[out_idx[-1] + 1]) if len(out_idx) else float(tv[0])
    hi, lo = 0.9 * v_target_v, 0.5 * v_target_v
    restarts, armed = 0, False
    for x in v:
        if x >= hi:
            armed = True
        elif armed and x < lo:
            restarts += 1
            armed = False
    first_hi = np.nonzero(v >= hi)[0]
    rise = v[: first_hi[0] + 1] if len(first_hi) else v
    monotonic = bool(np.min(rise - np.maximum.accumulate(rise)) > -0.05 * v_target_v)
    after = np.asarray(t) >= ramp_s
    vin_min = float(np.min(np.asarray(vin)[after])) if after.any() else float("nan")
    return Startup(t_reg, float(max(0.0, (np.max(v) / v_target_v - 1) * 100)), restarts, float(v[-1]), vin_min,
                   monotonic)


def startup_result(m: Startup, v_target_v: float, overshoot_max_pct: float = 10.0) -> Result:
    """Start-up verdict: in regulation at the end, no restarts, overshoot within the limit, monotonic rise."""
    fails = []
    if m.t_reg_s is None:
        fails.append("never settles in the band")
    if m.restarts:
        fails.append(f"{m.restarts} restart(s): output fell below half of target after reaching 90 percent, hiccup "
                     "or UVLO cycling")
    if m.overshoot_pct > overshoot_max_pct:
        fails.append(f"overshoot {m.overshoot_pct:.0f} percent exceeds {overshoot_max_pct:.0f} percent")
    if fails:
        verdict, reason = Verdict.FAIL, "; ".join(fails)
    elif not m.monotonic:
        verdict, reason = Verdict.MARGINAL, "rise not monotonic"
    else:
        verdict, reason = Verdict.PASS, f"in regulation at {m.t_reg_s * 1e6:.0f} us"
    return Result(
        name="start-up",
        formula="t_reg = last time |Vout - Vtarget| > 2 percent; overshoot = max(Vout)/Vtarget - 1",
        inputs={"V_target": Quantity(v_target_v, "V"), "overshoot_max": Quantity(overshoot_max_pct, "%")},
        outputs={"t_reg": Quantity(m.t_reg_s if m.t_reg_s is not None else float("nan"), "s"),
                 "overshoot": Quantity(m.overshoot_pct, "%"), "restarts": Quantity(m.restarts, ""),
                 "V_final": Quantity(m.final_v, "V"), "Vin_min_after_ramp": Quantity(m.vin_min_after_ramp_v, "V")},
        verdict=verdict,
        reason=reason,
    )


@dataclass
class StartupResult:
    run: RunResult
    report: SanityReport
    metrics: Startup | None
    results: list[Result] = field(default_factory=list)

    @property
    def measured(self) -> Verdict:
        return worst((r.verdict for r in self.results), default=Verdict.UNKNOWN)

    @property
    def verdict(self) -> Verdict:
        return trusted_verdict(self.report.verdict, self.measured)

    def to_markdown(self) -> str:
        m = self.metrics
        lines = []
        if m is not None:
            t_reg = f"{m.t_reg_s * 1e6:.0f} us" if m.t_reg_s is not None else "never in band"
            lines.append(f"**start-up**: regulation at {t_reg}, overshoot {m.overshoot_pct:.1f} percent, restarts "
                         f"{m.restarts}, final {m.final_v:.3f} V, input minimum after ramp "
                         f"{m.vin_min_after_ramp_v:.3f} V, {'monotonic' if m.monotonic else 'NOT monotonic'}")
        lines += [r.to_markdown() for r in self.results]
        lines += ["", self.report.to_markdown(), "", verdict_line(self.report.verdict, self.measured)]
        return "\n".join(lines)


def run_startup(setup: StartupSetup, workdir: str | Path, name: str = "startup", force: bool = False,
                **run_kwargs: object) -> StartupResult:
    report = check_netlist(setup.netlist(), allow_open=setup.allow_open, expected_fsw_hz=setup.fsw_hz)
    if report.failed and not force:
        raise ValueError("fix the setup before running (or pass force=True):\n" + report.to_markdown())
    r = run(setup.netlist(), workdir, name, **run_kwargs)
    report.extend(check_run(r, setup.sw_node, setup.fsw_hz, t_start_s=0.8 * setup.t_stop_s))
    metrics = None
    results = []
    if r.ok:
        raw = r.raw()
        smooth = 1.0 / setup.fsw_hz if setup.fsw_hz else None
        metrics = startup_metrics(raw.axis(), raw[setup.out_node], raw[setup.in_node], setup.v_target_v,
                                  setup.ramp_s, smooth_period_s=smooth)
        results.append(startup_result(metrics, setup.v_target_v, setup.overshoot_max_pct))
    return StartupResult(r, report, metrics, results)


@dataclass(frozen=True)
class Cap:
    c_f: float
    esr_ohm: float = 0.0
    esl_h: float = 0.0
    count: int = 1
    name: str = "C"


@dataclass(frozen=True)
class Bead:
    """Ferrite bead: r_dc in series with (L || R_ac || C_par). Fit L, R_ac, C_par to the vendor Z curve."""

    r_dc_ohm: float
    l_h: float
    r_ac_ohm: float
    c_par_f: float = 0.0
    name: str = "FB"


@dataclass
class ImpedanceSetup:
    """Upstream source, optional bead or inductor, capacitors on each side; AC 1 A injected into the rail."""

    caps_rail: list[Cap]
    bead: Bead | None = None
    caps_src: list[Cap] = field(default_factory=list)
    source_r_ohm: float = 1e-3
    source_l_h: float = 0.0
    f_start_hz: float = 1e3
    f_stop_hz: float = 1e9
    points_per_decade: int = 50
    transfer: bool = False
    dialect: str = "ltspice"
    extra: str = ""

    def _l(self, name: str, a: str, b: str, value: float) -> str:
        rser = " Rser=0" if self.dialect == "ltspice" else ""
        return f"L{name} {a} {b} {_fmt(value)}{rser}"

    def _rl(self, name: str, a: str, b: str, r_ohm: float, l_h: float) -> list[str]:
        """Series R then L from a to b; the L is left out when zero."""
        r = _fmt(max(r_ohm, 1e-9))
        if l_h <= 0:
            return [f"R{name} {a} {b} {r}"]
        return [f"R{name} {a} {name}_m {r}", self._l(name, f"{name}_m", b, l_h)]

    def _caps(self, caps: list[Cap], node: str, tag: str) -> list[str]:
        lines = []
        for k, c in enumerate(caps):
            n = max(1, c.count)
            base = f"{tag}{k}"
            lines.append(f"C{base} {node} {base}_a {_fmt(c.c_f * n)}")
            lines += self._rl(base, f"{base}_a", "0", c.esr_ohm / n, c.esl_h / n)
        return lines

    def netlist(self) -> str:
        inj, src_ac = ("{inj}", "{1-inj}") if self.transfer else ("1", "0")
        lines = ["* impedance at rail by AC current injection" + (", step 2 is the transfer src->rail"
                                                               if self.transfer else "")]
        lines.append(f"Vsrc vs 0 0 AC {src_ac}")
        lines += self._rl("src", "vs", "src", self.source_r_ohm, self.source_l_h)
        lines += self._caps(self.caps_src, "src", "s")
        if self.bead is None:
            lines.append("Rlink src rail 1e-9")
        else:
            b = self.bead
            lines.append(f"R{b.name}dc src fb_m {_fmt(b.r_dc_ohm)}")
            lines.append(self._l(f"{b.name}", "fb_m", "rail", b.l_h))
            lines.append(f"R{b.name}ac fb_m rail {_fmt(b.r_ac_ohm)}")
            if b.c_par_f > 0:
                lines.append(f"C{b.name}par fb_m rail {_fmt(b.c_par_f)}")
        lines += self._caps(self.caps_rail, "rail", "r")
        lines.append(f"Iinj 0 rail 0 AC {inj}")
        if self.extra:
            lines.append(self.extra)
        if self.transfer:
            lines.append(".step param inj list 1 0")
        lines.append(f".ac dec {self.points_per_decade} {_fmt(self.f_start_hz)} {_fmt(self.f_stop_hz)}")
        lines.append(".end")
        return "\n".join(lines)


@dataclass
class ImpedanceResult:
    run: RunResult
    f_hz: np.ndarray
    z: np.ndarray
    summary: measure.ImpedanceSummary
    transfer: np.ndarray | None

    def to_markdown(self) -> str:
        s = self.summary
        lines = [f"**rail impedance**: max {s.max_z_ohm * 1e3:.1f} mOhm at {s.f_at_max_hz / 1e3:.4g} kHz"]
        for p in s.peaks:
            q = f", Q {p.q:.1f}" if p.q else ""
            lines.append(f"- peak {p.z_ohm * 1e3:.1f} mOhm at {p.f_hz / 1e3:.4g} kHz{q}")
        if s.z_target_ohm is not None:
            bands = ", ".join(f"{a / 1e3:.4g} to {b / 1e3:.4g} kHz" for a, b in s.bands_over_target_hz) or "none"
            lines.append(f"- above target {s.z_target_ohm * 1e3:.1f} mOhm: {bands}")
        if self.transfer is not None:
            g = np.abs(self.transfer)
            k = int(np.argmax(g))
            lines.append(f"- transfer src to rail peaks at {20 * math.log10(g[k]):.1f} dB "
                         f"at {self.f_hz[k] / 1e3:.4g} kHz")
        return "\n".join(lines)


def impedance_result(z_target_ohm: float | None, peak_z_ohm: float, f_hz: float) -> Result:
    """Peak rail impedance against a target impedance (V ripple allowed / transient current)."""
    verdict = Verdict.INFO if z_target_ohm is None else (Verdict.PASS if peak_z_ohm <= z_target_ohm else Verdict.FAIL)
    return Result(
        name="rail impedance peak", formula="Z = V(rail) / I_inj with I_inj = 1 A AC",
        inputs={"Z_target": Quantity(z_target_ohm if z_target_ohm is not None else float("nan"), "ohm")},
        outputs={"Z_peak": Quantity(peak_z_ohm, "ohm"), "f_peak": Quantity(f_hz, "Hz")},
        verdict=verdict,
    )


def run_impedance(setup: ImpedanceSetup, workdir: str | Path, z_target_ohm: float | None = None,
                  name: str = "impedance", **run_kwargs: object) -> ImpedanceResult:
    r = run(setup.netlist(), workdir, name, **run_kwargs)
    raw = r.raw()
    z_step = t_step = None
    if setup.transfer:
        # LTspice runs a .step list in sorted order, so find each step by its value, not its position.
        inj = [p.get("inj") for p in raw.step_params]
        if sorted(inj) != [0.0, 1.0]:
            raise RuntimeError(f"expected .step inj 0 and 1 in the log, got {raw.step_params}")
        z_step, t_step = inj.index(1.0), inj.index(0.0)
    f = raw.axis(z_step)
    z = measure.impedance(raw.get("V(rail)", z_step))
    transfer = raw.get("V(rail)", t_step) / raw.get("V(vs)", t_step) if setup.transfer else None
    return ImpedanceResult(r, f, z, measure.impedance_summary(f, z, z_target_ohm), transfer)
