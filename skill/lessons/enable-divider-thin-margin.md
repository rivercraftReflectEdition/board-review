# Enable divider with 40 mV of margin

**Rule:** an enable divider's margin must exceed resistor tolerance plus pin leakage times the
divider's Thevenin resistance, recomputed whenever the source rail or a resistor changes
([enable_uvlo_sequencing EN-2, EN-3](../checklists/enable_uvlo_sequencing.md)).

Board: Sauron rev1. Part: LTC3633A RUN1 pin, divided down from the 4 V rail.
Status: shipped; flagged as a next-spin item at bring-up, 2026-10-06.

## What happened

- RUN1 divider 57.6k over 27.4k from the 4.024 V rail: `4.024 * 27.4 / 85.0 = 1.297 V`.
  The rising threshold is 1.18 to 1.26 V (LTC3633A Rev B p.3). Margin: 37 mV.
- The specified pin leakage (up to 3 uA) through the divider's 18.6 kohm Thevenin resistance
  moves the pin 56 mV, more than the margin. At the corners the rail must reach about 4.14 V
  before the channel enables, above the nominal rail. Start-up becomes board-dependent.
- During the 3V3 debug a simulation showed a start-up hiccup through RUN1 when the 4 V rail
  sagged, which made RUN1 the lead suspect for a day until the bench ruled it out.
- Next spin: a lower-impedance divider and qualified supervision.

## Why the review missed it

- The July review recorded the enable dividers at 1.474 V. The released values differ, and the
  release notes list them as kept with no margin calculation. UNSURE when the top resistor
  changed; the released netlist and BOM settle it.
- No check included pin leakage.

## The checks that catch it now

- [EN-2](../checklists/enable_uvlo_sequencing.md): margin against tolerance and leakage.
- [EN-3](../checklists/enable_uvlo_sequencing.md): recompute when the source changes.
- [CR-5](../checklists/cascaded_rails.md): start-up interaction between rails.
