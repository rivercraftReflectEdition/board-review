# 3. Blocks

Goal: every part belongs to a block, every block has a checklist, and the cross-block structures
(power tree, domain map, strap map) exist before checks start.

## Detect

Start from `blocks.md` and `blocks.json`, which `python -m boardreview prep` wrote in stage 1
(`blocks.find_all`; rerun alone with `python -m boardreview.blocks <facts>/board_model.json
--json blocks.json`). It proposes candidates from the board model only: switching regulators
(an IC pin and an inductor on a switch node), bead and LC filters (an inductor or bead followed
by capacitance on a rail), crystals and oscillators, reset nets with their supervisors, I2C
buses, and straps (pull resistors that set one IC pin). Each candidate carries its evidence and
a confidence; a low-confidence block is a lead, not a fact.

It does not find LDOs, interfaces (PHY, camera, memory) or protection parts, and it does not
read the datasheet digests, so it cannot tell which pins are sampled at reset. The agent
confirms each candidate, adds what the detector missed from `nets_by_component.md` and the
digests, and lists every part with no block and why (for example mounting holes, fiducials, test
points).

## Record each block instance

In `blocks.json`: checklist name, instance name, parts, nets, input and output rails, operating
point (VIN, VOUT, load, fsw), mode settings decoded from straps, and digest references.

## Power tree

Start from `power_tree.md` from stage 1: rails with their evidence, the converters and
filters `blocks` found, and every pin per rail. Nodes are rails; edges are regulators, load
switches and filters. For each edge: source part,
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
