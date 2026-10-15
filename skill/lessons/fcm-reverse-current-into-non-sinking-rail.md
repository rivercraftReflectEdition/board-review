# Forced-continuous buck returning current into a rail that cannot sink

**Rule:** for every rail, list what can push current back into it and what absorbs it
([cascaded_rails CR-1](../checklists/cascaded_rails.md),
[buck_regulator BR-5](../checklists/buck_regulator.md)).

Board: Sauron rev1. Parts: LTC3633A (downstream, forced continuous) on a 4 V rail made by a base
LT8640 (SYNC/MODE floating, pulse skipping).
Status: never reviewed; seen at bring-up while debugging the 3V3 oscillation.

## What happened

- The LTC3633A MODE pin was strapped to ground in release week to select forced-continuous
  mode. In that mode the inductor current goes negative at light load and during output
  overshoot, and the charge returns to the input rail.
- The base LT8640 in pulse-skipping mode cannot sink. Only the -1 variant runs forced continuous,
  with a limited sink rating, and it inhibits that mode during soft-start and above about 7
  percent overvoltage (LT8640 Rev F pp.16-17).
- During the oscillation the switch node showed the bottom FET on with inductor current near
  -1.5 A, and a switch high level of 4.4 V, above VIN. The 4 V rail swung 3.65 to 4.35 V at the
  same 32 kHz.
- Nothing bounded that excursion. The 4 V rail also feeds a camera module supply (5.1 V
  maximum), a TVS with 5.0 V standoff and load switches rated 5.5 V. The swing stayed below them
  by magnitude, not by design.
- At the low end of the swing (3.65 V) the 3V3 channel's maximum output was about 3.37 V, which
  cut its recovery headroom and reinforced the cycle.

## Why the review missed it

- The mode change was judged per regulator. No check asked whether the upstream rail could absorb
  returned current. The power budget looked at forward current only.

## The checks that catch it now

- [CR-1](../checklists/cascaded_rails.md): returned current against what absorbs it.
- [BR-5](../checklists/buck_regulator.md): light-load mode and negative inductor current.
- [CR-4](../checklists/cascaded_rails.md): every load on the rail against its worst high.
- [CR-3](../checklists/cascaded_rails.md): headroom when the upstream rail sags.
