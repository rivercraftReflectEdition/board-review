# Straps and boot pins

Applies to every pin sampled at reset or power-up: PHY and switch configuration, addresses, boot
mode pins, regulator mode and frequency pins, sensor address and mode pins.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## STR-1 Sampled voltage inside its level window
- Check: compute the voltage each strap pin settles to from the fitted parts of the released
  variant plus the pin's internal pull, and compare with the level table (two-level VIL/VIH, or
  the voltage windows of multi-level pins).
- Why: a strap at mid-rail latches an undefined or default mode; many modes cannot be changed by
  software afterward.
- Compute: `calc.divider` with the internal pull in parallel with the external low side (or
  high side), at resistor and pull tolerance corners.
- Pass: inside the intended level window with margin at every corner.
- Not published: internal pull only typical; use a wide bound (for example 0.5x to 2x typical)
  and show the level holds at both ends.
- Example: [strap pairs fitted on both sides](../../docs/lessons/strap-pairs-fitted-both-sides.md)

## STR-2 Fitted state from the released variant
- Check: read fitted and DNP state from the BOM variant that goes to assembly, not from design
  notes. A pull-up and pull-down both fitted on a two-level pin is a finding.
- Why: a fix that lives only in notes or in an unreleased variant reaches no board.
- Compute: none; variant table against the netlist.
- Pass: exactly one side fitted per two-level strap, or the level table needs the divider.
- Example: [strap pairs fitted on both sides](../../docs/lessons/strap-pairs-fitted-both-sides.md)

## STR-3 Trace through series resistors and other loads
- Check: a strap network may sit one series resistor away from the pin. Follow the net through
  series parts to the pin, and include every other load on it during sampling (MCU pins in reset,
  LED drivers, transistor gates, other ICs' pulls).
- Why: per-net checks that stop at the first resistor miss doubled straps and loaded straps.
- Compute: `calc.divider` with all loads.
- Pass: STR-1 holds with every load included.

## STR-4 Nothing drives the strap net while it is sampled
- Check: what the other end of a dual-function pin does between power-up and strap latch.
- Why: an MCU pin driving during reset overrides the strap.
- Compute: `calc.timing` for latch time against the driver's reset state.
- Pass: every other driver is high-Z or agrees during sampling.

## STR-5 Boot pins select the intended source in every mode
- Check: compute each boot pin's level as in STR-1; list the boot modes the board needs
  (production, recovery or serial, development) and how each is reached.
- Why: a boot divider that reads high selects serial boot forever; a mode reachable only by
  soldering slows bring-up.
- Compute: `calc.divider` against the boot pin's VIH/VIL formula at the supply corners.
- Pass: production mode is the default with margin; every other mode is reachable through a
  documented jumper, DNP or test point.
- Example: [boot pin divider](../../docs/lessons/boot-pin-divider.md)

## STR-6 Readback in the bench plan
- Check: the bench plan reads back latched strap values (status registers, address scans) on
  first power, before functional tests.
- Why: a strap error shows up as a dead interface and wastes time on firmware.
- Compute: none.
- Pass: one readback step per strapped device with the expected register value.

## STR-7 Addresses unique on each bus
- Check: resolved address of every device on a shared bus, including module internal defaults.
- Why: two devices on one address both answer and corrupt each other.
- Compute: none; address tables from the digests.
- Pass: unique addresses; record them in the firmware handoff.
