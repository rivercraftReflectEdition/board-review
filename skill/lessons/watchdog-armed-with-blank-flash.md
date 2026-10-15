# Watchdog armed at power-up with blank flash

**Rule:** decide what the watchdog does with blank flash and under a debugger, and provide a
solder-free way to disable it for programming
([resets_supervisors_watchdogs RST-6, RST-7](../checklists/resets_supervisors_watchdogs.md)).

Board: Sauron rev1. Parts: TPS3435 external watchdog, STM32N657, S28HS01GT boot NOR.
Status: flagged as a bring-up hazard before release; handled with a strap that needed soldering.

## What happened

- The watchdog was armed from power-up by its enable strap, with a 1.44 s minimum timeout and no
  start-up delay. With a blank NOR nothing kicks it, so the board resets about every 1.6 s.
  First programming needed an 0402 resistor fitted, or its pads bridged, to disable it.
- During development, a debugger breakpoint placed before clock setup was reset by the boot
  stage's 2 s internal watchdog. One such reset left the first sector of the backup image slot
  erased (mechanism UNSURE). It was recovered over the network.
- In July and August the same watchdog had the opposite problems: enable strapped off by a 0 ohm,
  timeout select floating, WDI not wired, and no pull-up on its open-drain output.

## Why it slipped

- The watchdog policy (armed or not, and how to override it) was decided late and implemented as
  a resistor choice, not as a service jumper.

## The checks that catch it now

- [RST-6](../checklists/resets_supervisors_watchdogs.md): armed state against blank flash
  and debug.
- [RST-7](../checklists/resets_supervisors_watchdogs.md): configuration pins strapped.
- [RST-4](../checklists/resets_supervisors_watchdogs.md): open-drain output pull-up.
- [LAY-8](../checklists/layout.md): test and rework access.
