# Cascaded rails

Applies wherever one regulator feeds another, or several loads share a rail fed by one regulator.
Build the power tree first (workflow/30_blocks.md). Every edge of the tree gets these checks.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## CR-1 Upstream can sink what downstream returns
- Check: list every way current can flow back into the rail: a downstream synchronous converter
  in forced-continuous mode at light load or during output overshoot, soft-stop, pre-bias start,
  motor or inductive loads. Then check what absorbs it: an upstream regulator that can sink (its
  sink rating, and the modes and conditions where sinking is inhibited), a bleed load, or a clamp.
- Why: a pulse-skipping or diode-emulating upstream regulator cannot sink. Returned charge pumps
  the rail up until something gives.
- Compute: `C_rail dV/dt = I_up - I_down - I_other`; worst returned current from
  `calc.buck.inductor_ripple` valley current; charge per event `I_return * t_event`.
- Pass: the rail's worst excursion stays under every load's abs max and under the upstream
  regulator's OV threshold, at minimum load.
- Not published: sink current unspecified; treat as zero.
- Example: [reverse current into a non-sinking rail](../../docs/lessons/fcm-reverse-current-into-non-sinking-rail.md)

## CR-2 Source and load impedance
- Check: a regulated converter has negative incremental input impedance. The upstream rail's
  output impedance must stay well below it across frequency, or the two loops interact.
- Why: two regulators that are each stable alone can ring or oscillate together.
- Compute: `sim.setups.run_impedance` overlay of `|Z_out_upstream|` and `VIN^2 / P_in_downstream`.
- Pass: 6 dB separation at every frequency.

## CR-3 Headroom
- Check: the upstream rail's worst low (tolerance, load step trough, ripple) against the
  downstream part's minimum VIN, its dropout, and its maximum duty.
- Why: a downstream regulator at maximum duty cannot recover from a step and can limit-cycle.
- Compute: `calc.buck.dropout` maximum output `VIN * Dmax` minus conduction drops.
- Pass: positive headroom at the worst corner.

## CR-4 Every load on the rail survives the rail's worst high
- Check: list every part on the rail with its abs max and recommended maximum (including TVS
  standoffs and load switches). Compare with the upstream setpoint tolerance, overshoot, and any
  pumping from CR-1.
- Why: TVS diodes and load switches on a rail often have the lowest limits.
- Compute: `calc.divider.regulator_output` setpoint tolerance plus the CR-1 excursion.
- Pass: worst high below every abs max; below recommended maximums in normal operation.

## CR-5 Start-up interaction
- Check: downstream inrush sags the upstream rail below the downstream enable or UVLO threshold,
  restarting it in a loop; soft-start times and enable chains.
- Why: a start-up hiccup looks like a loop oscillation on the bench and costs debug time.
- Compute: `sim.setups.run_startup` with both regulators; `calc.divider.enable_thresholds` for
  enable thresholds.
- Pass: no restart in simulation at worst-case capacitance; bench start-up capture in the plan.

## CR-6 Power budget
- Check: upstream current capacity against the sum of downstream input currents at their worst
  efficiency, plus inrush.
- Why: a rail sized on typical efficiency browns out at cold or at minimum input.
- Compute: sum of `P_out / (eta_min * VIN_min)` per load, plus `C dV/dt` inrush.
- Pass: 20 percent margin at the worst corner.
