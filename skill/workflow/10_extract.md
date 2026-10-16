# 1. Extract

Goal: a board model that matches what will be built, and the mechanical checks that prove it.
No judgment of circuits until this stage passes. If it fails badly (a missing sheet, merged
buses, netlists that disagree in ways nobody can explain), stop and report that first; every
later stage would review the wrong circuit. A missing tool or a bounded discrepancy is not a stop
(Gate, below).

## What the tools read

`python -m boardreview prep` reads netlists as IPC-D-356 (`.ipc`, `.d356`), KiCad XML netlist,
KiCad board (`.kicad_pcb`), Protel `.NET`, eda-agent JSON or an earlier `board_model.json`, and
BOMs as CSV or XLSX. It does not read PADS or tabular netlists, KiCad s-expression netlists,
ODB++, IPC-2581, pick-and-place files or PDFs. Placement comes from a `.kicad_pcb` given to prep
(`placement.md`, and `placement.json` for the report), or from an IPC-D-356 file when there is no
board file; otherwise, and for stackup, rules, polygons and page references, from the CAD
tool or the PDF by hand.

## Altium through the eda-agent MCP tools

1. `proj_open`, then `proj_get_compile_freshness`; `proj_compile` or `proj_force_recompile`.
2. `proj_list_documents`: compare with the sheet hierarchy and with the files on disk (NET-3).
3. `proj_get_erc_violations` and `proj_get_messages`: keep every duplicate-net and
   net-label warning (NET-2).
4. Schematic netlist: save one JSON object with the results of `proj_get_bom` (every component
   with its pin-net connections) under `bom`, `proj_get_component_info_many` (MPN, parameters,
   sheet) under `component_info`, and `proj_list_variants` under `variants`. prep reads it as
   eda-agent JSON; pass `--variant` with the assembly variant. `proj_export_netlist` writes PADS
   or tabular CSV, which prep does not read.
5. BOM and variants: `proj_get_active_variant` and `proj_export_variant_matrix_csv`. A BOM with
   variant columns can go in as `--bom`. Fitted state per variant is required (NET-7).
6. Symbol pins: `lib_get_pin_list` (NET-8, by hand against the digests).
7. PCB, by hand for the layout checklist: `pcb_get_components` (position, side),
   `pcb_get_layer_stackup`, `pcb_get_design_rules`, `pcb_get_polygons`. PCB netlist: a JSON
   list of `pcb_get_component_pads` results, one per component, read as eda-agent JSON. UNSURE:
   no test fixture has this shape; check the part and pin counts in `facts.md` against the PCB.
8. Fab netlist: IPC-D-356A from the fab outputs (`proj_run_outjob` or
   `proj_generate_fab_package`, with an IPC-356 container enabled in the OutJob).
   `proj_compare_sch_pcb` and `proj_get_differences` cross-check the tool's own sync state but do
   not replace the 3-way compare.
9. Pages: `proj_export_pdf` for page references.

Bridge habits:
- Calls run one at a time. Do not fan out calls to the bridge.
- Large results are saved to files. Read them from disk in slices; keep them out of context.
- DRC and some exports can hang on large boards. Run DRC natively and import the report.
- The bridge stalls while the designer works in the tool. Prefer staged files during that time.
- Check compile freshness before every pull after an edit.

## Released files without a live tool

prep reads the IPC-D-356A fab netlist, an exported netlist in KiCad XML or Protel format, a KiCad
board file, and the BOM with variant columns (CSV or XLSX). Read the schematic PDF for pages, and
the pick-and-place file or ODB++ for placement when there is no `.kicad_pcb`, by hand.

When kicad-cli or the CAD tool cannot run here (not installed, blocked by a sandbox as in
workflow/setup.md, no license), use the exports the user supplies and continue. Say in
intake.md what is lost:
- ERC and compiler messages (NET-2 duplicate nets, NET-3 project contents).
- The tool's native schematic-to-PCB parity (`--schematic-parity`, `proj_compare_sch_pcb`). The
  3-way compare still runs on the exports.
- Export freshness: nothing proves the exports match the latest schematic and board edits.
  Record each file's date and hash, and ask when the exports were made.
- PDF page references, when no schematic PDF was supplied.

Each is an open gate item: the review goes on, the report lists it under what was not checked,
and any check that needs it stays unknown.

## KiCad through kicad-cli

Verified with KiCad 10.0.6 on Windows (October 2026) on the demo projects that ship with KiCad.
KiCad 8 and 9 have the same schematic exports; `pcb export ipcd356`, `--schematic-parity` and
`--variant` are UNSURE before KiCad 10 (check with `kicad-cli <command> --help`).

Find kicad-cli: `kicad-cli` on PATH; Windows per-user install
`%LOCALAPPDATA%\Programs\KiCad\<version>\bin\kicad-cli.exe`; Windows all-users install
`%ProgramFiles%\KiCad\<version>\bin\kicad-cli.exe`; macOS
`/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`; Linux `/usr/bin/kicad-cli`. Record
`kicad-cli version` in intake.md.

Write outputs into the review folder, not among the design files, and run the schematic commands
on the root sheet (`<project>.kicad_sch`), which pulls in the whole hierarchy:

```
kicad-cli sch export netlist --format kicadxml -o out/sch.xml board.kicad_sch
kicad-cli sch export bom --fields "Reference,Value,Footprint,MPN,DNP" -o out/bom.csv board.kicad_sch
kicad-cli pcb export ipcd356 -o out/fab.d356 board.kicad_pcb
kicad-cli sch erc --format json -o out/erc.json board.kicad_sch
kicad-cli pcb drc --schematic-parity --severity-all --format json -o out/drc.json board.kicad_pcb
kicad-cli sch export pdf -o out/sch.pdf board.kicad_sch
kicad-cli pcb export pos --format csv --units mm -o out/pos.csv board.kicad_pcb
python -m boardreview prep out/sch.xml --bom out/bom.csv --compare board.kicad_pcb out/fab.d356 --out <review folder>/facts
```

- Netlist: always `kicadxml`; prep rejects KiCad's s-expression netlist. KiCad 10 appends the pin
  number to every pin function (`VOUT_5`); prep removes it.
- BOM: one row per part (no `--group-by`) with value, footprint, MPN and DNP. Put the project's
  own MPN field name in `--fields` when it is not `MPN` (for example `Manufacturer_Part_Number`).
  The netlist carries every symbol field, and prep also reads MPN and manufacturer from it under
  the common names. With `--fields`, KiCad uses the field names as headers; the default export
  (`Refs`, `Qty`, grouped references) reads too. Parts marked "exclude from BOM" are absent from
  it by design: prep lists them apart and flags any that are fitted.
- Variants: for KiCad 10 design variants, add `--variant <name>` to the netlist and BOM exports
  for the assembly variant.
- PCB: compare against the `.kicad_pcb` file itself. It has full net names, the DNP attribute of
  each footprint (prep compares fitted state) and position, side and rotation (`placement.md`),
  and needs no kicad-cli. The IPC-D-356 export is the third source, the fab netlist.
- KiCad's IPC-D-356 keeps only the last 14 characters of a net name, in upper case
  (`/CSI/CAM_I2C_SCL` becomes `SI/CAM_I2C_SCL`), 6 of a designator and 4 of a pin number, writes
  `?` for a space, and writes no alias records. prep reports these as format limits, not as
  renames, and reads cut `unconnected-(...)` names as no net. A difference in a cut-off part
  cannot be seen in that file; the `.kicad_pcb` compare covers it.
- `--schematic-parity` is KiCad's own check of the board against the schematic. Read its
  `schematic_parity` list next to `compare.md`; it does not replace the compare.
- ERC, DRC, PDF and positions are read by hand.

## Build

Run from any folder once the package is installed (SKILL.md, Setup), one output folder per
snapshot:

```
python -m boardreview prep SCH_NETLIST --bom BOM --compare PCB_NETLIST FAB_NETLIST --out <review folder>/facts
```

1. Board model (`model.loaders.load_with_bom`): `board_model.json` with parts (designator, MPN,
   value, fitted, variant, kind), pins (number, name, net), nets and warnings; `bom_check.json`
   with parts only in the BOM, only in the netlist, or excluded from the BOM by the schematic.
   Pages are not in the model; position and side are in `placement.md` and `placement.json`,
   from a `.kicad_pcb` when given, else from IPC-D-356 pad centres.
2. 3-way compare (NET-1, `model.compare`): the first netlist is the naming reference; default
   labels are schematic, pcb, fab (`--labels` to change). Writes `compare.md` and
   `compare.json`. Connectivity differences come first; format limits (IPC-D-356 field cuts),
   pins with no net present in one source only, and mechanical, pinless or board-excluded parts
   are listed apart and are not connectivity differences. Fitted state is compared where both
   sources state it.
3. Lint (NET-2, NET-5, NET-7, `lint.run_all`): `lint.md`, `lint.json`, and `lint_findings.json`
   with each result as a candidate finding (`lint.to_findings`, verification PENDING). Floating
   inputs (NET-5), value outliers (NET-6) and symbol pins against digests (NET-8) have no lint
   check yet; do them from the staging views, and re-run NET-8 after stage 2.
4. Snapshot diff (NET-3, NET-4) against the previous review's snapshot, then re-verify every
   prior fix:
   `python -m boardreview.model compare <review folder>/facts/board_model.json <previous>/facts/board_model.json --labels current,previous --out <review folder>/snapshot_diff`
5. Staging views, small and one per purpose: `nets_by_net.md`, `nets_by_component.md` (with pin
   names), `power_tree.md`, `pinmaps/<REF>.md`, and `placement.md` (from the `.kicad_pcb`, or
   IPC-D-356 pad centres without one). A BOM
   table with variant is not generated; make it by hand when a check needs it. Agents read
   slices, not dumps.
6. Block candidates for stage 3 (`blocks.find_all`): `blocks.md` and `blocks.json`.
7. `facts.md`: the input files with SHA-256, every file written with its counts, every check
   skipped and why, and what prep does not run. Read it first and copy the hashes into
   intake.md.

## Gate

Run every netlist_integrity item. Record results in the review folder, each as passed, failed or
open. The gate passes with open items when each is named with what it costs; it stops the review
only when the connectivity model itself cannot be trusted.

A bounded assembly discrepancy does not stop the review. For example, one part is DNP in the
schematic and BOM but fitted in the PCB (`compare.md` lists fitted-state differences). Raise it
as a NET-7 finding, keep the rest of the connectivity model, and run every check that touches
the part in both fitted states. Its severity follows the worse state, weighed by which files the
assembler builds from.

Lessons behind this gate:
[bus net name collision](../lessons/bus-net-name-collision.md),
[sheet dropped from the compile](../lessons/sheet-dropped-from-compile.md),
[fix batch regressions](../lessons/fix-batch-regressions.md),
[DNP in the schematic, fitted in the PCB](../lessons/dnp-in-schematic-fitted-in-pcb.md).
