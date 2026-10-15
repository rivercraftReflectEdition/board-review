# Enable, UVLO and sequencing

Applies to every enable, run, UVLO and power-good path, and to the power-up and power-down order.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## EN-1 Every divider computed from BOM values
- Check: for each enable or UVLO divider, compute the rail voltage at which the pin crosses its
  rising and falling thresholds, from the released BOM values, not from the schematic note.
- Why: a decade or unit typo (ohm for kohm) keeps correct connectivity and passes every pin and
  net check.
- Compute: `calc.divider.enable_thresholds`: `V_on = V_th_rise * (R_top + R_bot) / R_bot`, same
  for falling.
- Pass: turn-on and turn-off inside the intended input window.
- Example: [UVLO resistor decade typo](../../docs/lessons/uvlo-resistor-decade-typo.md)

## EN-2 Margin against threshold spread and leakage
- Check: margin between the pin voltage at the worst rail and the threshold's min/max, including
  resistor tolerance and pin leakage times the divider's Thevenin resistance.
- Why: a few tens of mV of margin disappears into leakage on a high-impedance divider, and start-up
  becomes board-dependent.
- Compute: `calc.divider.enable_thresholds` with tolerance and leakage: shift
  `= I_leak * (R_top || R_bot)` at the pin.
- Pass: margin at the worst corner exceeds the tolerance plus leakage shift, at both thresholds.
- Example: [enable divider with thin margin](../../docs/lessons/enable-divider-thin-margin.md)

## EN-3 Recompute when the source changes
- Check: any change to the rail feeding a divider, or to either resistor, reopens EN-1 and EN-2.
- Why: dividers verified once are not rechecked when the upstream regulator or setpoint changes.
- Compute: as EN-1 and EN-2.
- Pass: the review log shows the calculation on the released rail and values.
- Example: [enable divider with thin margin](../../docs/lessons/enable-divider-thin-margin.md)

## EN-4 Order and timing match every part's requirement
- Check: power-up and power-down order, delays and tracking required by each IC (MCU, FPGA,
  sensors, modules) against the enable chain. Note which rules are hardware-enforced and which
  depend on firmware.
- Why: a sequencing rule left to firmware is broken during reset, programming and faults.
- Compute: `calc.timing.budget` for delays; soft-start times from the digests.
- Pass: every required order is enforced in hardware, or the firmware contract is written on the
  schematic and in the bench plan.

## EN-5 Enables driven or watched by logic pins
- Check: a logic pin on an enable or power-good net must see only voltages inside its abs max,
  and the enable must have a defined state while the logic is in reset.
- Why: pull-ups to a higher rail put pins above abs max permanently.
- Compute: `calc.divider.divider_output` for the pin voltage.
- Pass: pin voltage below abs max at the rail's worst high; defined default state.
- Example: [pull-ups above pin abs max](../../docs/lessons/pullups-above-pin-abs-max.md)

## EN-6 Leakage that enables something on its own
- Check: high-value pull-downs on enables fed through a transistor, diode or ESD structure whose
  leakage rises with temperature.
- Why: leakage times a large resistor can cross the enable threshold at the hot corner.
- Compute: `calc.divider.divider_output` with the published leakage at the hot corner; see
  thermal TH-3 when only one temperature is given.
- Pass: pin stays below the low threshold with maximum hot leakage.

## EN-7 Brownout and restart behavior
- Check: falling thresholds and hysteresis; what each part does between its POR and its UVLO;
  hiccup or latch-off behavior; which rails have a supervisor.
- Why: a rail can sag into a band where logic runs out of spec with no reset.
- Compute: `calc.divider.enable_thresholds` falling thresholds; digest POR and BOR levels.
- Pass: every logic rail is covered by a reset before it leaves its operating range.

## EN-8 Power-good outputs
- Check: open-drain power-good outputs need a pull-up to the reader's domain; the reader's input
  level and the PG output's VOL at the pull-up current.
- Why: a PG used as an enable with no pull-up never releases the next stage.
- Compute: pull-up current `(V_pullup - VOL) / R_pullup` against the digest's VOL test current.
- Pass: pull-up present; levels met in io_levels_and_domains IO-1.
