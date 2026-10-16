# Netlist integrity

Run during workflow/10_extract.md, before any judgment, and again after every change. These checks
find errors that make the rest of the review read the wrong circuit.
Missing data: follow the not-published rule in workflow/40_checks.md unless the item says more.

## NET-1 Three netlists agree
- Check: schematic netlist, PCB netlist and fab netlist (IPC-D-356 or ODB++) list the same nets
  with the same pins.
- Why: the board that is built is the fab data, not the schematic.
- Compute: `model.compare` over the three netlists.
- Pass: zero differences, or each difference explained and accepted.

## NET-2 Name collisions across hierarchy
- Check: the same net name declared in different scopes (harnesses, buses, sheet-local labels,
  ports). Compile warnings such as "duplicate nets" count.
- Why: a schematic can keep two nets apart by scope while the PCB, keyed by name, merges them
  into one: a hard short between two buses.
- Compute: compiler messages; `model.compare` nets merged between schematic and PCB;
  `lint.nets.near_duplicate_rails` for names that differ only in spelling or case.
- Pass: zero duplicate-net warnings before any schematic-to-PCB update.
- Example: [bus net name collision](../lessons/bus-net-name-collision.md)

## NET-3 Project contents complete
- Check: documents in the project against documents in the hierarchy and files on disk; part
  count per sheet against the previous snapshot.
- Why: a parent sheet removed from the project drops its children from the compile without an
  error; the netlist simply loses those circuits.
- Compute: `model.compare` against the previous snapshot; sheet list from the tool.
- Pass: every sheet in the hierarchy compiles; no unexplained drop in parts or nets.
- Example: [sheet dropped from the compile](../lessons/sheet-dropped-from-compile.md)

## NET-4 Diff after every change
- Check: after each fix batch or ECO, re-extract and diff against the last snapshot: parts and
  nets added or removed, renamed nets, pins that moved net. Every power net has exactly one
  source (or a deliberate OR). Every earlier finding marked fixed is checked in the new data.
- Why: label and rail renames create silent regressions (a rail with no source, a chip select left
  off), and fixes recorded as done are sometimes never applied.
- Compute: `model.compare` against the previous snapshot; power-net sources from the power tree
  (no lint check yet).
- Pass: every change in the diff is explained by an intended edit.
- Example: [fix batch regressions](../lessons/fix-batch-regressions.md)

## NET-5 Lint
- Check: single-pin nets, unconnected IC pins against the datasheet's NC list, floating inputs,
  power pins on the wrong rail, empty or control-character labels, unannotated designators.
- Why: cheap to find mechanically, expensive on the bench.
- Compute: `lint.run_all`; floating inputs, labels and designators from the staging views (no
  lint check yet).
- Pass: every lint result fixed or waived with a reason. An open, NC or option pin (unused
  PGOOD, MODE or address pin tied off, a pin the symbol calls NC) passes only with a source: the
  digest pin table or a datasheet page that allows that state for the selected mode. A schematic
  no-connect flag, a pin name or the lint result itself is not a source.
- Not published: no source for the pin's unused state, or no digest for the part. The pin stays
  unknown with a vendor question; a pin that could float an input gets a pull footprint.

## NET-6 Value outliers
- Check: resistor values off by a decade or more from their divider partner or from parts with
  the same role; unit mistakes (ohm for kohm); BOM value against schematic value.
- Why: a value typo keeps correct connectivity.
- Compute: value scan by role from the staging views (no lint check yet);
  `calc.divider.enable_thresholds` or `calc.divider.regulator_output` on every divider
  (enable_uvlo_sequencing EN-1).
- Pass: every outlier explained.
- Example: [UVLO resistor decade typo](../lessons/uvlo-resistor-decade-typo.md)

## NET-7 Variant data present and consistent
- Check: the BOM carries fitted and DNP state per variant, and the variant reviewed is the one
  ordered for assembly. The fitted state of every part agrees between the BOM, the schematic and
  the PCB, because assembly files generated from the PCB (position file, PCB-side BOM, ODB++)
  carry the footprint's own DNP flag.
- Why: without variant data every strap pair and option footprint is unreviewable. A DNP flag
  that never reached the PCB fits a part the BOM leaves off.
- Compute: `model.bom.read_bom` with the variant columns; `lint.parts.bom_netlist_mismatch` and
  `lint.parts.fitted_without_mpn`; `model.compare` lists parts fitted in one source and DNP in
  another (`compare.md`).
- Pass: variant table present and matches the assembly order; no part fitted in one source and
  DNP in another. A bounded difference is a finding, not a stop: analyze the circuit in both
  fitted states (workflow/10_extract.md, Gate).
- Example: [strap pairs fitted on both sides](../lessons/strap-pairs-fitted-both-sides.md),
  [DNP in the schematic, fitted in the PCB](../lessons/dnp-in-schematic-fitted-in-pcb.md)

## NET-8 Symbol pins against the datasheet
- Check: every IC symbol's pin numbers and names against the digest pin table, including
  multi-part symbols and package variants.
- Why: a symbol drawn from a different package swaps functions on correct-looking nets.
- Compute: pin maps from stage 1 against the digest pin table (no lint check yet).
- Pass: exact match.
