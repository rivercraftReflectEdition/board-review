# 3. Blocks

Goal: every part belongs to a block, every block has a checklist, and the cross-block structures
(power tree, domain map, strap map) exist before checks start.

## Detect

`blocks` proposes candidates from the board model and digests: regulators (by part class and
pin names), bead and LC filters (an inductor or bead followed by capacitance on a rail),
interfaces (PHY, camera, memory), clocks, resets and supervisors, straps (resistors on pins the
digests mark as sampled at reset), protection parts.

The agent confirms each candidate, adds what the detector missed, and lists every part with no
block and why (for example mounting holes, fiducials, test points).

## Record each block instance

In `blocks.json`: checklist name, instance name, parts, nets, input and output rails, operating
point (VIN, VOUT, load, fsw), mode settings decoded from straps, and digest references.

## Power tree

Nodes are rails; edges are regulators, load switches and filters. For each edge: source part,
mode (forced continuous, pulse skip, burst), whether it can sink, soft-start and enable source.
For each rail: every load with its abs max and recommended range, total capacitance, and every
part that can return current. The power tree drives cascaded_rails, enable_uvlo_sequencing and
pdn_decoupling.

## Domain map

The reference supply of every IC pin (from digest `pins[].domain`), and every net that connects
pins of different domains or ties a pin to a supply through a resistor. Drives
io_levels_and_domains, resets_supervisors_watchdogs and camera_csi.

## Strap map

Every pin sampled at reset with its full network, traced through series resistors to every
other load on the net (STR-3), and the fitted state of each part in the released variant.

## Output

`blocks.json`, `power_tree.json`, `domains.json`, `straps.json` in the review folder. Cross-block
checklists run once over these structures, not once per block.
