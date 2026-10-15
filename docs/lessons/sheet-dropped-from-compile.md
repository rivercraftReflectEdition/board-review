# A schematic sheet dropped out of the compile

**Rule:** compare the project's document list with the hierarchy and the files on disk, and diff
part counts against the last snapshot
([netlist_integrity NET-3, NET-4](../../skill/checklists/netlist_integrity.md)).

Board: Sauron rev1 (Altium project).
Status: caught in release week, 2026-08-27, before the package was sent.

## What happened

- The mid-level parent sheet of the regulator sheets (3V3 and 1V8, and 4 V) was removed from the
  project. Both child sheets dropped out of the compile. The file was still on disk.
- The compiled netlist simply had no regulators. The compiler raised no error for the missing
  circuits.
- It was noticed because whole sheets were missing from the netlist. The sheet was re-added and the
  netlist re-verified.

## Why it is easy to miss

- A review reads the compiled netlist. Circuits that are not in it raise no warnings, and checks
  on the remaining parts still pass. The visible symptom is power nets with no source.

## The checks that catch it now

- [NET-3](../../skill/checklists/netlist_integrity.md): project contents against hierarchy and disk.
- [NET-4](../../skill/checklists/netlist_integrity.md): snapshot diff and one source per power net.
- [NET-1](../../skill/checklists/netlist_integrity.md): 3-way compare with the PCB and fab netlists.
