# Camera and MIPI CSI-2

Applies to image sensors and camera modules on CSI-2 or parallel interfaces, and their control,
power and connector.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## CSI-1 Lane count and mapping
- Check: the sensor's default lane count against the wired lanes; lane order and polarity against
  what the receiver can swap; unused lanes and their pads.
- Why: a module that defaults to more lanes than wired needs a register write before streaming.
- Compute: none; digests and netlist.
- Pass: mapping supported by the receiver; the firmware handoff lists required lane settings.

## CSI-2 Bandwidth
- Check: pixel rate times bits per pixel against lanes times lane rate, and against the
  receiver's and memory's throughput including padding (for example RAW10 stored as 16 bits).
- Why: a link that fits on paper overflows the memory bus.
- Compute: `calc.timing.budget` per stage, required rate against available rate.
- Pass: 20 percent margin on each stage (default: covers bursts and blanking that an average
  rate hides).

## CSI-3 Power sequencing of the module
- Check: required rail order, delays and reset-low time of the sensor against the enable chain.
- Why: a module powered in the wrong order may latch up or fail to start.
- Compute: `calc.timing.budget`; see enable_uvlo_sequencing EN-4.
- Pass: enforced in hardware, or a written firmware contract.

## CSI-4 Control signals and back-powering
- Check: I2C, reset, trigger and clock pins in the module's I/O domain; pull-ups on the module's
  switched rail, not an always-on rail; inputs with no internal pull.
- Why: pull-ups on an always-on rail back-power an off module; floating triggers fire at random.
- Compute: `calc.divider.divider_output`; `calc.i2c.i2c_rise_time`.
- Pass: no path into an off module; every input has a defined state.

## CSI-5 D-PHY routing and termination
- Check: 100 ohm differential impedance, intra-pair and lane-to-clock skew, reference planes,
  and the receiver's termination or reference resistor value and tolerance.
- Why: skew and impedance errors show up as intermittent CRC errors.
- Compute: `calc.timing.budget` for the skew budget.
- Pass: inside the receiver's and sensor's skew limits.

## CSI-6 Connector
- Check: pinout against the module datasheet with mating orientation (mirroring), every ground
  pin connected, decoupling at the connector, and mechanical keepout (layout LAY-6).
- Why: a mirrored connector or a part under the module stops the board at first fit.
- Compute: none.
- Pass: pin-by-pin match; keepout clear.
