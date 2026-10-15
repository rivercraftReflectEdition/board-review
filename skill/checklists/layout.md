# Layout (phase 2)

Applies once placement exists. Uses PCB data from the board model (placements, layers, polygons,
vias, stackup). Some items need routed copper; mark them UNSURE until routing is done.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## LAY-1 Switcher hot loop and switch node
- Check: input capacitor, switch and ground return form the smallest loop on one layer; switch
  node copper no larger than needed; nothing sensitive under or beside it.
- Why: the hot loop's inductance sets ringing and EMI.
- Compute: loop area from placements; none beyond that.
- Pass: matches the datasheet layout example and its rules in the digest.

## LAY-2 Feedback and compensation nodes
- Check: divider and compensation parts close to the IC, on the IC's side, returned to the
  quiet ground the datasheet names; no vias or long runs on high-impedance nodes; distance from
  the switch node.
- Why: stray capacitance at FB adds lag `atan(2 pi fc (R_top||R_bot) C)`; coupling from the
  switch node injects noise into the loop.
- Compute: `calc.loop.Pole` at `1/(2 pi (R_top||R_bot) C)` with an estimated stray C; its phase
  at crossover is the lag.
- Pass: lag under 5 deg at crossover (default, as in buck_regulator BR-9); datasheet layout rules
  met.

## LAY-3 Decoupling placement
- Check: smallest capacitor closest to the pin with the shortest via path; same-side or
  opposite-side placement against the datasheet's guidance for BGAs.
- Why: mounting inductance, not capacitance, limits high-frequency decoupling.
- Compute: `sim.setups.run_impedance` with via inductance when the rail is critical.
- Pass: every pin group has its high-frequency capacitor within the guidance distance.

## LAY-4 Return paths
- Check: high-speed signals keep a continuous reference plane; stitching vias where a signal
  changes between layers referenced to different planes.
- Why: a broken return path radiates and couples into neighbors.
- Compute: none; layer and plane map.
- Pass: no high-speed signal crosses a plane split; stitching at every reference change.

## LAY-5 Impedance and length rules from the real stackup
- Check: trace widths and gaps for single-ended and differential impedance computed from the
  fabricator's stackup; length-match rules from the timing budgets.
- Why: rules inherited from another board's stackup give the wrong impedance.
- Compute: `calc.timing.budget` for skew budgets; the fabricator's stackup values.
- Pass: rules match the computed values.

## LAY-6 Mechanical keepouts and stack height
- Check: parts inside a module, connector or shield footprint against the mating stack height;
  parts under inductors and transformers; board-edge and mounting-hole clearances.
- Why: one tall part under a mezzanine module stops it from seating.
- Compute: none; 3D or height data against the mating drawing.
- Pass: no part taller than the gap inside any keepout.
- Example: [module keepout](../../docs/lessons/module-keepout-shadow.md)

## LAY-7 Isolation and creepage
- Check: copper, parts and vias across isolation barriers (magnetics, isolators) against the
  required creepage and clearance for the coating and voltage.
- Why: a decoupling capacitor in the isolation gap defeats the barrier.
- Compute: none; IPC-2221 or the product's standard.
- Pass: required distances met.

## LAY-8 Test and rework access
- Check: probe points for every rail, reset, clock and enable; loop injection points; footprints
  for options the review left open.
- Why: paper cannot settle everything; the bench needs access.
- Compute: none.
- Pass: each bench test in the report has a place to probe.

## LAY-9 Schematic and PCB in sync
- Check: netlist_integrity NET-1 passes on the copper that goes to fab.
- Why: an unsynced ECO ships the old circuit.
- Compute: `model.compare` 3-way compare.
- Pass: zero differences.
