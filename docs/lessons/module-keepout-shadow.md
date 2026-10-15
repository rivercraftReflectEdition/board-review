# Parts under a mezzanine module taller than the stack gap

**Rule:** check part heights inside every module, connector or shield footprint against the
mating stack height ([layout LAY-6](../../skill/checklists/layout.md)).

Board: Sauron rev1. Part: camera module (FRAMOS FSM:GO, about 26.5 mm) on a 1.5 mm stack.
Status: caught in the 2026-08-24 pre-fab review.

## What happened

- 86 top-side parts sat inside the module's footprint. Three were taller than the 1.5 mm gap,
  so the module could not seat.
- The module seated on the first assembled boards (fit check 2026-10-07). How the three parts
  were cleared is not in the notes read for this page (UNSURE).

## Why it is easy to miss

- Schematic review cannot see it, and DRC does not know the module's height unless a 3D body or
  height rule exists for the region under it.

## The checks that catch it now

- [LAY-6](../../skill/checklists/layout.md): mechanical keepouts and stack height.
- [CSI-6](../../skill/checklists/camera_csi.md): connector and keepout.
