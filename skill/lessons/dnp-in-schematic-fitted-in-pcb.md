# DNP in the schematic, fitted in the PCB

**Rule:** read the fitted state of every part from each source that can drive assembly (BOM,
schematic, PCB footprint), raise any difference as a finding, and analyze the circuit in both
fitted states ([netlist_integrity NET-7](../checklists/netlist_integrity.md)).

Board: an open-source carrier board for a compute module, reviewed offline from its KiCad files.
Parts: two 0 ohm option resistors and a fuse.
Status: caught.

## What happened

- Two 0 ohm option resistors select the supply for a camera connector's pull-ups. One links the
  pull-up node to a 1.8 V LDO output, the other to the 3.3 V buck output through a fuse. Only
  one is meant to be fitted.
- The schematic and its BOM mark the 1.8 V link DNP. The PCB footprint of the same resistor is
  fitted. Symbols and footprints each carry their own DNP flag in KiCad, and the two can differ.
- Built from the BOM, the board is right. Built from files generated from the PCB (a position
  file, a PCB-side BOM), both links are placed and the 1.8 V and 3.3 V rails are shorted through
  two 0 ohm resistors and the fuse.

## Why it was caught, and why it is easy to miss

- prep's 3-way compare reads the footprint DNP flag from the `.kicad_pcb` and lists every part
  fitted in one source and DNP in another. A review that reads only the BOM sees a correct
  board, and pin-and-net checks see two resistors on the right nets.
- The review did not stop at the discrepancy. It kept the connectivity model, which agreed in
  all three netlists, raised one NET-7 finding, and analyzed the option network in both fitted
  states.
- The verifier confirmed the data mismatch and kept the electrical consequence conditional on
  which files the assembler uses. The finding went out as major, not blocker, because the
  supplied BOM avoids the short.
- Bench step before first power: confirm the 1.8 V link is absent and measure no low resistance
  between the two rails.

## The checks that catch it now

- [NET-7](../checklists/netlist_integrity.md): fitted state agrees between the BOM, the
  schematic and the PCB; a bounded difference is a finding, analyzed in both fitted states.
- [NET-1](../checklists/netlist_integrity.md): the 3-way compare lists fitted-state differences.
- [Extract gate](../workflow/10_extract.md): a bounded discrepancy does not stop the review.
