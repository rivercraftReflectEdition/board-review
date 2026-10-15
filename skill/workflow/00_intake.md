# 0. Intake

Goal: fix the scope and the facts the review judges against, before reading any circuit.

## Collect

1. **Design source.** Tool (Altium or KiCad), project path, revision, date. Say whether this is
   the released data. To review what was built, prefer the released package (fab netlist,
   BOM with variant, PDF, ODB++ or Gerber) over the live project, and note any difference.
2. **Variant.** Which variant goes to assembly and where its fitted/DNP list lives. If there is
   no variant data, record it now as a netlist_integrity NET-7 finding; every strap and option
   footprint depends on it.
3. **Requirements.** Input voltage range with transients, temperature range, environment
   (vacuum, radiation, vibration, conformal coat), interface documents, power budget, lifetime.
   Missing requirements become assumptions written in the report header.
4. **Stage.** Pre-route, pre-fab, ECO check, or bring-up debug. Layout checks need placement;
   bring-up debug starts from the failing blocks.
5. **Prior reviews.** Findings, dispositions, accepted risks, and the known-good list (things
   that look wrong and are right, with the page that says so). Every fix marked done is
   re-verified in the new data (NET-4); do not trust the fix log.
6. **Design notes and intent.** Anything unusual the designer chose on purpose.
7. **Bench data.** Captures and measurements with board serial and assembly state.
8. **Datasheet sources.** Local PDF folder, vendor models, application notes, errata.

## Local workspace

Create a review folder outside this repo, for example `outputs/<board>_review_<date>/`, with
`sources.local.json` listing every input path. Everything extracted from the board stays there.
For eval boards, `evals/<board>/sources.local.json` points at it (ignored by git).

## Ask only what the files cannot answer

Ask the user short questions with a proposed default: "Variant DEFAULT is the assembly variant?
(yes)". Do not ask what the netlist, BOM or notes already say.

## Output

`intake.md` in the review folder: sources with hashes, variant, requirements and assumptions,
stage, blocks in scope, prior findings to re-verify, known-good list, open questions.
