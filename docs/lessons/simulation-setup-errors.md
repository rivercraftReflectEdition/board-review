# Simulations that gave confident wrong answers

**Rule:** a simulation result counts only after its netlist, operating point and injection pass
sanity checks, and a nominal model never passes a loop whose real compensation is unknown
([40_checks sanity checks](../../skill/workflow/40_checks.md),
[buck_regulator BR-2](../../skill/checklists/buck_regulator.md)).

Board: Sauron rev1. Part: LTC3633A, vendor LTspice model.
Status: three wrong conclusions during the 3V3 debug, 2026-10-06, each corrected the same day.

## What happened

1. A hand-written netlist left the second channel's pins floating. It produced an oscillation
   that seemed to match the bench. It was an artifact.
2. In the schematic, the timing resistor's wire stopped 16 grid units short of the RT pin. The
   model ran at 747 kHz instead of 1.187 MHz, and the margin results were for the wrong circuit.
3. Loop-gain injection at 20 mV exceeded the inductor's current slew limit above about 63 kHz.
   It reported crossover at 78 kHz and 35 deg. At 3 mV the same circuit gave about 169 kHz and
   42 deg.

Even the corrected nominal model showed positive margin where all three boards oscillated. The
model uses typical silicon and an ideal comparator.

## Why it matters for review

- Each error looked like a finding. A simulation that agrees with expectations gets less
  scrutiny than one that does not.

## The checks that catch it now

- [40_checks sanity checks](../../skill/workflow/40_checks.md): pins connected, fsw from RT within
  5 percent, injection amplitude independence, model limits written down, corners run.
- [BR-2](../../skill/checklists/buck_regulator.md): a nominal model is an estimate, not a pass.
