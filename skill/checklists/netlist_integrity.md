# Netlist integrity

Run during workflow/10_extract.md, before any judgment, and again after every change. These checks
find errors that make the rest of the review read the wrong circuit.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## NET-1 Three netlists agree
- Check: schematic netlist, PCB netlist and fab netlist (IPC-D-356 or ODB++) list the same nets
  with the same pins.
- Why: the board that is built is the fab data, not the schematic.
- Compute: `model` 3-way compare.
- Pass: zero differences, or each difference explained and accepted.

## NET-2 Name collisions across hierarchy
- Check: the same net name declared in different scopes (harnesses, buses, sheet-local labels,
  ports). Compile warnings such as "duplicate nets" count.
- Why: a schematic can keep two nets apart by scope while the PCB, keyed by name, merges them
  into one: a hard short between two buses.
- Compute: `lint` duplicate-name scan; compiler messages.
- Pass: zero duplicate-net warnings before any schematic-to-PCB update.
- Example: [bus net name collision](../../docs/lessons/bus-net-name-collision.md)

## NET-3 Project contents complete
- Check: documents in the project against documents in the hierarchy and files on disk; part
  count per sheet against the previous snapshot.
- Why: a parent sheet removed from the project drops its children from the compile without an
  error; the netlist simply loses those circuits.
- Compute: `model` snapshot diff.
- Pass: every sheet in the hierarchy compiles; no unexplained drop in parts or nets.
- Example: [sheet dropped from the compile](../../docs/lessons/sheet-dropped-from-compile.md)

## NET-4 Diff after every change
- Check: after each fix batch or ECO, re-extract and diff against the last snapshot: parts and
  nets added or removed, renamed nets, pins that moved net. Every power net has exactly one
  source (or a deliberate OR). Every earlier finding marked fixed is checked in the new data.
- Why: label and rail renames create silent regressions (a rail with no source, a chip select left
  off), and fixes recorded as done are sometimes never applied.
- Compute: `model` snapshot diff; `lint` power-net source check.
- Pass: every change in the diff is explained by an intended edit.
- Example: [fix batch regressions](../../docs/lessons/fix-batch-regressions.md)

## NET-5 Lint
- Check: single-pin nets, unconnected IC pins against the datasheet's NC list, floating inputs,
  power pins on the wrong rail, empty or control-character labels, unannotated designators.
- Why: cheap to find mechanically, expensive on the bench.
- Compute: `lint`.
- Pass: every lint result fixed or waived with a reason.

## NET-6 Value outliers
- Check: resistor values off by a decade or more from their divider partner or from parts with
  the same role; unit mistakes (ohm for kohm); BOM value against schematic value.
- Why: a value typo keeps correct connectivity.
- Compute: `lint` value scan; `calc.divider` on every divider (enable_uvlo_sequencing EN-1).
- Pass: every outlier explained.
- Example: [UVLO resistor decade typo](../../docs/lessons/uvlo-resistor-decade-typo.md)

## NET-7 Variant data present
- Check: the BOM carries fitted and DNP state per variant, and the variant reviewed is the one
  ordered for assembly.
- Why: without variant data every strap pair and option footprint is unreviewable.
- Compute: `model` BOM import with variant.
- Pass: variant table present and matches the assembly order.
- Example: [strap pairs fitted on both sides](../../docs/lessons/strap-pairs-fitted-both-sides.md)

## NET-8 Symbol pins against the datasheet
- Check: every IC symbol's pin numbers and names against the digest pin table, including
  multi-part symbols and package variants.
- Why: a symbol drawn from a different package swaps functions on correct-looking nets.
- Compute: `lint` pin-map compare against digests.
- Pass: exact match.
