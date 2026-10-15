# 6. Report

Goal: a report an engineer can act on in one reading, a findings file a script can score, and a
bench plan for everything paper could not settle.

## report.md

1. **Header.** Board, revision, variant, source files with hashes, date, stage, scope, what was
   not reviewed, assumptions from intake.
2. **Summary.** Counts by severity. One line per blocker and major: part or net, what fails,
   fix.
3. **Findings**, grouped by block or by sheet. Each one: title; location (parts, nets, pins,
   page); claim; evidence with document, revision and page; math (`Result.to_markdown()`); what
   is not published; fix; bench test; verification status and who checked.
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
   applicable, unknown).

## findings.json

A list of findings that validates against `schemas/finding.schema.json`. This is the file
`evals/score.py` scores.

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
filler.

## After fixes

When the designer applies fixes, run again from workflow/10_extract.md: diff against this
snapshot (NET-4), re-verify each fix in the data, re-run the checks the change touches, and
update each finding's status.
