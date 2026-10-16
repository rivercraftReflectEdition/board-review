# 6. Report

Goal: a report an engineer can act on in one reading, a findings file a script can score, and a
bench plan for everything paper could not settle.

## Render it

Write findings.json, the bench plan and the known-good list, then run:

```
python -m boardreview report --findings findings.json --facts facts/ --bench bench.json \
  --known-good known_good.json [--previous OLD/findings.json] [--status status.json] \
  [--checks checks.json] [--placement board.kicad_pcb | board.d356 | board-pos.csv] [--pos-units mm] \
  [--power-tree power_tree.json] [--blocks blocks.json] [--supporting FILE ...] [--google-fonts] \
  [--detail full] --out report/
```

Outputs in `--out`:

| File | What |
|---|---|
| report.html | One self-contained page. The verdict, progress, one row per confirmed problem and the open questions are visible; everything else is folded. Checkbox state stays in this browser (localStorage, keyed by board, revision and the findings hash). Export status saves status.json. |
| report_artifact.html | The same page for an artifact. Checkbox state lives in the artifact's shared database; without it the page falls back to localStorage. |
| report.md | The full report for a pull request, in the order below. |
| tickets/ID.md | One short ticket draft per finding: what breaks, where, fix, how to verify, status. |
| findings.json | The findings with status.json merged in. Keep this as the record. |
| status.json | The current checkbox state in the export format. |
| analysis.html | With `--detail full`: every check by block instance, passes folded, in the reading order below. Findings and checks link both ways. |

Inputs:

- **findings.json**: a list of findings, or `{"board", "revision", "variant", "date", "stage",
  "scope", "not_reviewed", "assumptions", "firmware", "accepted_risks", "findings": [...]}`.
  `firmware` entries are `{item, setting, never}`; `accepted_risks` are `{item, reason, by}`. A
  `verdict` string replaces the computed headline.
- **Per finding**, beyond the required fields: `symptom` (what you would see, one short line),
  `change_type` (`bom_only`, `layout`, `part_change`, `firmware`, `none`), `area` (defaults
  from the block). `parts` may hold ranges such as `R14-R22`. Write the title as what breaks.
- **facts/**: the prep folder. Part values, MPNs, DNP state, pins and nets come from
  board_model.json; the power tree from blocks.json.
- **Reviewed stage 3 files**: `--power-tree power_tree.json` (edges with `part`, `kind`, `input`,
  `output`) and `--blocks blocks.json` replace the tree and blocks prep guessed, so corrected
  directions and every LDO and load switch reach the page (workflow/30_blocks.md). Pass them
  whenever stage 3 corrected anything.
- **Supporting files**: verification, source availability, feedback and review files found next
  to findings.json (verify/, intake.md, power_tree.json, checks.json and others) are linked in a
  folded section. `--supporting` adds more, for example `datasheets/datasheets.md` from stage 2.
- **Fonts**: the pages use system fonts and work offline. `--google-fonts` loads the display
  fonts from Google Fonts instead.
- **Placement**: `placement.json`, which prep writes in facts/ from a `.kicad_pcb` or an
  IPC-D-356 file it was given; or a KiCad board file, an IPC-D-356 file or a
  `kicad-cli pcb export pos` file, passed with `--placement` or dropped in facts/. The netlist
  sources named in board_model.json are read too. A board file wins over a position file, which
  wins over IPC-D-356; sources are never mixed because their origins differ. A position CSV does not state its units: pass `--pos-units`. The schematic sheet per
  part comes from a KiCad XML netlist when one is found. The board map is drawn from pad or part
  positions, not the board outline, and says so.
- **bench.json**: a list of steps, or `{"steps": [...]}`. Each step: `id` (b1, b2, ...),
  `phase`, `title`, `pass`, `findings` (ids it settles), and optional `setup`, `procedure`,
  `expected`, `on_fail`. Without a bench file the page lists one step per finding bench test.
- **known_good.json**: a list of `{ref, note, source, decided}`.
- **checks.json**: every checklist item run (workflow/40_checks.md). Read from next to
  findings.json when `--checks` is not given.

Reading order, for every check in analysis.html and every calculation in a finding's Math fold:

1. The headline in words, with the verdict as a word: **Fails** U2 +3V3 loop: phase margin too low.
2. Two or three plain sentences with the real numbers (the check's `summary`, or the
   calculator's).
3. The key numbers against what we want: "Phase margin 30° (want 45° or more) · Crossover
   64 kHz".
4. Sources as sentences: "The datasheet says EN rising threshold is 1.15 to 1.25 V (U1
   datasheet rev A, p.5)." Not-published items say what they became.
5. The plot, with a caption that says what to look at.
6. Folded: the math (formula, every input with its source, every output), assumptions, and the
   simulation checks.

The default view never shows variable names. Write labels, summaries and headlines so that it
does not need them.

Finding and bench ids must be unique across both lists and use letters, digits and
`_ . - ~ : @ +` only; they become checkbox ids and status document ids.

## Problems and open questions

A finding the verifier marked UNVERIFIABLE is an open question, not a problem. The report keeps
the two apart:

- **Problems** (CONFIRMED, or PENDING when the challenge has not run) carry their severity, a
  fix checkbox and the progress bar.
- **Open questions** (UNVERIFIABLE) render in their own section with no severity chip and no
  fix checkbox. Each says what is missing (from `not_published`), what settles it
  (`bench_test`), the bench step that settles it or the document to get (a `vendor_question` or
  `model` action), and the severity it would have if it holds.
- The verdict comes from the problems only. The line under it counts both: "1 confirmed
  problem, 11 open questions." With no blocker or major problem and open questions left, the
  verdict says the board is not signed off.
- Unknown checks are counted by why they could not run, in the folded "Checks that could not
  run": no datasheet (not supplied, or a `vendor_question`), no model (a curve or model is
  missing), needs bench (only a measurement settles it), other. The reason comes from each
  check's `reason` and `not_published`, so write the reason plainly: "U6 datasheet not
  supplied", "bead impedance curve at bias not published".

## Two checkbox states

1. **Fixed in design.** A person ticks the box when the change is in the design files. Nothing
   checks this; it is a claim.
2. **Confirmed in the data.** Only a re-review sets it, after it finds the fix in the new
   netlist or BOM. It can also say the fix was not found. A person cannot set it from the page.

A tick never closes a finding. Fix logs marked done have hidden fixes that never reached the
build.

## After fixes

When the designer applies fixes, run again from workflow/10_extract.md: diff against this
snapshot (NET-4), re-verify each fix in the data, re-run the checks the change touches, and
update each finding's status.

1. Collect the ticks. Locally: ask for the exported status.json. Artifact: read every document
   in the artifact database's `status` collection and save them as
   `{"items": {ID: {done, at, by, verified, verifyNote}}}`.
2. Run prep on the new design into a new facts folder.
3. Run `python -m boardreview verify-fixes --findings findings.json --old-facts facts/
   --new-facts facts_v2/ --status status.json --status-out status_v2.json`. For each finding
   marked fixed it checks what a script can check: a part removed or DNP, a value changed, a
   pin moved to a net. It sets `verified_in_data` true or false with a one-line note. When it
   cannot tell, it leaves `verified_in_data` unset with a note that starts "needs a reviewer".
   It never confirms on a guess.
4. For each "needs a reviewer", read the new facts yourself. Set `verified_in_data` and
   `verify_note` in findings.json only when you can cite the net, pin or BOM row that shows the
   fix.
5. Write the result back. Locally: render again with `--status status_v2.json` (or the edited
   findings.json). Artifact: write `verified`, `verifyNote` and `verifiedAt` into each finding's
   document in the `status` collection, merging so `done`, `at` and `by` stay as the person set
   them. Never write `done`.
6. Render the new review with `--previous` pointing at the old findings.json. The "what changed"
   fold matches findings by block, failure mode and shared parts or nets. An old finding that is
   gone counts as fixed only when its fix shows in the new facts; otherwise it is listed as not
   found again, not confirmed.

## Publishing the artifact

Publish report_artifact.html with capabilities `{db: {}, user: {scopes: ["profile"]},
downloads: true}`. With `--detail full`, publish analysis.html beside it as a supporting file so
the links between the two pages work. Status documents live in collection `status`, one per
finding or bench id: `{done, at, by, verified, verifyNote}`. A tick updates `done`, `at` and
`by` on an existing document, so it never overwrites what a re-review wrote.

## report.md

1. **Header.** Board, revision, variant, source files with hashes, date, stage, scope, what was
   not reviewed, assumptions from intake.
2. **Summary.** The verdict, the count of confirmed problems and open questions, problems by
   severity. One line per blocker and major problem: part or net, what fails, fix. The open
   question ids, and the unknown checks counted by reason.
3. **Findings**, the problems grouped by block or by sheet. Each one: title; location (parts,
   nets, pins, page); claim; evidence with document, revision and page; math
   (`Result.to_markdown()`); what is not published; fix; bench test; verification status and
   who checked. Then **Open questions**: each with what is missing, what settles it, the bench
   step or document, the severity if it holds, then the same detail.
4. **Required footprints** from not-published items (Cff, compensation, dampers, series
   resistors, injection points, probe points).
5. **Firmware handoff.** Register settings, fuses and option bits with bit positions and the
   ones never to set, clock limits, strap readback values, sequencing contracts, defaults to
   clear.
6. **Accepted risks and deviations** with the reason and who accepted them.
7. **Bench test plan** (below).
8. **Known-good list.** Items that look wrong and are right, each with the page that says so,
   for the next review.
9. **Appendix.** Refuted findings with reasons; checklist coverage per block (run, not
   applicable, unknown); checks that could not run, counted by reason with examples.

## findings.json

A list of findings that validates against `schemas/finding.schema.json`. Check it with
`python -m boardreview validate findings.json` and fix every error before the report goes out.
This is the file the eval scorer in the board-review repo reads.

## Bench test plan

One entry per item paper cannot settle, and one per high-risk pass worth confirming:
- what it settles (finding id or check id);
- setup: probe point, equipment, load, temperature, board serial;
- procedure;
- expected value with tolerance, from the calculator;
- pass and fail rule;
- what to do on fail, using the footprint the report required.

Order: unpowered checks (rail resistance to ground, cap values); current-limited first power;
strap and ID readback; rails and sequencing; loop checks (start-up capture, load step, Bode at
small injection); interfaces; temperature corners.

## Writing

Plain engineer prose. Short sentences. Tables for numbers. State the number, the limit and the
consequence. Spell out terms. Mark anything unverified UNSURE and say what settles it. No
filler. In the report rows the title says what breaks; the symptom says what you would see.
