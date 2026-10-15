# Strap pairs fitted on both sides

**Rule:** compute every strap pin's voltage from the parts fitted in the released variant plus
the internal pull, and read the fitted state from the BOM that goes to assembly
([straps_and_boot_pins STR-1 to STR-3](../checklists/straps_and_boot_pins.md),
[netlist_integrity NET-7](../checklists/netlist_integrity.md)).

Board: Sauron rev1. Part: ADIN1200 Ethernet PHY.
Status: found in July, found again in August, reached the boards anyway; reworked 2026-10-07.

## What happened

- Each ADIN1200 strap had a 10k pull-up and a 10k pull-down footprint, meant as "fit one side".
  The released BOM listed both sides fitted on all nine pairs.
- With the PHY's internal pull-down (45 kohm typical), each MAC interface select pin sat at
  `3.3 * 8.18 / (10 + 8.18) = 1.485 V`, below VIH = 2.0 V (ADIN1200 Rev B Table 1 p.6). The PHY
  latched RGMII on a board wired for RMII. RMII cannot be set by software afterward (p.33).
- At bring-up MDIO worked, the mode registers read back RGMII, and there was no link. Removing
  nine resistors fixed it: the straps decoded RMII and the link came up at 100 Mbit/s full duplex.

## Why the reviews missed it

- The July review found it. The August review found it again: the fix had never reached the BOM.
  The release notes listed the strap DNPs as done; the BOM sent to assembly had no variant data
  and its DNP list named other parts.
- Review staging carried no fitted or DNP state, so no reviewer could see what would be built.
- Some strap dividers sat one 22 ohm series resistor away from the PHY pin. Per-net checks that
  stop at the first resistor counted 11 doubled straps instead of 14.

## The checks that catch it now

- [STR-1](../checklists/straps_and_boot_pins.md): pin voltage with the internal pull.
- [STR-2](../checklists/straps_and_boot_pins.md): fitted state from the released variant.
- [STR-3](../checklists/straps_and_boot_pins.md): trace through series resistors.
- [STR-6](../checklists/straps_and_boot_pins.md): strap readback in the bench plan.
- [NET-7](../checklists/netlist_integrity.md): variant data present.
- [NET-4](../checklists/netlist_integrity.md): prior fixes re-verified in the data.
