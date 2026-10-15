"""Run LTspice (or ngspice) in batch on a netlist and collect the .raw, the .log and their errors."""

from __future__ import annotations

import os
import re
import shutil
import string
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from boardreview.sim.rawfile import RawFile, read_raw, read_text_any

ENV_LTSPICE = "BOARDREVIEW_LTSPICE"
ENV_NGSPICE = "BOARDREVIEW_NGSPICE"
LTSPICE_PATHS = (
    r"C:\Program Files\ADI\LTspice\LTspice.exe",
    r"C:\Program Files\LTC\LTspiceXVII\XVIIx64.exe",
    "/Applications/LTspice.app/Contents/MacOS/LTspice",
)

_HEADER_LINES = ("circuit:", "start time:", "ltspice ", "solver =", "maximum thread", "tnom =", "temp =",
                 "method =", "asciirawfile")
_FILE_LINE = re.compile(r"\.\w+\(\d+\):")
_MEAS = re.compile(r"^([A-Za-z_][\w.]*):\s*[^=]*=\s*\(?([-+\d.eE]+)")
_ERROR_PATTERNS = (
    re.compile(r"\berror\b", re.I),
    re.compile(r"time step too small", re.I),
    re.compile(r"singular matrix", re.I),
    re.compile(r"not defined|undefined|unknown (sub|model|param)", re.I),
    re.compile(r"file not found|could not open|can't find|cannot find", re.I),
    re.compile(r"does not match number of pins", re.I),
    re.compile(r"(analysis|simulation) (failed|aborted)", re.I),
    re.compile(r"gmin stepping failed|source stepping failed|failed to converge", re.I),
)
_WARNING_PATTERNS = (
    re.compile(r"\bwarning\b", re.I),
    re.compile(r"fail'?ed", re.I),
    re.compile(r"floating|questionable|ignored|is not used|resetting", re.I),
)
_NOTE_PATTERNS = (
    re.compile(r"direct newton iteration failed", re.I),
    re.compile(r"(gmin|source) stepping succeeded", re.I),
    re.compile(r"starting (gmin|source) stepping", re.I),
)


@dataclass(frozen=True)
class LogReport:
    """What a reviewer must see from a simulator log before trusting the waveforms."""

    text: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    notes: tuple[str, ...]
    measurements: dict[str, list[float]]
    failed_measurements: tuple[str, ...]
    steps: tuple[dict[str, float], ...]
    files_loaded: tuple[str, ...]
    elapsed_s: float | None


def parse_log(text: str) -> LogReport:
    """Split an LTspice or ngspice log into errors, warnings, notes, .meas results and loaded files."""
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    measurements: dict[str, list[float]] = {}
    failed: list[str] = []
    steps: list[dict[str, float]] = []
    files: list[str] = []
    elapsed = None
    lines = text.replace("\r", "").split("\n")
    in_files = False
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        i += 1
        if not stripped:
            in_files = False
            continue
        if stripped.lower().startswith("files loaded"):
            in_files = True
            continue
        if in_files:
            files.append(stripped)
            continue
        low = stripped.lower()
        if low.startswith(_HEADER_LINES):
            continue
        if low.startswith(".step "):
            steps.append({k: _num(v) for k, v in re.findall(r"([\w.]+)=(\S+)", stripped[6:])})
            continue
        m = re.match(r"total elapsed time:\s*([\d.eE+-]+)", low)
        if m:
            elapsed = float(m.group(1))
            continue
        m = re.match(r'measurement\s+"?([^"\s]+)"?\s+fail', low)
        if m:
            failed.append(m.group(1))
            warnings.append(stripped)
            continue
        if _FILE_LINE.search(stripped):
            context = [stripped]
            while i < len(lines) and lines[i].strip() and not _FILE_LINE.search(lines[i]):
                context.append(lines[i].rstrip())
                i += 1
            errors.append("\n".join(context))
            continue
        m = _MEAS.match(stripped)
        if m and not low.startswith(("circuit", "start time", "warning", "error")):
            measurements.setdefault(m.group(1).lower(), []).append(float(m.group(2)))
            continue
        if any(p.search(stripped) for p in _NOTE_PATTERNS):
            notes.append(stripped)
            continue
        if any(p.search(stripped) for p in _ERROR_PATTERNS):
            errors.append(stripped)
            continue
        if any(p.search(stripped) for p in _WARNING_PATTERNS):
            warnings.append(stripped)
    measurements.update(_meas_tables(lines))
    return LogReport(
        text=text,
        errors=tuple(errors),
        warnings=tuple(warnings),
        notes=tuple(notes),
        measurements=measurements,
        failed_measurements=tuple(failed),
        steps=tuple(steps),
        files_loaded=tuple(files),
        elapsed_s=elapsed,
    )


def _meas_tables(lines: list[str]) -> dict[str, list[float]]:
    """Stepped .meas results, which LTspice prints as 'Measurement: name' then a step table."""
    out: dict[str, list[float]] = {}
    i = 0
    while i < len(lines):
        m = re.match(r"\s*measurement:\s*(\S+)", lines[i], re.I)
        i += 1
        if not m:
            continue
        name = m.group(1).lower()
        values = []
        while i < len(lines) and lines[i].strip():
            parts = lines[i].split()
            if parts and parts[0].isdigit() and len(parts) >= 2:
                values.append(_num(parts[1]))
            i += 1
        if values:
            out[name] = values
    return out


def _num(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        return float("nan")


@dataclass
class RunResult:
    backend: str
    command: tuple[str, ...]
    netlist: Path
    raw_path: Path | None
    log_path: Path | None
    returncode: int | None
    wall_s: float
    timed_out: bool
    log: LogReport
    _raw: RawFile | None = field(default=None, repr=False)

    @property
    def ok(self) -> bool:
        return (
            not self.timed_out
            and self.returncode == 0
            and not self.log.errors
            and self.raw_path is not None
            and self.raw_path.exists()
        )

    @property
    def op_raw_path(self) -> Path | None:
        p = self.netlist.with_name(self.netlist.stem + ".op.raw")
        return p if p.exists() else None

    def raw(self) -> RawFile:
        """Parsed waveforms; raises with the log errors if the run did not produce any."""
        if self._raw is None:
            if self.raw_path is None or not self.raw_path.exists():
                raise RuntimeError(f"no .raw from {self.netlist.name}: " + "; ".join(self.problems()))
            self._raw = read_raw(self.raw_path, self.log_path)
        return self._raw

    def problems(self) -> list[str]:
        out = []
        if self.timed_out:
            out.append(f"timed out after {self.wall_s:.0f} s")
        if self.returncode not in (0, None):
            out.append(f"exit code {self.returncode}")
        out += [e.splitlines()[0] for e in self.log.errors]
        return out

    def summary(self) -> str:
        """Markdown block: status, command, errors, warnings and notes from the log."""
        status = "ok" if self.ok else "FAILED"
        lines = [f"**{self.backend} run {self.netlist.name}**: {status} in {self.wall_s:.1f} s"]
        lines.append("`" + " ".join(self.command) + "`")
        lines += [f"- error: {e}" for e in self.problems()]
        lines += [f"- warning: {w}" for w in self.log.warnings]
        lines += [f"- note: {n}" for n in self.log.notes]
        lines += [f"- loaded: {f}" for f in self.log.files_loaded]
        return "\n".join(lines)


class LTspice:
    """LTspice batch backend: 'LTspice.exe -b [-ascii] [-alt|-norm] [-I<path>] deck.net' writes deck.raw and deck.log."""

    name = "ltspice"

    def __init__(self, exe: str | Path | None = None):
        self.exe = Path(exe) if exe else find_ltspice()

    def available(self) -> bool:
        return self.exe is not None and Path(self.exe).exists()

    def command(self, netlist: Path, ascii_raw: bool = False, solver: str | None = None,
                include_dir: Path | None = None) -> list[str]:
        cmd = [str(self.exe), "-b"]
        if ascii_raw:
            cmd.append("-ascii")
        if solver in ("alt", "norm"):
            cmd.append(f"-{solver}")
        if include_dir is not None:
            cmd.append(f"-I{include_dir}")
        cmd.append(str(netlist))
        return cmd

    def outputs(self, netlist: Path) -> tuple[Path, Path]:
        return netlist.with_suffix(".raw"), netlist.with_suffix(".log")

    def env(self, ascii_raw: bool) -> dict[str, str] | None:
        return None


class NgSpice:
    """ngspice batch backend: 'ngspice -b -r deck.raw -o deck.log deck.net'. Netlist dialect differs from LTspice."""

    name = "ngspice"

    def __init__(self, exe: str | Path | None = None):
        self.exe = Path(exe) if exe else find_ngspice()

    def available(self) -> bool:
        return self.exe is not None and Path(self.exe).exists()

    def command(self, netlist: Path, ascii_raw: bool = False, solver: str | None = None,
                include_dir: Path | None = None) -> list[str]:
        raw, log = self.outputs(netlist)
        return [str(self.exe), "-b", "-r", str(raw), "-o", str(log), str(netlist)]

    def outputs(self, netlist: Path) -> tuple[Path, Path]:
        return netlist.with_suffix(".raw"), netlist.with_suffix(".log")

    def env(self, ascii_raw: bool) -> dict[str, str] | None:
        if not ascii_raw:
            return None
        return {**os.environ, "SPICE_ASCIIRAWFILE": "1"}


def find_ltspice() -> Path | None:
    """LTspice executable from BOARDREVIEW_LTSPICE, the usual install paths, or PATH."""
    env = os.environ.get(ENV_LTSPICE)
    if env and Path(env).exists():
        return Path(env)
    for p in LTSPICE_PATHS:
        if Path(p).exists():
            return Path(p)
    found = shutil.which("LTspice") or shutil.which("XVIIx64")
    return Path(found) if found else None


def find_ngspice() -> Path | None:
    """ngspice executable from BOARDREVIEW_NGSPICE or PATH."""
    env = os.environ.get(ENV_NGSPICE)
    if env and Path(env).exists():
        return Path(env)
    found = shutil.which("ngspice_con") or shutil.which("ngspice")
    return Path(found) if found else None


def get_backend(name: str = "ltspice") -> LTspice | NgSpice:
    """Backend by name; raises if the simulator is not installed."""
    backend = {"ltspice": LTspice, "ngspice": NgSpice}[name.lower()]()
    if not backend.available():
        raise FileNotFoundError(f"{name} not found; set {ENV_LTSPICE if name == 'ltspice' else ENV_NGSPICE}")
    return backend


def render(template: str, **params: object) -> str:
    """Fill a netlist template that uses $name or ${name}; a missing value is an error, not a blank."""
    return string.Template(template).substitute({k: _spice_value(v) for k, v in params.items()})


def _spice_value(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def write_netlist(text: str, path: str | Path) -> Path:
    """Write a netlist with a title line first (SPICE ignores line 1) and a closing .end."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = text.strip("\n").replace("\r\n", "\n").split("\n")
    if not lines or not lines[0].lstrip().startswith("*"):
        lines.insert(0, f"* {path.stem}")
    if not any(line.strip().lower() == ".end" for line in lines):
        lines.append(".end")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def run(
    netlist: str | Path,
    workdir: str | Path | None = None,
    name: str = "sim",
    timeout_s: float = 600.0,
    ascii_raw: bool = False,
    backend: LTspice | NgSpice | None = None,
    solver: str | None = None,
    include_dir: str | Path | None = None,
) -> RunResult:
    """Run one netlist (a path, or text written to workdir/name.net) and collect its outputs."""
    backend = backend or get_backend("ltspice")
    path = _as_netlist_path(netlist, workdir, name)
    raw_path, log_path = backend.outputs(path)
    for stale in (raw_path, log_path, path.with_name(path.stem + ".op.raw")):
        if stale.exists():
            stale.unlink()
    cmd = backend.command(path, ascii_raw, solver, Path(include_dir) if include_dir else None)
    t0 = time.monotonic()
    timed_out = False
    returncode: int | None
    try:
        proc = subprocess.run(cmd, cwd=path.parent, capture_output=True, timeout=timeout_s,
                              env=backend.env(ascii_raw))
        returncode = proc.returncode
        console = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        timed_out = True
        returncode = None
        console = ""
    wall = time.monotonic() - t0
    text = read_text_any(log_path.read_bytes()) if log_path.exists() else ""
    if console.strip():
        text = text + "\n" + console
    return RunResult(
        backend=backend.name,
        command=tuple(cmd),
        netlist=path,
        raw_path=raw_path if raw_path.exists() else None,
        log_path=log_path if log_path.exists() else None,
        returncode=returncode,
        wall_s=wall,
        timed_out=timed_out,
        log=parse_log(text),
    )


def run_many(netlists: list[str | Path], workdir: str | Path | None = None, names: list[str] | None = None,
             max_workers: int = 2, **kwargs: object) -> list[RunResult]:
    """Run several netlists in parallel processes; results keep the input order."""
    names = names or [f"sim{i:03d}" for i in range(len(netlists))]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(run, n, workdir, nm, **kwargs) for n, nm in zip(netlists, names)]
        return [f.result() for f in futures]


def schematic_to_netlist(asc_path: str | Path, timeout_s: float = 60.0, exe: str | Path | None = None) -> Path:
    """Convert an LTspice .asc to a .net next to it with 'LTspice.exe -netlist', so the netlist checks can read it."""
    asc = Path(asc_path).resolve()
    lt = LTspice(exe)
    if not lt.available():
        raise FileNotFoundError(f"LTspice not found; set {ENV_LTSPICE}")
    net = asc.with_suffix(".net")
    if net.exists():
        net.unlink()
    subprocess.run([str(lt.exe), "-netlist", str(asc)], cwd=asc.parent, capture_output=True, timeout=timeout_s)
    if not net.exists():
        raise RuntimeError(f"LTspice did not write {net.name}")
    return net


def _as_netlist_path(netlist: str | Path, workdir: str | Path | None, name: str) -> Path:
    if isinstance(netlist, Path) or ("\n" not in str(netlist) and Path(str(netlist)).suffix.lower() in
                                     (".net", ".cir", ".sp", ".spi", ".spice", ".ckt")):
        path = Path(netlist).resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        return path
    if workdir is None:
        raise ValueError("netlist text needs a workdir to be written to")
    return write_netlist(str(netlist), Path(workdir).resolve() / f"{name}.net")
