# 5. Verify

Goal: try to break every finding, and the riskiest passes, before anyone acts on them.

## Who

A second agent with fresh context, not the one that wrote the finding. Give it the finding JSON,
the digests, the staging views and the datasheet paths. Do not give it the first agent's notes;
it must reach the facts on its own.

How to start it:
- Claude Code: a subagent (the Agent tool) whose prompt holds this page, the finding JSON and the
  source paths, and nothing from the main conversation. One subagent per finding or per small
  group of findings on the same block.
- Codex CLI: a separate run from the review folder, for example
  `codex exec -s read-only -C <review folder> -o verify/F-003.md "<prompt>"`, where the prompt
  holds this page's steps, the finding JSON and the source paths. A fresh interactive session
  given only those files works the same way.
- Any other agent: a new session or pass that is given only the finding JSON and the cited
  sources, never the notes or chat that produced the finding.

Record who checked in `verification.by` (for example `claude-code subagent`, `codex exec`) and
the files it read in `verification.sources_checked`. If no second context can be started, the
finding stays PENDING and the report says the refutation pass has not run.

## Per finding

1. **Reproduce the facts.** Net membership, both ends of every resistor, BOM value and fitted
   state in the released variant, pin and ball functions, datasheet values on the cited page at
   the cited conditions.
2. **Re-derive the math** with its own calculator run.
3. **Try each refutation:**
   - Part is DNP in the released variant, or the variant data is missing.
   - An internal pull, a series resistor, or another load changes the level.
   - The datasheet row applies at other conditions (temperature, reverse voltage, current,
     supply) than the claim uses.
   - Typical values used where guaranteed values decide, or the reverse.
   - A datasheet configuration makes the circuit intentional (application figure, footnote).
   - Design notes or the known-good list say it is intentional.
   - Already fixed in the current data.
   - Wrong pin or ball mapping (multi-part symbols, package variants).
   - The mechanism needs a condition that cannot occur on this board.
4. **Verdict:**
   - CONFIRMED: facts and math reproduce and no refutation holds.
   - WRONG: a refutation holds. Say which, with the page.
   - UNVERIFIABLE: depends on a value the documents do not give. The finding must carry a bench
     test and, where it applies, a footprint.
   Record corrections to numbers or severity even when the verdict is CONFIRMED.

## Passes are claims too

Give the verifier a sample of high-risk passes, written as claims: "the 3.3 V buck loop passes
because ...". A wrong pass costs more than a wrong finding, because nobody looks again. See
[loop out of example envelope](../lessons/loop-out-of-example-envelope.md).

## Disputes

When two verifiers disagree, the main agent reads the cited pages itself and decides. Record the
decision with the page: in the finding, or in the known-good list so the next review does not
reopen it. If the circuit is intentional but looks wrong, ask for a note on the schematic. See
[verifier dispute on ESD grounds](../lessons/verifier-dispute-esd-grounds.md).

## Severity check

A blocker must show how the board fails as built. A major must name the corner or fault.

## Output

The `verification` block on each finding. WRONG findings move to an appendix with the reason, so
they are not raised again.
