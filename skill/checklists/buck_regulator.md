# Buck regulator

Applies to every synchronous or asynchronous buck, integrated switch or controller, any vendor.
Run once per channel. Inputs: the digest (`example_envelope`, equations, timing, thresholds),
BOM values, effective capacitance from `calc.mlcc_bias.mlcc_effective`.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## BR-1 Operating point inside the example envelope
- Check: compare VIN range, VOUT, duty, fsw, L, effective COUT at bias, compensation mode and
  light-load mode with the datasheet's example circuits for the same compensation mode.
- Why: an internally compensated loop is only validated near the vendor's examples. Correct pins
  and a "datasheet-prescribed" compensation tie say nothing about margin at your operating point.
- Compute: `calc.buck.duty_cycle` at both VIN extremes; `calc.mlcc_bias.mlcc_effective` for COUT;
  `calc.buck.example_envelope` against the digest `example_envelope`.
- Pass: the datasheet's component selection rules for that mode cover the operating point, or
  one example circuit of the same mode covers it alone (`calc.buck.example_envelope`: VIN range
  plus 5 percent, VOUT within a factor of 1.15, fsw 1.25, L and COUT 1.5; these factors are
  defaults, because the vendor shows behavior only near its examples). Sitting inside the span of
  several examples is not a pass: each value may come from a different example and the
  combination was never shown. A BR-1 pass is a screen; BR-2 still runs at the corners.
- Not published: internal compensation values are usually not given. Then BR-3 footprints are
  required and a bench Bode goes in the test plan.
- Example: [loop out of envelope](../../docs/lessons/loop-out-of-example-envelope.md)

## BR-2 Loop margin at the corners
- Check: phase and gain margin at worst corners of VIN, load, L tolerance, COUT (bias, temperature,
  tolerance, aging) and fsw.
- Why: nominal margin hides the corner that oscillates; a vendor model is a nominal estimate.
- Compute: `calc.loop.margins` (Bode, PM, GM, peaking; `calc.loop.Divider` for the divider and
  Cff); `sim.setups.run_loop_gain` when the plant is not published, after the sanity checks in
  workflow/40_checks.md, judged with `sim.setups.LoopGainResult.margins_result` at
  `gm_min_db=10` (its default is 6 dB).
- Pass: the datasheet's own criterion when it gives one. Otherwise these defaults at every
  corner: PM >= 45 deg (closed-loop peaking about 2.3 dB at crossover), GM >= 10 dB (room for
  gain spread the corners do not model), crossover below fsw/5 (the averaged model holds well
  below fsw; sampling adds phase lag toward fsw/2). They are review defaults, not limits from a
  standard.
- Not published: gm, current-sense gain or internal network missing means the result is an
  estimate. Report it as UNVERIFIABLE with a bench Bode and a load step.
- Example: [simulation setup errors](../../docs/lessons/simulation-setup-errors.md)

## BR-3 Rework options for a loop paper cannot settle
- Check: a DNP Cff footprint across the top feedback resistor; a 0 ohm plus DNP R-C on the
  compensation pin when the part can take external compensation; an injection point (0 ohm or
  10 to 50 ohm pad in series with the top feedback resistor).
- Why: without footprints a margin problem found on the bench becomes tack-soldered rework.
- Compute: `calc.loop.cff_lead` for the Cff zero `1/(2 pi R_top Cff)` and pole
  `1/(2 pi (R_top||R_bot) Cff)`.
- Pass: all three present whenever BR-2 is not a measured pass.
- Example: [loop out of envelope](../../docs/lessons/loop-out-of-example-envelope.md)

## BR-4 Large-signal slew headroom
- Check: inductor current slew available to correct a disturbance:
  up `(VIN_min * Dmax - VOUT) / L`, down `VOUT / L`, with `Dmax = 1 - fsw * (t_off_min + dead times)`.
- Why: a small up-slew turns a lightly damped ring into a large limit cycle at a much lower
  frequency.
- Compute: `calc.buck.current_slew`; compare with the same number for the datasheet examples.
- Pass: slew covers the load-step dI/dt. Slew more than 3x below the slowest example is a
  review trigger, not a verdict: run BR-2 at the corners and require BR-3 footprints.
- Example: [loop out of envelope](../../docs/lessons/loop-out-of-example-envelope.md)

## BR-5 Light-load mode and negative inductor current
- Check: which mode the MODE/SYNC pin and the orderable suffix select (forced continuous, pulse
  skip, burst). In forced continuous the valley current goes negative at light load and during
  output overshoot.
- Why: negative current flows back into the input rail; see cascaded_rails CR-1.
- Compute: `calc.buck.inductor_ripple` valley current `I_load - dI/2` at minimum load and maximum
  ripple.
- Pass: either the mode cannot return current, or CR-1 passes for the input rail.
- Example: [reverse current into a non-sinking rail](../../docs/lessons/fcm-reverse-current-into-non-sinking-rail.md)

## BR-6 On-time, off-time and frequency limits
- Check: `t_on = D / fsw` and `t_off = (1 - D) / fsw` against minimum on and off times at the VIN
  extremes; fsw across RT tolerance and temperature against the allowed range and any frequency
  floor for internal compensation.
- Why: below minimum off-time the part skips or stretches cycles and loses duty headroom; below
  the frequency floor the internal compensation is out of its design range.
- Compute: `calc.buck.duty_cycle` at each VIN extreme for `t_on = D / fsw`; `calc.buck.dropout`
  for the duty limit that minimum off-time and dead time set.
- Pass: 20 percent margin on each timing limit at its worst corner (default: minimum on and off
  times vary with temperature and gate drive and are often typical only); fsw inside the range.
- Not published: timing limits given as typical only; treat as UNSURE and add a bench check of
  the switch node at the VIN extremes.

## BR-7 Inductor saturation and ripple
- Check: Isat at the current-limit peak, not the load peak. Use the limit type the datasheet
  states: a peak limit plus the overshoot from current-sense delay, or a valley limit plus the
  full ripple above it. Ripple ratio within the datasheet's guidance; DCR loss and temperature
  rise.
- Why: an inductor that saturates in a fault defeats the current limit.
- Compute: peak limit: `I_peak_limit_max + VIN_max * t_delay / L_min`. Valley limit:
  `I_valley_limit_max + dI`, with dI the larger of the ripple at VIN_max and L_min
  (`calc.buck.inductor_ripple`) and `VIN_max * t_on_min / L_min` into a short. No calculator for
  either peak yet.
- Pass: Isat (at the vendor's roll-off definition, hot) above the worst peak.

## BR-8 Internal supply, bootstrap and gate-drive budget
- Check: INTVCC/VCC and bootstrap capacitors at bias meet the datasheet minimum; for controllers,
  gate charge `Qg * fsw` summed over FETs is below the internal regulator's guaranteed current.
- Why: an undersized internal supply sags, gate drive weakens, and the FETs run hot or the part
  never starts.
- Compute: `calc.mlcc_bias.mlcc_effective`; gate-drive current `sum(Qg) * fsw` (no calculator yet).
- Pass: effective capacitance above the minimum; gate current below 70 percent of the
  guaranteed limit (default: datasheet Qg is at one VGS and VDS, the real charge at the board's
  drive and VIN can be higher, and the internal regulator also feeds the control circuits).

## BR-9 Feedback divider accuracy and impedance
- Check: VOUT tolerance from reference tolerance and resistor tolerance against every load's
  supply range; FB pin leakage times the divider Thevenin resistance; stray capacitance at FB.
- Why: a high-impedance divider adds phase lag with a few pF and moves the setpoint with leakage.
- Compute: `calc.divider.regulator_output` with tolerance and FB current; lag
  `atan(2 pi fc (R_top||R_bot) C_stray)`, the phase of `calc.loop.Pole` at
  `1/(2 pi (R_top||R_bot) C_stray)`.
- Pass: worst-case VOUT inside every load's recommended range; lag under 5 deg at crossover
  (default: a small share of a 45 deg phase margin).

## BR-10 Re-check after late changes
- Check: any change to mode, L, COUT, fsw, compensation or VIN after the last review reopens
  BR-1 to BR-5.
- Why: late ECOs are applied under schedule pressure and are the least reviewed.
- Compute: `model.compare` against the previous snapshot to list the changed parts; then BR-1
  to BR-5.
- Pass: the review log shows BR-1 to BR-5 re-run on the released values.
- Example: [loop out of envelope](../../docs/lessons/loop-out-of-example-envelope.md)

## BR-11 Input capacitance and input filter interaction
- Check: input capacitor ripple current rating; input filter output impedance against the
  converter's negative input impedance `-VIN^2 / P_in`.
- Why: an undamped input filter and a regulating converter can oscillate together.
- Compute: `calc.lc_tank.lc_filter` for the filter peak; `sim.setups.run_impedance` for the
  impedance overlay.
- Pass: filter output impedance at least 6 dB below `VIN^2 / P_in` at every frequency (default:
  keeps `Z_out / |Z_in|` under 0.5, a common margin on the Middlebrook criterion; a measured input
  impedance or the datasheet's own rule overrides it).
