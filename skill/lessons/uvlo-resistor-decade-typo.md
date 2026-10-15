# UVLO resistor with a decade typo

**Rule:** compute every enable and UVLO divider from BOM values, and scan for resistor values a
decade or more off from their partners
([enable_uvlo_sequencing EN-1](../checklists/enable_uvlo_sequencing.md),
[netlist_integrity NET-6](../checklists/netlist_integrity.md)).

Board: Sauron rev1, early front end. Part: LM5116 buck controller (later replaced by an LT8640
when the input bus changed to 12 V).
Status: caught in the July schematic review.

## What happened

- The UVLO divider's bottom resistor was 27.4 ohm ("27R4") instead of 27.4 kohm ("27K4").
- At 28 V input the UVLO pin sat near 4 mV. Turn-on would have needed about 8.9 kV. The converter
  would never have started. With 27.4 kohm, turn-on was 9.1 V.

## Why it is easy to miss

- Connectivity is correct, ERC is clean, and pin-and-net checks pass. Only arithmetic on the value
  finds it.

## Why it was caught

- The review computed every divider from its BOM values and compared the result with the
  intended threshold.

## The checks that catch it now

- [EN-1](../checklists/enable_uvlo_sequencing.md): every divider computed from BOM values.
- [NET-6](../checklists/netlist_integrity.md): value outlier scan.
