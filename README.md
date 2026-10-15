# board-review

A Claude Code skill for schematic and board reviews that catch what a pin-and-net check misses:
loop stability, LC tanks, sink capability between rails, straps, reset margins, abs-max under
real conditions. Altium first (through eda-agent), KiCad next, one board model for both.

## Principles

1. **Facts before judgment.** Scripts build the board model and datasheet facts. The model judges,
   and every judgment cites a pin, a net, a datasheet page, or a calculator result.
2. **Show the math.** Every check that has a number runs a calculator and prints the formula,
   inputs and result.
3. **"Not published" is an answer.** When a datasheet hides a value (internal compensation, bead
   SRF), the finding becomes a required footprint or a bench test, never a guess.
4. **Every finding survives a refutation pass** by a second agent before it is reported.
5. **Measured by real misses.** The eval set is boards we already know the bugs of. A review that
   misses one is a checklist bug.

## Layout

```
skill/                    installable skill (link into ~/.claude/skills/board-review)
  SKILL.md                entry point: when to use, workflow, rules, finding format
  workflow/               one page per stage: intake, extract, datasheets, blocks, checks, verify, report
  checklists/             one page per circuit block (buck, ldo, ferrite/LC, pdn, clocks, resets,
                          io levels, straps, ethernet, csi, xspi memory, protection, sequencing, thermal)
  schemas/                board_model, datasheet_digest, finding (JSON Schema)
tools/boardreview/        Python package the skill calls
  model/                  netlist, BOM and pin map from Altium, KiCad and IPC-D-356; 3-way compare
  lint/                   deterministic checks: single-pin nets, open IC pins, floating grounds, names
  blocks/                 find regulators, filters, interfaces, clocks and resets in the netlist
  calc/                   calculators: buck, loop (Bode, PM/GM, Cff), lc_tank, mlcc_bias, divider,
                          crystal, i2c, tvs, thermal
  sim/                    LTspice batch runs (ngspice optional): loop-gain injection, load step,
                          PDN and filter impedance, with netlist sanity checks before trusting a run
  report/                 markdown and HTML report
tests/                    calculator and model tests with worked numbers
evals/                    expected findings per board and the scorer (board data stays local)
docs/lessons/             one page per real miss: what, why, which check now catches it
```

## Data policy

See docs/CONVENTIONS.md for code and writing rules.

Board files, BOMs, schematics and vendor PDFs are never committed. Evals point to local paths
listed in `evals/<board>/sources.local.json` (ignored by git). Datasheet digests (our own notes with
page citations) and curve CSVs from vendor tools may be committed once reviewed.
