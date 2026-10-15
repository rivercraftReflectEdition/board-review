# Thermal

Applies to every part that dissipates more than a few tens of mW, and to temperature-dependent
parameters used by other checks.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## TH-1 Junction temperature at the worst corner
- Check: dissipation at the worst electrical corner; `Tj = T_board + P * theta` with the board's
  real thermal path, not the JEDEC number.
- Why: JEDEC theta assumes a large multilayer board in still air.
- Compute: `calc.thermal`.
- Pass: Tj below the datasheet maximum minus the project's derating.

## TH-2 Exposed pads and thermal vias
- Check: exposed pad connection to the right net (some pads are the switch node, not ground), via
  count and size per the datasheet, copper area.
- Why: a pad on the wrong net or with too few vias loses most of the thermal path.
- Compute: `calc.thermal` via resistance.
- Pass: matches the datasheet layout guidance.

## TH-3 Temperature corners in other checks
- Check: every check that uses leakage, VF, RDS(on), threshold or capacitance uses the value at
  the relevant temperature corner (cold for VF and capacitance, hot for leakage and RDS(on)).
- Why: room-temperature numbers hide the opposite-corner failures.
- Compute: digest curves; leakage roughly doubles every 10 C when only one point is given.
- Pass: both corners evaluated where they push in opposite directions.

## TH-4 Derating
- Check: resistor power, capacitor ripple current and voltage, FET SOA against the project's
  derating rules.
- Why: parts at 100 percent of rating fail early.
- Compute: `calc.thermal`; SOA from the digest curve.
- Pass: inside the derating rule.

## TH-5 Self-heating and neighbors
- Check: sensor excitation self-heating; hot parts near references, crystals, and temperature
  sensors.
- Why: a sensor that heats itself or sits next to a regulator reads wrong.
- Compute: `calc.thermal` self-heating `P = I^2 R` with the sensor's dissipation constant.
- Pass: error below the measurement budget.

## TH-6 No convection
- Check: in vacuum or sealed housings, only conduction to the chassis counts.
- Why: board temperatures in vacuum run far above bench readings.
- Compute: `calc.thermal` conduction only.
- Pass: Tj limit met with no convection term.
