# Buck loop outside the datasheet's example envelope

**Rule:** compare every regulator's operating point with the datasheet's examples for the same
compensation mode, and give any loop that paper cannot settle a Cff and compensation footprint
([buck_regulator BR-1 to BR-4](../../skill/checklists/buck_regulator.md)).

Board: Sauron rev1 star tracker carrier (STM32N657). Part: LTC3633A dual buck, channel 1 (3V3).
Status: missed by three reviews; found at bring-up on all three boards, 2026-10-06.

## What happened

- Channel 1 ran from the 4.02 V rail at about 1.19 MHz in forced-continuous mode, with ITH tied
  to INTVCC (internal compensation), L = 6.8 uH and about 17 uF effective COUT (two 10 uF 0805
  X7S plus 100 nF parts). Forced-continuous mode and the 6.8 uH inductor were release-week
  changes.
- Every board oscillated: 3V3 swung 2.76 to 3.50 V in a 32 kHz relaxation cycle, and 1V8, which
  is sequenced from 3V3 power-good, did not come up.
- Mechanism from bench and model: a lightly damped ring near 100 to 160 kHz, plus a small
  inductor up-slew, `(VIN * Dmax - VOUT) / L` = 57 mA/us at 6.8 uH, became the 32 kHz cycle. The
  datasheet examples have 7 to 13 A/us.
- 2.2 uH removed the 32 kHz cycle on board 1 but left a 115 kHz, 45 mV ring: zero margin.
  Board 2 still oscillated with 2.2 uH. Extra 10 uF parts lowered the amplitude, not the
  frequency.
- 22 pF across the top feedback resistor stopped it on board 2 (2026-10-14): even switching at
  1.173 MHz, 7.7 mV pk-pk. The fitted model puts that at about 20 deg PM and 4 dB GM. Stable,
  thin. Next spin: external ITH compensation, a Cff footprint, more COUT.

## Why the reviews missed it

- The 07-30, 08-24 and 08-28 reviews checked pins and connectivity, and passed the ITH-to-INTVCC
  tie as the datasheet's documented configuration. It is. Nobody compared the operating point
  with the examples.
- The datasheet does not publish the internal network or the ITH-to-current gain. It recommends
  internal compensation above 1 MHz (LTC3633A Rev B p.16); its 1 MHz example (p.26) uses external
  compensation. "Not published" was read as "fine".
- The vendor's LTspice model, set up correctly, gives about 42 deg at 18 uF. Simulation alone
  would have passed the loop. The boards had tens of degrees less.
- The mode and inductor changes came late and the loop was not rechecked.
- There was no Cff or compensation footprint, so every fix was tack soldering.

## The checks that catch it now

- [BR-1](../../skill/checklists/buck_regulator.md): operating point against the example envelope.
- [BR-2](../../skill/checklists/buck_regulator.md): margin at corners; a nominal model is not a pass.
- [BR-3](../../skill/checklists/buck_regulator.md): Cff, compensation and injection footprints.
- [BR-4](../../skill/checklists/buck_regulator.md): slew headroom against the examples.
- [BR-10](../../skill/checklists/buck_regulator.md): re-check after late changes.
- [50_verify](../../skill/workflow/50_verify.md): high-risk passes go to the verifier.
