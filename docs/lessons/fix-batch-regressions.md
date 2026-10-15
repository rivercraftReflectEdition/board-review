# Regressions from a fix batch, and fixes never applied

**Rule:** after every fix batch, re-extract and diff against the last snapshot, and re-verify
every fix in the data instead of the fix log
([netlist_integrity NET-4](../../skill/checklists/netlist_integrity.md)).

Board: Sauron rev1.
Status: caught by re-running the mechanical checks, 2026-07-31 and 2026-08-24.

## What happened

- On 2026-07-31, after fixes were applied by hand, a fresh pass of the mechanical checks found new
  errors made by the edits:
  - a rail rename left the MCU's internal regulator supply net with no source, and the filtered
    analog rail lost its bead: the board could not boot;
  - after the memory bus split, the PSRAM chip select no longer reached the MCU;
  - camera I2C pull-ups landed on the wrong renamed rail, which would back-power the module.
- On 2026-08-24 the pre-fab review found that several July fixes had never been applied: strap
  DNPs, the boot pin, the watchdog straps.

## Why it happens

- Renames are silent: the schematic still looks connected. Fixes are applied by hand under
  schedule pressure, and the fix log says "done".

## The checks that catch it now

- [NET-4](../../skill/checklists/netlist_integrity.md): diff after every change, one source per
  power net, prior fixes checked in the data.
- [NET-3](../../skill/checklists/netlist_integrity.md): project contents complete.
- [IO-3](../../skill/checklists/io_levels_and_domains.md): back-powering.
- [MEM-2](../../skill/checklists/xspi_memory.md): every memory signal reaches the controller.
- [Intake item 5](../../skill/workflow/00_intake.md): prior findings re-verified.
