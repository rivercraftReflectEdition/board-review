# Evals

The skill is measured by bugs we already know. A dev board miss is a checklist bug: fix the
checklist item, then re-run. Board data never enters the repo; expected lists for real boards
live in `evals/<board>/local/` (ignored by git).

## Files

- `manifest.json`: every board, its split (`dev` or `held-out`), kind (`real`, `synthetic`,
  `seeded`, `clean`), expected file and optional default review file.
- `<board>/expected.json` or `<board>/local/expected.json`: expected findings, validated against
  `expected.schema.json`, plus `known_good` items (things that look wrong and are right).
- `<board>/README.md`: what the board is and where its local files live.
- `bug_classes.json`: classes planted by the seeded-bug eval, with the checklist items that
  should catch each.
- `score.py`: the scorer.

## Splits

- **dev**: boards whose reviews, notes or bench history were read while writing checklists and
  lessons. Sauron rev1 is dev.
- **held-out**: boards chosen, and their expected lists written and sealed, before checklist
  work starts. Nobody editing checklists or lessons reads their sources, notes or expected lists.
  The scorer prints only counts for held-out boards unless `--reveal-heldout` is given. Reveal
  only to measure a frozen checklist version; after that the board moves to dev.

## Running

```
python evals/score.py --manifest evals/manifest.json --reviews <dir of <board>.json>
python evals/score.py --expected evals/example/expected.json --review evals/example/review.json
```

A review file is a list of findings, or `{"findings": [...]}`, each validating against
`skill/schemas/finding.schema.json`. Schema errors are reported with the score. `--json` prints
the full result; `--include-refuted` also scores findings the refutation pass marked WRONG.

The report gives recall and precision per board, totals per split and overall (sums over
boards), recall by severity, detection per seeded bug class, and lists of misses, false
positives, known-good hits and duplicates.

## Matching rule

A review finding R matches an expected finding E when all four hold:

1. **Block.** R's block equals E's block or one of E's `alt_blocks`, after aliases (`buck`,
   `phy`, `tvs` and so on map to checklist names). R's block also passes when it shares a row
   of the equivalence table below with E's block, in the row for E's `failure_mode`.
2. **Location.** R's parts (plus the parts in its pins) or nets share at least one entry with
   E's. Designator ranges such as `R14-R22` expand. Net names compare without case, with `_` and
   spaces read as `-`, and with any hierarchy path dropped. An E with no parts and no nets
   matches any location.
3. **Mechanism.** R's text hits at least half of E's `keywords`, rounded up, minimum one. The
   text is R's title, claim, mechanism, fix, instance and check, plus the reason of every
   calculation whose verdict is `fail` or `marginal`. Each keyword is a group of `|`
   alternatives. An alternative hits when it starts a word in the text, or, if it has six or
   more characters, when it appears with spaces removed. Every expected item needs keywords;
   the scorer reports an item without them as an expected-file error. A matching
   `failure_mode` tag alone is not a match: "This circuit needs review" tagged
   `loop_instability` names no mechanism.
4. **Polarity.** R does not say the circuit is fine. It fails this when every calculation it
   carries (ignoring `info`) returns `pass`, or when its title or claim says the part is stable,
   fine, OK, correct, adequate, sufficient, safe or within limits, says it passes, or says there
   is no issue, unless the same text qualifies that with but, however, except, although, though,
   yet, until, unless or only. "U2 is stable" never matches a loop finding.

Equivalent blocks. Some failure modes are owned by more than one checklist, so a correct finding
can be filed under any of them. Each row lists the checklist items that check that failure
mode (`EQUIVALENT_BLOCKS` in `score.py`):

| Failure mode | Blocks | Checklist items |
|---|---|---|
| `missing_pullup` | io_levels_and_domains, resets_supervisors_watchdogs, enable_uvlo_sequencing, camera_csi, ethernet_phy | IO-7, RST-4, EN-8, CSI-4, ETH-3 |
| `strap_conflict` | straps_and_boot_pins, ethernet_phy | STR-1, STR-2, ETH-1 |
| `reverse_current` | cascaded_rails, buck_regulator | CR-1, BR-5 |
| `back_power` | io_levels_and_domains, camera_csi | IO-3, CSI-4 |
| `net_short` | netlist_integrity, xspi_memory | NET-2, MEM-1 |

A missing I2C pull-up on a camera module's control bus filed under camera_csi therefore matches
an expected item filed under io_levels_and_domains. Anything outside the table still needs
`alt_blocks` in the expected file.

Pairing is one to one. Candidate pairs are ranked by location overlap plus keyword hits plus 2
for a failure-mode tag match, best first. The tag still ranks pairs; it no longer decides them.

Counting:
- True positive: an expected finding paired with a review finding. Recall = TP / expected.
- Duplicate: an unpaired review finding that matches an already-paired expected finding. Listed,
  not counted in precision.
- Known-good hit: an unpaired review finding that matches a `known_good` item. Counted as a
  false positive and listed.
- False positive: any other unpaired review finding. Precision = TP / (TP + FP).
- Findings marked WRONG by the refutation pass are excluded unless `--include-refuted`.
- A clean board (no expected findings) has no recall; every finding on it is a false positive.

On a real board precision is a lower bound: the expected list holds the bugs we know, not every
bug. Triage each unmatched finding: real (add it to the expected list), wrong (checklist noise),
or duplicate.

## Seeded-bug eval

Goal: detection rate per bug class across vendors, independent of one board's history, and a
false-positive baseline from a clean design.

1. **Clean design.** Start from a design reviewed until no finding is open, with its known-good
   list. Review it with the current checklist version. Every finding on it counts as a false
   positive (`kind: clean`, `expected: null` in the manifest).
2. **Bug classes** (`bug_classes.json`): wrong divider value; bead plus capacitor resonating near
   a switching frequency; strap pull-up and pull-down both fitted; regulator outside its
   datasheet example envelope; missing pull-up; TVS standoff below the rail's worst case; upstream
   rail that cannot sink reverse current.
3. **Plant.** Each seeded copy gets one mutation per class, or a few classes that do not
   interact. A mutation edits only what a real mistake edits: a BOM value, a variant's fitted
   state, a strap or mode connection, a part number suffix. Record each mutation in the seeded
   board's `expected.json` with its `bug_class`, the parts and nets it touched, and the failure
   mode a reviewer should report.
4. **Vendors.** Seed each class on parts from at least two vendors across the set: regulators
   from different vendors for the envelope and divider classes, PHYs or switches from different
   vendors for the strap class, different bead and TVS makers. A checklist that only works on
   one vendor's parts fails here.
5. **Run** the skill on the clean design and on every seeded copy with the same checklist
   version.
6. **Score.** Detection per bug class = detected / seeded, summed over seeded boards, per split.
   Precision counts the clean design's findings and any finding on a seeded copy that matches no
   seed. A class below full detection points at its checklist items in `bug_classes.json`.
7. **Hold out** some seeded copies as `held-out` and use them only to measure a frozen checklist.

Planting will run on board model files (BOM, variant, netlist) through `tools/boardreview/model`.
Until that exists, mutations are applied by hand to a copy of the design and recorded in
`expected.json`.

`seeded_example/` is a small synthetic example: seven seeds on a mixed-vendor design, a review
that detects five of them plus one false positive, and a clean-design review with two false
positives.

## Adding a board

1. Choose its split before reading anything about its review history.
2. Commit `evals/<board>/README.md`: what the board is and where its local files live.
3. Write `evals/<board>/local/expected.json` and `evals/<board>/sources.local.json` (both ignored).
4. Add the board to `manifest.json`.
