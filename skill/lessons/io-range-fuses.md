# One-time I/O range fuses

**Rule:** list every irreversible I/O range setting the board needs, the one that must never be
set, and the bit positions checked against the reference manual
([io_levels_and_domains IO-4](../checklists/io_levels_and_domains.md),
[xspi_memory MEM-4](../checklists/xspi_memory.md)).

Board: Sauron rev1. Part: STM32N657 HSLV (high-speed low-voltage) OTP fuses.
Status: near miss; handled by a fuse plan written during review.

## What happened

- The MCU's 1.8 V I/O banks need one-time HSLV fuses for full-speed I/O. Until they are burned,
  the memory interfaces run in a degraded mode: slow probes work, rated speed does not.
- One HSLV bit belongs to the 3.3 V VDD bank. Burning it would leave the 3.3 V pins set for low
  voltage, permanently.
- The review's firmware list named the bits to burn (the two memory banks, camera banks
  optional) and the one never to burn. Bring-up used a script that checked the bit positions,
  burned only after a per-board go, and verified after reset. Two boards were burned this way and
  both verified.

## Why it is a lesson

- A one-line note in a firmware list was the only barrier between a fuse script and a bricked
  board. Reviews of the schematic alone would not have produced it.

## The checks that catch it now

- [IO-4](../checklists/io_levels_and_domains.md): irreversible I/O range settings.
- [MEM-4](../checklists/xspi_memory.md): memory I/O voltage and speed range.
- [60_report firmware handoff](../workflow/60_report.md).
