# Regulator enable pull-ups holding MCU pins above abs max

**Rule:** any pull-up that ends on a logic pin must stay below that pin's abs max at the rail's
worst high ([io_levels_and_domains IO-2](../checklists/io_levels_and_domains.md),
[enable_uvlo_sequencing EN-5](../checklists/enable_uvlo_sequencing.md)).

Board: Sauron rev1. Parts: LTC3633A RUN pins, STM32N657 GPIOs.
Status: caught in the July schematic review.

## What happened

- The two RUN pins had 47k pull-ups to the 4 V rail and were also wired to two MCU pins for
  software enable. Those pins sat at 3.81 to 4.11 V continuously, above their 3.6 V abs max.
- Fix: remove the MCU connections and set RUN with a divider. The freed pins went to the debug
  port, which had been left unrouted.

## Why it is easy to miss

- An enable wired to an MCU looks like good practice. The pin's domain and abs max are on a
  different page from the regulator.

## The checks that catch it now

- [IO-2](../checklists/io_levels_and_domains.md): pin abs max with pull resistors.
- [EN-5](../checklists/enable_uvlo_sequencing.md): enables driven or watched by logic.
