# Resets, supervisors and watchdogs

Applies to every reset net, supervisor, watchdog and reset-combining network (diode-OR, wired-OR,
buffers), and to reset inputs of memories, PHYs, sensors and modules.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## RST-1 Asserted level at the cold corner
- Check: the low level delivered to each reset input: driver VOL at the actual sink current, plus
  every series drop (diode VF at cold, resistor drop). Compare with the receiver's VIL max at its
  minimum supply.
- Why: diode drops rise at cold and VIL scales with the receiver's supply; a reset that is
  marginal on guaranteed limits may not assert.
- Compute: `calc.divider.divider_output` for the network, with VF and VOL from the digest at the
  cold corner.
- Pass: delivered low below VIL max on guaranteed limits, not typicals.
- Example: [reset diode-OR margins](../lessons/reset-diode-or-margins.md)

## RST-2 Released level at the hot corner
- Check: pull-up current against the sum of all leakage on the net (reverse diode leakage at
  the actual reverse voltage, ESD clamps, other inputs, open-drain off-state leakage).
- Why: leakage grows fast with temperature; a weak pull-up can hold a device in reset when hot.
  RST-1 and RST-2 push in opposite directions, so retuning one resistor rarely fixes both.
- Compute: `calc.divider.divider_output` with leakage at the hot corner; `calc.timing.rc_edge`
  for the release time with any reset capacitor.
- Pass: released level above VIH min with maximum hot leakage; release time inside limits.
- Example: [reset diode-OR margins](../lessons/reset-diode-or-margins.md)

## RST-3 Domains in the reset network
- Check: a reset net that idles at one rail and drives inputs on a lower rail; back-powering and
  abs max of the lower-rail inputs, and of the inputs while their rail is off.
- Why: a 3.3 V reset into a 1.8 V input exceeds its abs max if any path conducts.
- Compute: `calc.divider.divider_output`; see io_levels_and_domains IO-2 and IO-3.
- Pass: no input sees more than its abs max in any power state.

## RST-4 Open-drain outputs have pull-ups
- Check: every open-drain reset, watchdog or power-good output has the pull-up the datasheet
  requires, to the right rail, sized for rise time against the net capacitance.
- Why: relying on a receiver's weak internal pull-up gives slow, leakage-sensitive edges.
- Compute: `calc.divider.divider_output` for levels; `calc.timing.rc_edge` for rise time
  (`2.2 R C` from 10 to 90 percent).
- Pass: pull-up present; rise time inside the receiver's limits.

## RST-5 Pulse width and recovery times
- Check: each device's minimum reset pulse and time from reset release to first access; capacitor
  on the MCU reset pin within the datasheet maximum; reset coherence between MCU and memories after
  a warm reset.
- Why: a memory left in a non-default mode after a warm MCU reset stops the boot ROM.
- Compute: `calc.timing.budget`.
- Pass: every minimum met by the slowest path.

## RST-6 Watchdog armed state against blank flash and debug
- Check: whether the watchdog runs from power-up; the first-kick deadline against boot time; what
  happens with blank or corrupt flash and during a debugger halt; whether a service strap or
  jumper disables it without soldering.
- Why: an armed watchdog with blank flash resets the board every timeout period, which blocks
  first programming and debugger sessions.
- Compute: `calc.timing.budget` boot time against the minimum watchdog period.
- Pass: a documented, solder-free way to disable it for programming, and boot time below the
  minimum period with margin.
- Example: [watchdog armed with blank flash](../lessons/watchdog-armed-with-blank-flash.md)

## RST-7 Watchdog configuration pins
- Check: timeout select and enable pins strapped (not floating); WDI connected to a pin that
  firmware controls from early boot.
- Why: a floating select gives an undefined timeout; an enable strapped off by a stray 0 ohm
  makes the watchdog inert.
- Compute: none; netlist and variant.
- Pass: every configuration pin has a defined level in the released variant.

## RST-8 Brownout coverage
- Check: every rail that can sag has a path to a reset (supervisor or power-good into reset) for
  the parts it feeds, including external memories.
- Why: a memory that browns out while the MCU keeps running corrupts data silently.
- Compute: `calc.divider.enable_thresholds` for adjustable supervisor thresholds against each
  load's minimum.
- Pass: threshold above each load's minimum supply, with tolerance.

## RST-9 Polarity of two-terminal parts in reset networks
- Check: diode and LED orientation where the datasheet gives no numbered pins (band only).
  Compare the library symbol and footprint pin mapping with the package marking.
- Why: a reversed diode in a reset-OR holds a reset net at the wrong rail.
- Compute: none; library and footprint check.
- Pass: the symbol's cathode pin maps to the footprint pad under the package's cathode marking
  in the datasheet drawing, and the silkscreen polarity mark is at that pad. Libraries number
  diode pads differently; check the mapping, not the pad number.
- Example: [reset diode-OR margins](../lessons/reset-diode-or-margins.md)
