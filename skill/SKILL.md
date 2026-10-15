---
name: board-review
description: Schematic and PCB design review for Altium or KiCad boards. Use when asked to review a schematic, PCB, board, layout, power tree, ECO or design before fab or bring-up, or to check fixes from an earlier review. Builds a board model and datasheet digests first, then runs block checklists with calculators (loop margin against the datasheet's example envelope, LC tanks, reverse current between rails, straps, reset and enable margins, levels across domains, abs max), verifies every finding with a second-agent refutation pass, and reports each finding with its math plus a bench test plan.
---

# Board review

Pin-and-net checks find opens, shorts and wrong pins. Boards fail on the bench for other reasons:
a regulator outside the conditions its compensation was designed for, a bead and capacitor that
ring at the switching frequency, a rail that cannot absorb returned current, a strap at mid-rail,
a reset that does not assert at cold. This skill finds those, with numbers.

## Setup (once per machine)

The skill runs the `boardreview` Python package from the board-review repo; this folder is the
repo's `skill/` folder, linked into the agent's skills folder.

1. `python -m pip install -e <board-review repo>` (Python 3.11+, numpy, scipy). It needs network
   access and a writable Python; in a sandbox, ask the user to run it.
2. Check from any folder: `python -m boardreview --help` lists `prep` and `validate`. If it fails,
   resolve this folder's link to find the repo (its parent) and run step 1.
3. KiCad boards need `kicad-cli` (verified with KiCad 10.0.6; workflow/10_extract.md says where
   it is installed and which exports to run).

Paths in this skill (`workflow/`, `checklists/`, `schemas/`, `lessons/`) are relative to the folder
that holds this SKILL.md. Python names are relative to the `boardreview` package:
`calc.buck.current_slew` is `boardreview.calc.buck.current_slew`.

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
| 1 Extract | workflow/10_extract.md | facts/ from `python -m boardreview prep`: board model, compare, lint, block candidates, facts.md |
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
3. **Show the math.** Every number comes from a calculator in `boardreview.calc` and the
   report prints its formula, inputs and outputs (`Result.to_markdown()`). Where a checklist
   says no calculator exists yet, write the formula, inputs and result the same way. Use
   worst-case corners: tolerance, temperature, bias, aging. Typical values are labeled typical.
4. **"Not published" is an answer.** When the documents do not give a value the check needs
   (internal compensation, bead inductance, sink current), say so in the digest. The finding
   becomes a required footprint, a bench test, or a vendor question. Never guess a value and
   never drop the check.
5. **Every finding survives refutation.** A second agent with fresh context tries to break each
   finding against the sources (workflow/50_verify.md says how in Claude Code, Codex and other
   agents). WRONG findings are dropped. UNVERIFIABLE
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

Each finding is one JSON object that validates against `schemas/finding.schema.json`; check the
file with `python -m boardreview validate findings.json` before reporting. Required:

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

- `python -m boardreview prep`: board model, staging views, lint, block candidates and the
  netlist compare in one folder, indexed by `facts.md` (workflow/10_extract.md).
- `python -m boardreview validate FILE`: schema check for findings.json (`--schema digest` or
  `--schema board_model` for the others).
- `python -m boardreview report`: report.html, the artifact page, report.md, ticket drafts and,
  with `--detail full`, analysis.html, from findings.json and the facts folder
  (workflow/60_report.md).
- `python -m boardreview verify-fixes`: marks findings set fixed as verified, or not, in the facts
  of the fixed design (workflow/60_report.md).
- `model`: board model from IPC-D-356, KiCad XML, `.kicad_pcb`, Protel .NET, eda-agent JSON and
  a BOM; `model.compare` for the 3-way compare and the snapshot diff.
- `lint`: single-pin nets, unconnected IC pins, ground and supply pins on the wrong net,
  floating protection grounds, near-duplicate rail names, parts without MPN, DNP-only links,
  BOM against netlist. `lint.to_findings` writes results as PENDING candidate findings.
- `blocks`: candidate switching regulators, bead and LC filters, crystals, oscillators, resets,
  I2C buses, straps.
- `calc`: `buck`, `loop`, `lc_tank`, `mlcc_bias`, `divider`, `timing`, `protection`, `i2c`,
  `crystal`, `thermal`. Each function returns a `Result`.
- `sim`: LTspice batch runs from `sim.setups` (`run_loop_gain`, `run_load_step`, `run_startup`,
  `run_impedance`) with the checks in `sim.sanity`. A simulation is evidence only after its
  checks pass.
- Altium: the eda-agent MCP tools (any agent that speaks MCP). KiCad: `kicad-cli`.

## Running in different agents

The skill needs a shell, file reads and writes, and a second context for stage 5.
- A second agent with fresh context: a subagent in Claude Code; a separate `codex exec` run or a
  fresh session in Codex; elsewhere, a new pass that sees only the finding JSON and the cited
  sources (workflow/50_verify.md).
- Work split across agents (one per MPN, one per block) can run in the same ways, or one piece
  after another in one session. The output files are the same.
- Datasheet pages are read as images (workflow/20_datasheets.md). Without network access, ask
  the user for the PDFs; never fill a digest from memory.

## Lessons and evals

- `lessons/`: one page per real miss, linked to the checklist item that now catches it.
- In the board-review repo only: `evals/` holds expected findings per board and the scorer. A
  miss on a dev board is a checklist bug. Held-out boards are never read while editing checklists.
