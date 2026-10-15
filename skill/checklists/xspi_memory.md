# External xSPI memory (NOR, PSRAM, HyperBus, octal and quad SPI)

Applies to serial and octal flash, PSRAM and similar memories on xSPI-class controllers.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## MEM-1 Memory nets match the intended bus topology
- Check: write down the intended topology first: separate buses, or one bus shared by several
  devices. Then confirm the schematic, PCB and fab netlists match it. Signal names shared through
  harnesses, buses or hierarchical sheets must not merge buses meant to be separate (run
  netlist_integrity NET-2), and a shared bus must give each device the chip select the
  controller mode expects (one per device, or one shared select in a documented dual-memory
  mode).
- Why: nets keyed by name merge at PCB transfer even when the schematic kept them apart. A
  shared bus is legitimate when it is the intent; a merge by name is not.
- Compute: none; `model.compare` 3-way compare.
- Pass: every memory signal is on the net the intended topology puts it on, in all three
  netlists, and the chip selects match the controller mode.
- Example: [bus net name collision](../lessons/bus-net-name-collision.md)

## MEM-2 Every signal reaches the right controller port pin
- Check: CS, CK, DQS and data land on pins of the same controller port with the right alternate
  function; port multiplexing settings noted for firmware.
- Why: a chip select left off the controller after a bus split makes the memory unreachable.
- Compute: none; alternate function table against the netlist (io_levels_and_domains IO-5).
- Pass: complete, single-pinned signal set per memory.

## MEM-3 Protocol variant
- Check: the memory's actual interface (octal xSPI, HyperBus, quad SPI, SDR or DDR) from its
  datasheet against the controller mode and the design notes.
- Why: similar part families use different protocols; the wrong assumption breaks the driver.
- Compute: none.
- Pass: notes, driver plan and datasheet agree.

## MEM-4 I/O voltage and speed range
- Check: memory VCCQ against the controller bank voltage; any I/O range or high-speed setting the
  controller needs at that voltage (see io_levels_and_domains IO-4) and the maximum clock with and
  without it.
- Why: running at full speed without the range setting is out of spec.
- Compute: none; reference manual.
- Pass: settings listed in the firmware handoff.

## MEM-5 Reset and power coherence
- Check: RESET# pulled up in the memory's domain; reset pulse and recovery times; reset reaching
  the memory on every MCU reset source; the memory's power and whether it can be cycled alone.
- Why: a memory left in a non-default mode after a warm reset blocks the boot ROM; a memory that
  cannot be power-cycled alone is hard to recover on the bench.
- Compute: `calc.timing.budget`; resets_supervisors_watchdogs RST-1 and RST-5.
- Pass: reset reaches the memory from every source with valid levels and timing.

## MEM-6 Timing budget
- Check: setup and hold at the planned clock including board skew, controller delay-line range
  and temperature.
- Why: a bus that passes at room temperature on one board fails hot or on another board.
- Compute: `calc.timing.budget` for setup and hold at the worst corner.
- Pass: positive margin at worst corner; otherwise a bench delay sweep over temperature.

## MEM-7 Debug and rework options
- Check: series resistor footprints on clock, strobe and data; probe access to supply, reset, CS
  and clock near the device; removed series parts justified.
- Why: without probe points a failing BGA memory cannot be diagnosed.
- Compute: none.
- Pass: options present or their absence accepted in the report.

## MEM-8 Write protection
- Check: whether the part has a write-protect pin and how boot regions are protected.
- Why: without a hardware pin, protection is a firmware duty that must be stated.
- Compute: none.
- Pass: scheme written in the firmware handoff.
