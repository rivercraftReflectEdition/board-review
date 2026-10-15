# Verifiers disagreeing on an ESD array's floating grounds

**Rule:** when verifiers disagree, the main agent reads the cited pages and decides, and the
decision goes on the known-good list and the schematic so the next review does not reopen it
([50_verify disputes](../workflow/50_verify.md),
[protection_tvs PROT-4](../checklists/protection_tvs.md)).

Board: Sauron rev1. Part: Semtech RClamp3374N on the Ethernet line side.
Status: flagged as a blocker in July and August; adjudicated intentional on 2026-08-28.

## What happened

- Every ground pin of the ESD array was unconnected. Earlier reviews called the clamp
  non-functional and a blocker.
- In the August campaign two verifiers split: one confirmed the blocker, the other refuted it
  from the datasheet's line-to-line configuration.
- The adjudication read the pages: a differential-only clamp, with the magnetics handling common
  mode. Intentional. A grounding fix had already been drafted for the assembler before that.

## Why it cost time

- The intent was not written on the schematic. Verifiers read different pages. The decision was
  not recorded where the next review would see it, so the finding flipped more than once.

## The checks that catch it now

- [50_verify](../workflow/50_verify.md): disputes go to the main agent with the pages.
- [PROT-4](../checklists/protection_tvs.md): configuration matches the datasheet and the
  intent is on the schematic.
- [ETH-6](../checklists/ethernet_phy.md): MDI protection.
- [60_report known-good list](../workflow/60_report.md).
