# Protection: TVS, ESD and overvoltage

Applies to TVS diodes, ESD arrays, input protection, reverse polarity and overvoltage paths.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## PROT-1 Standoff above the rail's worst high
- Check: VRWM against the rail's maximum in normal operation: setpoint tolerance, regulator
  overshoot, pumping (cascaded_rails CR-1), source tolerance.
- Why: a TVS with VRWM below the rail leaks, heats, and clamps during normal operation.
- Compute: `calc.protection.tvs_standoff`.
- Pass: VRWM at or above the worst normal maximum.

## PROT-2 Clamp below every protected part's rating
- Check: clamp voltage at the expected surge current (from the interface spec or test standard)
  against the abs max of every part on the net, including capacitors' voltage ratings.
- Why: a TVS that conducts but clamps above the IC's abs max protects nothing.
- Compute: `calc.protection.tvs_clamp` at the surge current the waveform and source impedance
  give.
- Pass: clamp at surge current below every abs max on the net, with the surge current inside the
  characterized clamp points and inside the rated IPP or PPP for that pulse shape.
- Not published: clamp given only up to a lower current, or no pulse rating; `tvs_clamp` returns
  UNKNOWN. Scaling with the dynamic resistance is an estimate only: mark it UNSURE and ask for the
  vendor curve or a surge test.

## PROT-3 Orientation
- Check: unidirectional TVS cathode toward the positive rail; footprint pin mapping against the
  package marking.
- Why: a reversed unidirectional TVS is a forward-biased short across the rail.
- Compute: none; library and footprint check.
- Pass: confirmed against the datasheet drawing and the footprint.

## PROT-4 ESD array configuration
- Check: ground pins connected, or a datasheet configuration that leaves them open used on
  purpose and noted on the schematic.
- Why: an array with floating grounds only clamps line to line; that may be the intent or a bug.
- Compute: none; digest application figures.
- Pass: matches a datasheet configuration; intent written on the schematic.
- Example: [verifier dispute on ESD grounds](../../docs/lessons/verifier-dispute-esd-grounds.md)

## PROT-5 Filter and TVS coordination
- Check: an input LC filter rings on hot-plug and surge; the ring adds to the clamp.
- Why: ceramic input capacitors with a long cable ring up toward twice the input step.
- Compute: `calc.lc_tank.lc_filter` for the peak and Z0; `sim.setups.run_startup` with a fast
  input ramp for hot-plug.
- Pass: peak below every rating with the damper as designed.

## PROT-6 Fault overvoltage on downstream rails
- Check: what a single fault (open feedback resistor, shorted pass FET) does to each downstream
  rail, and whether loads on it have a clamp or their own tolerance.
- Why: an open top feedback resistor drives a rail toward its input.
- Compute: rail voltage with the fault; load abs max.
- Pass: a clamp or supervisor limits the damage, or the risk is accepted in the report.

## PROT-7 Capacitance on fast signals
- Check: protection capacitance against the signal's bandwidth and the interface's budget.
- Why: a large TVS on a high-speed pair closes the eye.
- Compute: `calc.timing.rc_edge` for edge rate with the added C.
- Pass: inside the interface's capacitance budget.
