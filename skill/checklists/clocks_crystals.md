# Clocks, crystals and oscillators

Applies to every crystal, oscillator, clock buffer and clock input.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## CLK-1 Oscillator output level against the receiver's domain
- Check: oscillator supply (and the voltage code in its part number) against the receiver's
  input reference. Some clock inputs in bypass mode are referenced to a low-voltage analog supply,
  not to the I/O rail. Check VDD and OE of the oscillator too.
- Why: a 3.3 V clock into a 1.8 V-referenced input exceeds abs max; changing the part number alone
  leaves the oscillator powered from the wrong rail.
- Compute: `calc.divider` if levels are shifted by a network; otherwise digest VOH and VIH.
- Pass: VOH max below the input's abs max and VIH met at minimum supply.
- Example: [oscillator output domain](../../docs/lessons/oscillator-output-domain.md)

## CLK-2 Crystal load and drive
- Check: `CL = C1 * C2 / (C1 + C2) + C_stray` against the crystal's CL; oscillator gain margin
  (negative resistance at least 3 to 5 times ESR max); drive level against the crystal's maximum.
- Why: wrong load capacitance pulls frequency; low gain margin fails to start at cold or with age.
- Compute: `calc.crystal`.
- Pass: CL within 1 pF, gain margin at least 5 (3 if the MCU vendor says so), drive under maximum.

## CLK-3 Frequency budget
- Check: initial tolerance plus temperature plus aging plus supply and load pull against the
  interface requirement (Ethernet, USB, CAN, UART, timekeeping).
- Why: a budget that passes at room temperature fails over life.
- Compute: `calc.crystal` ppm budget or `calc.timing`.
- Pass: total inside the interface requirement with margin.

## CLK-4 Unused oscillator pins and bypass straps
- Check: in bypass mode the unused oscillator pin is left or tied exactly as the datasheet says.
- Why: a grounded or floating pin can be right or wrong depending on the mode; reviewers flag
  correct straps as errors.
- Compute: none; digest pin table.
- Pass: matches the datasheet for the selected mode.

## CLK-5 Distribution, enables and default state
- Check: series termination, stub length, fan-out, the OE default during reset, and which device
  sources a shared reference clock (for example a 50 MHz RMII reference).
- Why: two drivers on one reference clock, or none, kills the interface.
- Compute: `calc.timing` for edge rate and skew.
- Pass: exactly one driver; termination per the source's drive and trace length.

## CLK-6 Clock limits that firmware must respect
- Check: peripheral kernel clock maxima and PLL limits for the planned clock tree; list them in
  the firmware handoff.
- Why: a board that works on a lab image can fail on a production clock tree.
- Compute: none; digest table.
- Pass: every planned clock inside its limit, noted in the report.
