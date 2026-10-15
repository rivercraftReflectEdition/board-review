# I/O levels and power domains

Applies to every net that crosses between power domains, every pull resistor, and every logic
input or output. Build the domain map first: each pin's reference supply from the digest
(`pins[].domain`) and the netlist.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## IO-1 Levels across domains at temperature and supply corners
- Check: driver VOH/VOL against receiver VIH/VIL at the worst supply and temperature. Many
  datasheets give thresholds as formulas of the supply (for example `VIH = a * VDD + b`).
- Why: thresholds that pass at nominal fail at the supply corner when the two domains move apart.
- Compute: `calc.divider` for any network; threshold formulas from the digest.
- Pass: margin at both levels at every corner.

## IO-2 Pin abs max with pull resistors and dividers
- Check: every pull-up or divider that ends on a pin; the pin's voltage against its abs max,
  using the domain the pin belongs to (5 V tolerant pins only when their own supply is up).
- Why: a pull-up to a higher rail puts a pin above abs max for the life of the board.
- Compute: `calc.divider`.
- Pass: below abs max at the rail's worst high, in every power state.
- Example: [pull-ups above pin abs max](../../docs/lessons/pullups-above-pin-abs-max.md)

## IO-3 Back-powering
- Check: any path from a powered domain into an unpowered one: I/O driving high, pull-ups on the
  wrong rail, resistors between rails, clamp diodes. Compute the current and the voltage the
  unpowered rail rises to.
- Why: back-powering violates sequencing rules, latches parts up, and can hold a module half
  powered.
- Compute: `calc.divider` with the clamp diode as a source; current into the dead rail.
- Pass: current below the datasheet's injection limit and the dead rail stays below its
  power-on threshold.

## IO-4 Irreversible I/O range settings
- Check: one-time fuses or option bits that set an I/O bank's voltage range or speed mode. List
  which banks need which setting, the setting that must never be programmed on a bank at a higher
  voltage, and the performance until it is set.
- Why: the wrong fuse permanently damages pins or caps interface speed; the right one is often
  required for full-speed memory.
- Compute: none; reference manual and digest.
- Pass: a fuse plan in the report with bit positions checked against the reference manual and a
  per-board go step.
- Example: [I/O range fuses](../../docs/lessons/io-range-fuses.md)

## IO-5 Pin function and order
- Check: every bus signal lands on a pin whose alternate function is that signal: SCL on SCL,
  SDA on SDA, TX to RX, clock on clock. Check against the alternate function table, not the net
  name.
- Why: a swapped pair has correct net names and passes every connectivity check.
- Compute: none; digest alternate function table against the netlist.
- Pass: each signal's pin has the matching function.
- Example: [I2C pins crossed](../../docs/lessons/i2c-pins-crossed.md)

## IO-6 Default state during reset and boot
- Check: inputs that control something (transceiver enables, load switch enables, triggers)
  while the driver is in reset or high-Z.
- Why: a floating driver-enable on a shared bus transmits garbage during every reset.
- Compute: none; internal pull from the digest, external pull from the netlist.
- Pass: a defined safe state from an external pull or a documented internal one.

## IO-7 Open-drain lines and pull-ups
- Check: every open-drain line (I2C, interrupts, power-good, faults) has a pull-up; VOL at the
  real pull-up current against VIL (some parts guarantee VOL only at high current).
- Why: a missing pull-up never reads high; a weak VOL guarantee can sit above VIL.
- Compute: `calc.i2c` for rise time and pull-up range; `calc.divider` for VOL.
- Pass: pull-up present; rise time and VOL inside limits.

## IO-8 MOSFET gate drive
- Check: VGS(th) max and the VGS at which RDS(on) is specified against the actual gate drive.
- Why: a FET with VGS(th) max near the drive voltage may not turn on.
- Compute: none; digest values.
- Pass: drive above the RDS(on) test voltage, or VGS(th) max well below the drive.
