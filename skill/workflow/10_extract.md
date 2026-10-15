# 1. Extract

Goal: a board model that matches what will be built, and the mechanical checks that prove it.
No judgment of circuits until this stage passes. If it fails badly (a missing sheet, merged
buses), stop and report that first; every later stage would review the wrong circuit.

## What the tools read

`python -m boardreview prep` reads netlists as IPC-D-356 (`.ipc`, `.d356`), KiCad XML netlist,
Protel `.NET`, eda-agent JSON or an earlier `board_model.json`, and BOMs as CSV or XLSX. It does
not read PADS or tabular netlists, KiCad s-expression netlists, `.kicad_pcb`, ODB++, IPC-2581,
pick-and-place files or PDFs. Placement, stackup, rules, polygons and page references come from
the CAD tool or the PDF by hand.

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

prep reads the IPC-D-356A fab netlist, an exported netlist in KiCad XML or Protel format, and the
BOM with variant columns (CSV or XLSX). Read the schematic PDF for pages, and the pick-and-place
file or ODB++ for placement, by hand.

## KiCad through kicad-cli

```
kicad-cli sch export netlist --format kicadxml -o out/sch.xml board.kicad_sch
kicad-cli sch export bom --fields "Reference,Value,Footprint,MPN,DNP" -o out/bom.csv board.kicad_sch
kicad-cli sch erc --format json -o out/erc.json board.kicad_sch
kicad-cli sch export pdf -o out/sch.pdf board.kicad_sch
kicad-cli pcb export pos --format csv -o out/pos.csv board.kicad_pcb
kicad-cli pcb drc --format json -o out/drc.json board.kicad_pcb
```

prep reads `sch.xml` and `bom.csv`; ERC, DRC, PDF and positions are read by hand. The KiCad
s-expression netlist format is rejected; export `kicadxml`. PCB and fab netlist: IPC-D-356 from
the PCB editor's fabrication outputs, or `kicad-cli pcb export ipcd356` on KiCad 9 (UNSURE for
older versions). prep does not read `.kicad_pcb`, ODB++ or IPC-2581. Variant (DNP) state comes
from the DNP field and any variant tool in use.

## Build

Run from the board-review repo with `tools/` on `PYTHONPATH`, one output folder per snapshot:

```
python -m boardreview prep SCH_NETLIST --bom BOM --compare PCB_NETLIST FAB_NETLIST --out <review folder>/facts
```

1. Board model (`model.loaders.load_with_bom`): `board_model.json` with parts (designator, MPN,
   value, fitted, variant, kind), pins (number, name, net), nets and warnings; `bom_check.json`
   with parts only in the BOM or only in the netlist. Position, side and pages are not in the
   model yet.
2. 3-way compare (NET-1, `model.compare`): the first netlist is the naming reference; default
   labels are schematic, pcb, fab (`--labels` to change). Writes `compare.md` and
   `compare.json`.
3. Lint (NET-2, NET-5, NET-7, `lint.run_all`): `lint.md`, `lint.json`, and `lint_findings.json`
   with each result as a candidate finding (`lint.to_findings`, verification PENDING). Floating
   inputs (NET-5), value outliers (NET-6) and symbol pins against digests (NET-8) have no lint
   check yet; do them from the staging views, and re-run NET-8 after stage 2.
4. Snapshot diff (NET-3, NET-4) against the previous review's snapshot, then re-verify every
   prior fix:
   `python -m boardreview.model compare <review folder>/facts/board_model.json <previous>/facts/board_model.json --labels current,previous --out <review folder>/snapshot_diff`
5. Staging views, small and one per purpose: `nets_by_net.md`, `nets_by_component.md` (with pin
   names), `power_tree.md`, `pinmaps/<REF>.md`. A BOM table with variant and placements are not
   generated; make them by hand when a check needs them. Agents read slices, not dumps.
6. Block candidates for stage 3 (`blocks.find_all`): `blocks.md` and `blocks.json`.
7. `facts.md`: the input files with SHA-256, every file written with its counts, every check
   skipped and why, and what prep does not run. Read it first and copy the hashes into
   intake.md.

## Gate

Run every netlist_integrity item. Record results in the review folder. Lessons behind this gate:
[bus net name collision](../../docs/lessons/bus-net-name-collision.md),
[sheet dropped from the compile](../../docs/lessons/sheet-dropped-from-compile.md),
[fix batch regressions](../../docs/lessons/fix-batch-regressions.md).
