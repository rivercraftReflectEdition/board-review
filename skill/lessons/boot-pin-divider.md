# Boot pin divider that selects serial boot forever

**Rule:** compute each boot pin's level from the fitted parts, and make every boot mode the board
needs reachable without soldering
([straps_and_boot_pins STR-5](../checklists/straps_and_boot_pins.md)).

Board: Sauron rev1. Part: STM32N657 BOOT0 and BOOT1 (PA6).
Status: July, both boot pins floated (fixed). August 24, BOOT0 had both resistors fitted (fixed
before fab). Bring-up: mode changes needed soldering.

## What happened

- The July fix added a 10k pull-down and a 10k pull-up footprint on BOOT0, the pull-up meant as
  DNP for serial recovery. With no variant data, both were fitted.
- BOOT0 sat at 1.65 V against VIH minimum 1.606 V (`VIH = 0.52 * VDD - 0.11` at 3.3 V; DS14791
  Rev 9 Table 65 p.169). It read 1 by 44 mV nominal. With BOOT1 low the part entered serial boot
  on every reset (AN5967 Rev 4 Table 8 p.18). Flash boot was impossible without rework.
- At bring-up, moving between development boot and flash boot meant fitting or removing an 0402
  pull-up on BOOT1 by hand, several times.

## Why it was missed in July

- The pins were connected and had resistors. The divider was not computed against VIH, and the
  intended DNP lived only in the review notes.

## The checks that catch it now

- [STR-5](../checklists/straps_and_boot_pins.md): boot pin levels and reachable modes.
- [STR-1](../checklists/straps_and_boot_pins.md) and
  [STR-2](../checklists/straps_and_boot_pins.md): level and fitted state.
- [NET-7](../checklists/netlist_integrity.md): variant data present.
