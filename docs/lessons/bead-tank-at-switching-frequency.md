# Ferrite bead and capacitor resonating at the switching frequency

**Rule:** compute the resonance and Q of every bead filter against nearby switching frequencies,
and when the bead's inductance is not published, bound it instead of staying silent
([ferrite_lc_filter FLT-1, FLT-2](../../skill/checklists/ferrite_lc_filter.md)).

Board: Sauron rev1. Parts: TDK KPZ1608SHR121ATDH5 beads (120 ohm at 100 MHz) on MCU analog
supplies, fed from a 1V8 rail made by an LTC3633A at about 1.2 MHz.
Status: caught before fab (pre-route review, 2026-08-12); fixed in the release.

## What happened

- One bead fed an MCU regulator's analog supply with 100 nF after it. Another fed the PLL, ADC
  and camera analog supplies with 300 nF.
- Bead inductance at low frequency estimated at about 190 nH. First filter: f0 = 1.15 MHz,
  Q about 15, gain about +21 dB at the 1.2 MHz buck frequency. Second: f0 = 665 kHz, Q about 13.
- The filters would have amplified the ripple they were placed to remove.
- Release fix: the first bead was deleted and that supply tied to its rail as the MCU vendor's
  grouping allows. The second kept its bead with a damper (1 ohm in series with 1 uF) on the
  filtered node.

## Why it was nearly missed

- A second reviewer, working the camera block, saw the same filter and noted that a bead with a
  few hundred nF of ceramics can peak. It did not flag it, because the bead datasheet was not at
  hand and the inductance would be an estimate. Not published became silence.
- The datasheet gives impedance at 100 MHz, not inductance at 1 MHz. The reviewer that flagged it
  checked the verdict across the plausible range: at 100 nH, Q is still about 10.
- Connectivity and capacitor values matched the MCU vendor's decoupling table.

## The checks that catch it now

- [FLT-1](../../skill/checklists/ferrite_lc_filter.md): resonance against every nearby fsw, with
  a bound when L is not published.
- [FLT-2](../../skill/checklists/ferrite_lc_filter.md): damping to Q <= 2.
- [Not-published rule](../../skill/workflow/40_checks.md): an unknown is never a pass and never
  dropped.
