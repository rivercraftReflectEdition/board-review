# Reset diode-OR: no margin at cold, stuck in reset when hot

**Rule:** check every reset input's asserted level at the cold corner and its released level at
the hot corner, on guaranteed values
([resets_supervisors_watchdogs RST-1, RST-2](../checklists/resets_supervisors_watchdogs.md)).

Board: Sauron rev1. Parts: TPS3435 watchdog (open-drain output) and the MCU reset on a 3.3 V
net, BAT30 Schottky diodes into the 1.8 V RESET# pins of the NOR (S28HS01GT) and PSRAM
(S80KS5123).
Status: called fine in July; raised to blocker at the 2026-08-28 gate review; shipped as a backup
reset path; flight fix planned.

## What happened

- Cold: the low level delivered to RESET# is the driver's VOL plus the diode's VF. On guaranteed
  limits it reaches 566 mV against the PSRAM's VIL maximum of 540 mV at 1.8 V (510 mV at 1.7 V).
  Reset is not guaranteed to assert at cold. UNSURE: this page does not record the terms of
  the 566 mV. What settles it: the driver's guaranteed VOL at its actual sink current and the
  BAT30 VF at the cold corner and that current, each with its datasheet page.
- Hot: BAT30 reverse leakage (50 uA maximum at 85 C, specified at VR = 10 V; ST DocID12564 Rev 3
  Table 4 p.2) against the PSRAM's internal pull-up. Above roughly 90 to 105 C the leakage can
  hold the memory in reset. UNSURE: that range extrapolates the 85 C limit and rests on a
  PSRAM pull-up value this page does not give. What settles it: BAT30 reverse current at the
  real reverse voltage (about 1.5 V, the 3.3 V net against the 1.8 V pin) and temperature from
  the vendor curve, the PSRAM pull-up minimum with its page, or a hot bench test.
- The two failures sit at opposite temperature corners, so no resistor value fixes both. Next
  spin: a 1.8 V open-drain buffer (SN74LVC2G07, VOL 0.45 V maximum at 4 mA) in place of the
  diodes.
- The SOD-523 datasheet has no pin numbers. Diode orientation could only be checked against the
  library symbol and the part's band.
- Bench, room temperature: software reset 10 of 10 and internal watchdog reset 3 of 3 passed. The
  external watchdog path and the temperature corners are still untested.

## Why the first review missed it

- The July review used typical VF and concluded the circuit worked "in every realistic
  condition". Only the guaranteed stack shows the cold failure.
- Leakage was first quoted without its test voltage, which started an argument about its size
  instead of a calculation at the real reverse voltage.

## The checks that catch it now

- [RST-1](../checklists/resets_supervisors_watchdogs.md): asserted level at cold.
- [RST-2](../checklists/resets_supervisors_watchdogs.md): released level at hot.
- [RST-3](../checklists/resets_supervisors_watchdogs.md): domains in the reset network.
- [RST-9](../checklists/resets_supervisors_watchdogs.md): polarity of two-terminal parts.
- [TH-3](../checklists/thermal.md): both temperature corners where they oppose.
