# I2C clock and data crossed at the MCU

**Rule:** check every bus signal's pin against the alternate function table, not against the net
name ([io_levels_and_domains IO-5](../checklists/io_levels_and_domains.md)).

Board: Sauron rev1. Part: STM32N657 I2C to the camera module.
Status: caught in the final July review.

## What happened

- The camera I2C SCL net landed on the MCU pin whose I2C function is SDA, and SDA on the SCL pin
  (PC10 and PC11). Net names were correct at both ends.
- The same pass found a debug UART TX on the wrong pin. An earlier pass had found a 3.3 V debug
  probe signal routed to a 1.8 V-domain pin.

## Why it is easy to miss

- Connectivity, net names and ERC are all correct. Only the pin's function is wrong. It was
  caught only when the reviewer checked each signal's ball against the alternate function table.

## The checks that catch it now

- [IO-5](../checklists/io_levels_and_domains.md): pin function and order.
- [IO-1](../checklists/io_levels_and_domains.md): levels across domains.
- [NET-8](../checklists/netlist_integrity.md): symbol pins against the datasheet.
