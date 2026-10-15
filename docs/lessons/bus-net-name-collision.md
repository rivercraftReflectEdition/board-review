# Two memory buses shorted by a net name collision

**Rule:** zero duplicate-net warnings before any schematic-to-PCB update, and a 3-way netlist
compare before review
([netlist_integrity NET-1, NET-2](../../skill/checklists/netlist_integrity.md),
[xspi_memory MEM-1](../../skill/checklists/xspi_memory.md)).

Board: Sauron rev1. Parts: S28HS01GT octal NOR and S80KS5123 PSRAM on separate controller ports.
Status: caught in the July schematic review, before PCB sync.

## What happened

- The flash and PSRAM sheets used harness definitions that declared the same signal names:
  DQ0 to DQ7 and CS-N.
- Under hierarchical scope the compiled schematic kept two nets per name and raised nine
  "duplicate nets" warnings.
- PCB nets are keyed by name. Updating the PCB would have put both memories' pads on one net per
  name: the two buses shorted on copper, and net classes and length rules merged with them.
- Fix: prefix the names per memory and recompile until the warning count is zero.
- The fix itself caused a regression: the PSRAM chip select no longer reached the MCU pin. It was
  caught by re-running the mechanical checks
  ([fix batch regressions](fix-batch-regressions.md)).

## Why it is easy to miss

- The schematic and the schematic netlist both look right. The only signal is a compiler warning
  that is easy to treat as noise.

## The checks that catch it now

- [NET-2](../../skill/checklists/netlist_integrity.md): duplicate names across hierarchy.
- [NET-1](../../skill/checklists/netlist_integrity.md): schematic, PCB and fab netlists agree.
- [MEM-1](../../skill/checklists/xspi_memory.md): memory nets match the intended bus topology.
- [NET-4](../../skill/checklists/netlist_integrity.md): diff after every fix.
