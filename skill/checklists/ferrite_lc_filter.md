# Ferrite bead and LC filters

Applies to every bead or inductor followed by capacitance on a supply: analog rail filters, PLL
supplies, input filters of converters. A bead at low frequency is an inductor with little loss.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## FLT-1 Resonance against nearby switching frequencies
- Check: `f0 = 1 / (2 pi sqrt(L C))` using the bead's low-frequency inductance at the real DC
  current and the total effective capacitance after the bead. Compare f0 with the fsw of every
  converter on or near that rail, their harmonics, and the edge rate of load steps.
- Why: an undamped bead plus a few hundred nF of ceramics forms a high-Q tank. If f0 lands near
  fsw the filter amplifies the ripple it was meant to remove.
- Compute: `calc.lc_tank.lc_filter` gain `|H(f)|` at each fsw, swept across L and C tolerance;
  the corners alone miss a resonance that crosses fsw between them.
- Pass: `|H(fsw)| < 1` across the sweep and peak gain under 6 dB (default: a gain of 2 on
  whatever excites the tank, about a `q_damping` of 2 in FLT-2 when the tank is lightly damped),
  or no switcher harmonic, clock or load-step edge reaches the peak frequency (list them).
- Not published: bead datasheets often give only impedance at 100 MHz. Use the vendor's SPICE or
  S-parameter model. If none, sweep L over a plausible range, including any L that puts f0 on
  an fsw harmonic. A plausible range is an assumption, not a published bound, so the result stays
  unknown even when the sweep is clean: require the FLT-2 damper footprint and a bench check of
  the rail ripple. Silence is not an option.
- Example: [bead tank at the switching frequency](../lessons/bead-tank-at-switching-frequency.md)

## FLT-2 Damping
- Check: the damping Q, `Q = Z0 / R_series` with `Z0 = sqrt(L / C)`, R_series = bead
  resistance at f0 plus capacitor ESR plus source and series damping resistance.
- Why: low-loss beads and ceramics give Q of 10 or more; even off-resonance, any excitation
  near f0 rings.
- Compute: `calc.lc_tank.lc_filter` reports this Q as `q_damping` (with `r_total` and Z0 as
  `r0`), and the peak gain as `peak` in dB and `peak_gain_linear`. Quote `q_damping` as the Q.
  `peak_gain_linear`, `10^(peak/20)`, is only a proxy: for a series RLC the peak is
  `Q / sqrt(1 - 1 / (4 Q^2))`, within 15 percent of Q for Q of 1 and above, and 1 for any Q
  below 0.7, so an overdamped tank with a Q of 0.1 still shows 1. With an R-C damper or a load
  resistor, `q_damping` leaves their damping out and is an upper bound. Damper:
  `calc.lc_tank.lc_filter` with a series R-C across the output in `dampers`, `Rd ~ Z0`,
  `Cd >= 3 C`; `calc.lc_tank.damping_options` gives Rd for a chosen Cd.
- Pass: `q_damping` <= 2. With a damper or a load, a bound above 2 still passes when the peak
  gain stays under 6 dB (default: a ring that dies in a few cycles; tighten it when the load's
  ripple budget needs it).
- Example: [bead tank at the switching frequency](../lessons/bead-tank-at-switching-frequency.md)

## FLT-3 Bead DC bias and rating
- Check: inductance and impedance drop with DC current; rated current and DCR at the hot corner.
- Why: a filter sized at zero current moves its resonance at full load.
- Compute: digest curve CSV of L or Z against DC current.
- Pass: the filter still meets FLT-1 at the real current; current under the bead's rating.

## FLT-4 DC drop
- Check: `DCR_max * I_max` against the load's supply tolerance stack.
- Why: the drop eats margin on low-voltage analog supplies with tight minimums.
- Compute: `calc.divider.regulator_output` for the rail's low corner, minus `DCR_max * I_max`.
- Pass: the load's minimum supply met at the worst corner.

## FLT-5 Ring from load steps
- Check: a load step excites the tank; ring amplitude about `dI * Z0`, decay `2 Q / (2 pi f0)`
  with Q from FLT-2 (`q_damping`), not the peak-gain proxy.
- Why: digital loads on a filtered rail (PLLs, internal regulators) step with microsecond edges.
- Compute: `calc.lc_tank.lc_filter` for Z0 (`r0`); `sim.setups.run_load_step` when the load
  profile matters.
- Pass: rail stays inside the load's limits during the ring.

## FLT-6 Converter input filters
- Check: an LC ahead of a switching converter must meet BR-11 (output impedance below the
  converter's negative input impedance) and its hot-plug overshoot must stay under part ratings.
- Why: a hot-plugged LC with ceramic capacitors rings up toward twice the input voltage.
- Compute: `calc.lc_tank.lc_filter`; `sim.setups.run_startup` with a fast input ramp for hot-plug.
- Pass: see buck_regulator BR-11 and protection_tvs PROT-5.
