# Oscillator output in the wrong voltage domain

**Rule:** check a clock input's reference supply, which may not be the I/O rail, and check the
oscillator's supply and enable after any part number change
([clocks_crystals CLK-1](../../skill/checklists/clocks_crystals.md)).

Board: Sauron rev1. Parts: SiT2024 oscillator into the STM32N657 HSE input in bypass mode.
Status: caught in July; the first fix was incomplete and was caught in the next round.

## What happened

- The oscillator was ordered in a 3.3 V supply code and drove OSC_IN. In bypass mode OSC_IN is
  referenced to the 1.8 V analog always-on supply, so a 3.3 V clock exceeded the input's range.
- Fix: the 1.8 V variant (-18E suffix) powered from 1V8. The next review found the part number
  changed but the oscillator's VDD and OE still on 3V3.
- OSC_OUT tied to ground through a 0 ohm resistor looked wrong to several reviewers. It is the
  datasheet's strap for digital bypass. It went on the known-good list.

## Why it is easy to miss

- The clock net is connected and named correctly. The level problem lives in the supply-code
  suffix of the part number and in a footnote on the input's reference supply.

## The checks that catch it now

- [CLK-1](../../skill/checklists/clocks_crystals.md): output level against the receiver's domain.
- [CLK-4](../../skill/checklists/clocks_crystals.md): bypass straps per the datasheet.
- [IO-2](../../skill/checklists/io_levels_and_domains.md): pin abs max.
- [NET-4](../../skill/checklists/netlist_integrity.md): re-check after the fix.
