# Power distribution and decoupling

Applies to every IC supply pin group and every rail's bulk capacitance.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## PDN-1 Required capacitors present
- Check: count, value and type per supply pin group against the datasheet and the vendor's
  hardware application note. Dedicated pins (internal regulator outputs, references, reset) get
  exactly what the datasheet states, including stated maximum values.
- Why: "more is better" breaks pins with a maximum capacitance (reset delay, internal LDO
  stability).
- Compute: none; digest table against the BOM.
- Pass: every listed capacitor present, none above a stated maximum.

## PDN-2 Effective capacitance at bias
- Check: each ceramic at its DC bias, temperature and tolerance. Class II parts in small cases can
  lose most of their value.
- Why: a design that meets the minimum on nominal values may be far below it on the board.
- Compute: `calc.mlcc_bias`.
- Pass: effective value meets the datasheet minimum.
- Not published: no bias curve from the vendor; use the worst curve of the same case, voltage
  rating and dielectric, mark UNSURE, and measure one unit unpowered and biased.

## PDN-3 Target impedance
- Check: `Z_target = dV_allowed / dI_step`; PDN impedance below target from DC to the frequency
  where the load's current edges stop.
- Why: rail droop during load steps causes resets and data errors that look like firmware bugs.
- Compute: `sim.pdn` with regulator output impedance, capacitor ESR and ESL, plane spreading.
- Pass: impedance below target, no anti-resonance peak above it.

## PDN-4 Anti-resonance between banks
- Check: parallel banks of different values resonate where one bank's ESL meets the next bank's C.
- Why: the peak can sit right at a clock or switching frequency.
- Compute: `sim.pdn`.
- Pass: peaks below target, or damped by ESR.

## PDN-5 Voltage rating
- Check: rating against the rail maximum including transients; polymer and tantalum derating per
  vendor; ceramics rated so their bias loss is acceptable.
- Why: overstressed polymer and tantalum parts fail short.
- Compute: none; rail maximum from cascaded_rails CR-4.
- Pass: inside the project's derating rule.

## PDN-6 Total capacitance and inrush
- Check: total capacitance on a rail against the regulator's soft-start, the load switch's
  limits and any interface maximum (for example a battery or bus with a stated limit).
- Why: inrush trips current limits, browns out the source, or welds connector contacts.
- Compute: `I = C dV/dt` during soft-start.
- Pass: inrush under the source's limit.
