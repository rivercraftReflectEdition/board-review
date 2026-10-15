# Ethernet PHY

Applies to any Ethernet PHY and its magnetics, MDI protection and MAC interface.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## ETH-1 MAC interface mode matches the wiring
- Check: the strap-selected MAC interface (MII, RMII, RGMII and delay options) against the
  wiring and the MAC's configuration. Run straps_and_boot_pins STR-1 to STR-3 on every PHY strap.
- Why: many PHYs latch the interface mode only from straps; a wrong strap means no link and no
  software fix.
- Compute: `calc.divider.divider_output` per strap.
- Pass: every strap decodes to the intended mode, address and options.
- Example: [strap pairs fitted on both sides](../lessons/strap-pairs-fitted-both-sides.md)

## ETH-2 Reference clock
- Check: source and direction of the reference clock (50 MHz for RMII, 25 MHz crystal or
  oscillator otherwise), frequency tolerance, and which end drives it.
- Why: RMII with no 50 MHz reference, or two drivers, gives no link.
- Compute: `calc.timing.budget` in ppm against the 50 ppm Ethernet requirement;
  `calc.crystal.load_capacitance` for the pulling term.
- Pass: one source, inside tolerance.

## ETH-3 Management interface
- Check: MDIO pull-up value, MDC frequency against the PHY maximum, PHY address against other
  PHYs on the bus, and that the MDIO net actually reaches the PHY pin.
- Why: a label break on MDIO is invisible until bring-up.
- Compute: none; netlist and digest.
- Pass: connected, pulled up, unique address.

## ETH-4 Magnetics orientation and center taps
- Check: chip side and line side of the magnetics against the module's datasheet, pin by pin;
  center-tap treatment for the PHY's driver type (voltage mode or current mode); line-side
  termination; creepage across the isolation barrier.
- Why: a transposed magnetics symbol puts the common-mode choke on the wrong side or swaps pairs.
- Compute: none; digest pinout against the netlist.
- Pass: matches the vendor's reference topology; any deviation is documented with its effect.

## ETH-5 Reset, LEDs and dual-function pins
- Check: reset pull-up value and timing per datasheet; LED pins that double as straps (some PHYs
  sense LED polarity at reset); energy-saving features enabled by default.
- Why: LED wiring changes the strap value; default power saving surprises firmware.
- Compute: `calc.divider.divider_output` for LED-strap levels.
- Pass: straps hold with the LED circuits attached; firmware handoff lists defaults to clear.

## ETH-6 MDI protection
- Check: TVS or ESD array ground pins connected, or the datasheet's differential-only
  configuration used on purpose and noted on the schematic; capacitance budget.
- Why: floating ground pins look like a blocker or an intent; the schematic must say which.
- Compute: none; digest pin configuration.
- Pass: matches a configuration the datasheet shows.
- Example: [verifier dispute on ESD grounds](../lessons/verifier-dispute-esd-grounds.md)

## ETH-7 Bench readback
- Check: the bench plan reads PHY ID, strap status and interface mode registers before link tests.
- Why: confirms ETH-1 in minutes.
- Compute: none.
- Pass: expected register values written in the plan.
