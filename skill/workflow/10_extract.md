# 1. Extract

Goal: a board model that matches what will be built, and the mechanical checks that prove it.
No judgment of circuits until this stage passes. If it fails badly (a missing sheet, merged
buses), stop and report that first; every later stage would review the wrong circuit.

## Altium through the eda-agent MCP tools

1. `proj_open`, then `proj_get_compile_freshness`; `proj_compile` or `proj_force_recompile`.
2. `proj_list_documents`: compare with the sheet hierarchy and with the files on disk (NET-3).
3. `proj_get_erc_violations` and `proj_get_messages`: keep every duplicate-net and
   net-label warning (NET-2).
4. Schematic netlist: `proj_export_netlist` or `proj_get_nets` with
   `proj_get_connectivity_many` for pin names.
5. BOM and variants: `proj_get_bom`, `proj_list_variants`, `proj_get_active_variant`,
   `proj_export_variant_matrix_csv`. Fitted state per variant is required (NET-7).
6. Parts: `proj_get_component_info_many` for MPN and parameters; `lib_get_pin_list` for symbol
   pins (NET-8).
7. PCB: `pcb_get_components` (position, side), `pcb_get_nets`, `pcb_get_component_pads`,
   `pcb_get_layer_stackup`, `pcb_get_design_rules`, `pcb_get_polygons`.
8. Fab netlist: IPC-D-356A from the fab outputs (`proj_run_outjob` or
   `proj_generate_fab_package`). `proj_compare_sch_pcb` and `proj_get_differences` cross-check the
   tool's own sync state but do not replace the 3-way compare.
9. Pages: `proj_export_pdf` for page references.

Bridge habits:
- Calls run one at a time. Do not fan out calls to the bridge.
- Large results are saved to files. Read them from disk in slices; keep them out of context.
- DRC and some exports can hang on large boards. Run DRC natively and import the report.
- The bridge stalls while the designer works in the tool. Prefer staged files during that time.
- Check compile freshness before every pull after an edit.

## Released files without a live tool

Schematic PDF, BOM with variant columns, IPC-D-356A or ODB++, pick-and-place, and an exported
netlist. `model` reads these directly.

## KiCad through kicad-cli

```
kicad-cli sch export netlist --format kicadsexpr -o out/sch.net board.kicad_sch
kicad-cli sch export bom --fields "Reference,Value,Footprint,MPN,DNP" -o out/bom.csv board.kicad_sch
kicad-cli sch erc --format json -o out/erc.json board.kicad_sch
kicad-cli sch export pdf -o out/sch.pdf board.kicad_sch
kicad-cli pcb export pos --format csv -o out/pos.csv board.kicad_pcb
kicad-cli pcb drc --format json -o out/drc.json board.kicad_pcb
```

PCB pad nets come from the `.kicad_pcb` file through `model`. Fab netlist: `kicad-cli pcb export
ipcd356` on KiCad 9 (UNSURE for older versions; use the PCB editor's fabrication outputs), or
ODB++ or IPC-2581. Variant (DNP) state comes from the DNP field and any variant tool in use.

## Build

1. `model` builds `board_model.json`: parts (designator, MPN, value, fitted per variant, side,
   position), pins (number, name, net), nets, pages, rails. Record source file hashes.
2. 3-way compare (NET-1): schematic netlist, PCB netlist, fab netlist.
3. `lint` (NET-2, NET-5, NET-6, NET-8): duplicate names, single-pin nets, open IC pins, floating
   inputs, value outliers, symbol pins against digests (re-run NET-8 after stage 2).
4. Snapshot diff (NET-3, NET-4) against the previous review's snapshot. Re-verify every prior fix.
5. Staging views for reviewers, small and one per purpose: nets by net, nets by part with pin
   names, BOM table with variant, power nets, placements. Agents read slices, not dumps.

## Gate

Run every netlist_integrity item. Record results in the review folder. Lessons behind this gate:
[bus net name collision](../../docs/lessons/bus-net-name-collision.md),
[sheet dropped from the compile](../../docs/lessons/sheet-dropped-from-compile.md),
[fix batch regressions](../../docs/lessons/fix-batch-regressions.md).
