"""LTspice (ngspice optional) runs a reviewer can trust: setups, runner, raw reader, measurements, sanity checks."""

from boardreview.sim.measure import loop_margins, margins_result, ring_result, step_response, switching_frequency
from boardreview.sim.rawfile import RawFile, read_raw
from boardreview.sim.runner import LTspice, NgSpice, RunResult, get_backend, run, run_many, schematic_to_netlist
from boardreview.sim.sanity import SanityReport, check_netlist, check_run, injection_slew_check
from boardreview.sim.setups import (
    Bead,
    Cap,
    ImpedanceSetup,
    LoadStepSetup,
    LoopGainSetup,
    StartupSetup,
    body_from_netlist,
    injection_frequencies,
    run_impedance,
    run_load_step,
    run_loop_gain,
    run_startup,
)

__all__ = [
    "Bead", "Cap", "ImpedanceSetup", "LTspice", "LoadStepSetup", "LoopGainSetup", "NgSpice", "RawFile", "RunResult",
    "SanityReport", "StartupSetup", "body_from_netlist", "check_netlist", "check_run", "get_backend",
    "injection_frequencies", "injection_slew_check", "loop_margins", "margins_result", "read_raw", "ring_result",
    "run", "run_impedance", "run_load_step", "run_loop_gain", "run_many", "run_startup", "schematic_to_netlist",
    "step_response", "switching_frequency",
]
