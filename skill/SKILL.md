---
name: board-review
description: Schematic and PCB design review for Altium or KiCad boards. Use when asked to review a schematic, PCB, board, layout, power tree, ECO or design before fab or bring-up, or to check fixes from an earlier review. Builds a board model and datasheet digests first, then runs block checklists with calculators (loop margin against the datasheet's example envelope, LC tanks, reverse current between rails, straps, reset and enable margins, levels across domains, abs max), verifies every finding with a second-agent refutation pass, and reports each finding with its math plus a bench test plan.
---

# Board review

Pin-and-net checks find opens, shorts and wrong pins. Boards fail on the bench for other reasons:
a regulator outside the conditions its compensation was designed for, a bead and capacitor that
ring at the switching frequency, a rail that cannot absorb returned current, a strap at mid-rail,
a reset that does not assert at cold. This skill finds those, with numbers.

## When to use

- A schematic or PCB review before fab, before routing, or before an ECO is released.
- Re-verifying fixes from an earlier review (always re-extract; never trust the fix log).
- A bench failure that needs a design-level explanation (run the blocks involved).

Not for: library creation, routing, or firmware review.

## Workflow

Run the stages in order. Each stage has a page in `workflow/`. Do not judge before stage 2 ends.

| Stage | Page | Output (in the review's local folder, never in this repo) |
|---|---|---|
| 0 Intake | workflow/00_intake.md | intake.md: scope, revision, variant, requirements, prior findings |
| 1 Extract | workflow/10_extract.md | board_model.json, netlists, BOM with variant, compare and lint results |
| 2 Datasheets | workflow/20_datasheets.md | one digest per MPN (schemas/datasheet_digest.schema.json), curve CSVs |
| 3 Blocks | workflow/30_blocks.md | blocks.json and the power tree, each block mapped to a checklist |
| 4 Checks | workflow/40_checks.md | per-item results with calculator output; candidate findings |
| 5 Verify | workflow/50_verify.md | each finding CONFIRMED, WRONG or UNVERIFIABLE by a second agent |
| 6 Report | workflow/60_report.md | report.md, findings.json, bench test plan, known-good list |

Checklists live in `checklists/`, one per block type. Each item states the check, why it matters,
the calculator, the pass criterion, and what to do when the data is not published.

## Hard rules

1. **Facts before judgment.** Build the board model, run the 3-way netlist compare and lint, and
   write the datasheet digests before any finding. A finding drawn from memory of a part is not a
   finding.
2. **Cite everything.** Every claim names a pin (`U4.12`), a net, a schematic page, a datasheet
   document with revision and page, or a calculator result. No citation, no claim.
3. **Show the math.** Every number comes from a calculator in `tools/boardreview/calc` and the
   report prints its formula, inputs and outputs (`Result.to_markdown()`). Use worst-case
   corners: tolerance, temperature, bias, aging. Typical values are labeled typical.
4. **"Not published" is an answer.** When the documents do not give a value the check needs
   (internal compensation, bead inductance, sink current), say so in the digest. The finding
   becomes a required footprint, a bench test, or a vendor question. Never guess a value and
   never drop the check.
5. **Every finding survives refutation.** A second agent with fresh context tries to break each
   finding against the sources (workflow/50_verify.md). WRONG findings are dropped. UNVERIFIABLE
   findings carry a bench test. High-risk passes get the same treatment: a wrong pass is how
   real misses happen.
6. **Compare with the example envelope.** For every regulator, compare the operating point with
   the datasheet's example circuits for the same compensation mode. Correct pins do not mean a
   stable loop.
7. **Re-run after every change.** Any fix batch, ECO, rail change or variant change means
   re-extract, re-diff and re-run the affected checks.
8. **Board data stays local.** Never commit board files, netlists, BOMs, schematics, PDFs or
   screenshots. Digests and curve CSVs may be committed after review.
9. **Plain engineer prose.** Short sentences. State the number, the limit and the consequence.
   No filler. Mark anything unverified UNSURE and say what would settle it.

## Finding format

Each finding is one JSON object that validates against `schemas/finding.schema.json`. Required:

- `id`, `title` (one line: part or net, what fails), `severity` (blocker, major, minor, note)
- `block` (a checklist name) and `check` (the item, for example `buck_regulator#BR-1`)
- `failure_mode` (from the schema's list, for example `loop_instability`, `strap_conflict`)
- `parts`, `nets`, `pins`, `pages` as they apply
- `claim`: what is wrong and what fails, one or two sentences
- `evidence`: list of `{kind, ref, detail}` with document, revision and page, or net, or file
- `calculations`: calculator results with formula, inputs, outputs and verdict
- `not_published`: values the documents lack, each with its consequence
- `fix`, and `bench_test` whenever paper cannot settle it
- `verification`: status from the refutation pass, who checked, what they read

In report.md each finding prints as: title; location; claim; evidence; math; fix; bench test;
verification. Severity:

- blocker: the board does not work or is damaged as built.
- major: works on the bench but fails at a corner, over life, or in a likely fault.
- minor: margin or cost issue with a known bound.
- note: information for firmware, test or the next spin.

## Tools

- `tools/boardreview/model`: board model from Altium, KiCad and IPC-D-356; 3-way compare;
  snapshot diff.
- `tools/boardreview/lint`: single-pin nets, open IC pins, floating inputs, duplicate names,
  value outliers.
- `tools/boardreview/blocks`: candidate regulators, filters, interfaces, clocks, resets, straps.
- `tools/boardreview/calc`: `buck`, `loop`, `lc_tank`, `mlcc_bias`, `divider`, `timing`, `tvs`,
  `i2c`, `crystal`, `thermal`. Each returns a `Result`.
- `tools/boardreview/sim`: LTspice batch runs (loop gain by injection, load step, start-up, PDN
  impedance) with sanity checks. A simulation is evidence only after its checks pass.
- Altium: the eda-agent MCP tools. KiCad: `kicad-cli`.

## Evals and lessons (in the board-review repo)

- `docs/lessons/`: one page per real miss, linked to the checklist item that now catches it.
- `evals/`: expected findings per board and `evals/score.py`. A miss on a dev board is a
  checklist bug. Held-out boards are never read while editing checklists.
