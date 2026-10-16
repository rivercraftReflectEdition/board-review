# 0. Intake

Goal: fix the scope and the facts the review judges against, before reading any circuit.

## Collect

1. **Design source.** Tool (Altium or KiCad), project path, revision, date. Say whether this is
   the released data. To review what was built, prefer the released package (fab netlist,
   BOM with variant, PDF, ODB++ or Gerber) over the live project, and note any difference.
2. **Variant.** Which variant goes to assembly and where its fitted/DNP list lives. If there is
   no variant data, record it now as a netlist_integrity NET-7 finding; every strap and option
   footprint depends on it.
3. **Requirements.** Input voltage range with transients, temperature range, loads per rail,
   environment (vacuum, radiation, vibration, conformal coat), interface documents, power budget,
   lifetime. A requirement nobody gives is recorded as unknown, never filled in. Do not invent
   corner values (12 V plus or minus 10 percent, -40 to 85 C, a full-load budget). A nominal value
   (the voltage in a rail name, a typical input) may be used only as a diagnostic labeled as
   such, and a check whose verdict needs the missing corner stays unknown. The report header
   lists the unknowns.
4. **Stage.** Pre-route, pre-fab, ECO check, or bring-up debug. Layout checks need placement;
   bring-up debug starts from the failing blocks.
5. **Prior reviews.** Findings, dispositions, accepted risks, and the known-good list (things
   that look wrong and are right, with the page that says so). Every fix marked done is
   re-verified in the new data (NET-4); do not trust the fix log.
6. **Design notes and intent.** Anything unusual the designer chose on purpose.
7. **Bench data.** Captures and measurements with board serial and assembly state.
8. **Datasheet sources.** Local PDF folder, vendor models, application notes, errata.

## Local workspace

Create a review folder with `sources.local.json` listing every input path, for example
`outputs/<board>_review_<date>/`. Everything extracted from the board stays there. When the user
asks for it, the review folder can sit inside the board project (for example `<project>/review/`);
the review then writes only there and changes no design file. Board data never goes into the
board-review repo. For eval boards in that repo, `evals/<board>/sources.local.json` points at the
review folder (ignored by git).

## Ask only what the files cannot answer

Ask the user short questions. Offer a proposed default only where the files suggest one:
"Variant DEFAULT is the assembly variant? (yes)". Ask for requirements without a proposed
number; if the user does not know, record unknown. Do not ask what the netlist, BOM or notes
already say, and do not ask again for what the user said is unavailable.

## Output

`intake.md` in the review folder: sources with hashes, variant, requirements with each unknown
named, stage, blocks in scope, prior findings to re-verify, known-good list, open questions.
