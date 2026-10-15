# LDO and linear regulators

Applies to LDOs, linear current sources used as regulators, and references with a pass element.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## LDO-1 Dropout at the worst corner
- Check: `VIN_min - VOUT_max` against the dropout voltage at the real load current and hot
  junction temperature. VIN_min includes the upstream rail's tolerance and ripple trough.
- Why: an LDO in dropout passes input ripple and transients straight to the load.
- Compute: `calc.divider.regulator_output` for VOUT tolerance; dropout from the digest curve at Tj.
- Pass: headroom above maximum dropout plus the ripple trough.
- Not published: dropout given only as typical; use the curve at the hot corner and mark UNSURE.

## LDO-2 Output capacitor inside the stable region
- Check: effective COUT at bias and its ESR against the datasheet's stability region; some parts
  need a minimum ESR or allow only a maximum capacitance.
- Why: outside the region the LDO rings or oscillates.
- Compute: `calc.mlcc_bias.mlcc_effective`.
- Pass: inside the region at all temperatures and tolerances.

## LDO-3 Power dissipation
- Check: `P = (VIN_max - VOUT) * I_max + VIN_max * I_q` against the package's board-level
  thermal resistance.
- Why: thermal shutdown or drift at the hot corner.
- Compute: `calc.thermal.junction_temp`.
- Pass: Tj below the datasheet maximum minus the project's derating.

## LDO-4 Ripple rejection at the upstream switching frequency
- Check: PSRR at the upstream converter's fsw and at the actual headroom; PSRR collapses near
  dropout.
- Why: LDOs are often placed to clean a switcher's ripple and do little at MHz frequencies.
- Compute: output ripple `= input ripple * 10^(-PSRR/20)` from the digest PSRR curve CSV.
- Pass: output ripple below the load's limit.
- Not published: no curve at that frequency or headroom; add a bench measurement or an LC
  pre-filter footprint (then run ferrite_lc_filter).

## LDO-5 Reverse current when VIN falls below VOUT
- Check: output capacitance or another source holding VOUT up while VIN collapses.
- Why: many LDOs conduct backward through the pass element and can be damaged or back-power the
  input rail.
- Compute: none; datasheet reverse-current statement and the power tree.
- Pass: the datasheet allows it, or a reverse-blocking part or diode is fitted.

## LDO-6 Minimum load and start-up
- Check: minimum load current for regulation (current-source regulators); soft-start and inrush
  into COUT against the upstream limit.
- Why: below minimum load the output drifts high.
- Compute: lightest real load including sleep states; `C dV/dt` inrush.
- Pass: minimum load met in every state; inrush under the source's limit.
