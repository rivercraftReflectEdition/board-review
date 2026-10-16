# 4. Checks

Goal: run every applicable checklist item on every block instance, with numbers, and turn
failures into candidate findings.

## Order

1. Power tree first: cascaded_rails, then each regulator (buck_regulator, ldo), then filters
   and decoupling. Rail values and tolerances computed here feed every later check.
2. enable_uvlo_sequencing and resets_supervisors_watchdogs over the enable and reset chains.
3. io_levels_and_domains over the domain map; straps_and_boot_pins over the strap map.
4. Interfaces: ethernet_phy, camera_csi, xspi_memory, clocks_crystals, clock_distribution,
   data_converters and rf_front_end. Fetch applicable files per [models](models.md).
5. Run spur_plan once across the board's regulators, clocks and sensitive paths.
6. protection_tvs, thermal, then layout when placement exists.

Agents may split by block (subagents in any agent that has them, separate `codex exec` runs in
Codex, or one block after another). Each agent gets the checklist, the block record, the digests
and the staging views, not the whole board.

## Run each item

For every item record one of: pass, marginal, fail, not applicable (with the reason), or unknown
(with the not-published entry, the source_unavailable record, or the missing requirement). For
every numeric item keep the calculator `Result`.

- Inputs come from digests and the BOM, never from memory of a part.
- Corners: resistor and reference tolerance, both temperature extremes, DC bias, aging, supply
  limits. Where two corners push in opposite directions (leakage hot, VF cold) run both.
- A corner that intake.md records as unknown (input range, temperature, load) is not invented.
  Run the check at a nominal value only as a diagnostic, marked nominal (below), and record the
  item unknown when its verdict depends on the missing corner.
- Mark what the inputs are: nominal, worst_case, example (a datasheet example's values) or ideal
  (for example Dmax = 1). Calculators that take a `context` argument (`calc.buck.current_slew`,
  `calc.buck.slew_clamp_vpp`, `calc.buck.example_envelope`, `calc.loop.margins`) mark their own
  Result; mark any other with `Result.in_context`. A pass from anything but worst_case comes back
  unknown, with the summary saying so, and the report shows it as unknown.
- Guaranteed values decide pass and fail. Typical values may explain, never pass.
- Print `Result.to_markdown()` in the working notes so the math is visible.

## checks.json

Start the file from the blocks of stage 3:

```
python -m boardreview checks --facts <review folder>/facts --blocks <review folder>/blocks.json --out <review folder>/checks.json
```

It writes one unknown entry per checklist item per block instance, from each block's `checklist`
field (prep's blocks by their kind), and the board-wide checklists once. Entries already in the
file are kept, so run it again after adding blocks. Replace each entry as you run the item; one
left with the skeleton's "Not run yet" reason was not run.
The spur_plan instance is always board-level. A switching regulator or clock together with an
RF, converter or clock-distribution block makes it applicable. Other unused checklists retain
board entries for the reviewer to assess; set not_applicable only with the reason.

Write every item run, pass or fail, to `checks.json` in the review folder: a list of objects
that validate against `schemas/check_result.schema.json`, or `{"board": ..., "checks": [...]}`.
Check it with `python -m boardreview validate checks.json --schema checks`.
One entry per item per block instance:

- `id` unique in the file (for example `U9-ch1.BR-1`), `block`, `instance` (for example
  "U9 channel 1, 3V3 rail"), `item` (`BR-1`), `title`;
- `headline`: what it is and the outcome, in words: "U9 3V3 loop: phase margin too low";
- `summary`: two or three plain sentences with the real numbers. Say what was checked, the
  number against what we want, and what it means on the bench: "The loop crosses over at
  64 kHz with 30° of phase margin. We want at least 45°, so 3V3 will ring after each load
  step." Leave it out to use the calculator's own summary;
- `verdict`: pass, marginal, fail, unknown or not_applicable, with `reason` (required for
  unknown and not_applicable). A check's verdict is never better than its worst calculator
  verdict unless its `summary` says why; the report flags it otherwise. Write an unknown's
  reason plainly ("U6 datasheet not supplied", "bead impedance curve at bias not published"):
  the report counts unknown checks by it;
- `results`: each calculator `Result` as `Result.to_dict(name)`, where name is the calculator
  path such as `calc.loop.margins`; plots are included, `context` says what the inputs were, and
  a value that is not finite is written as null with a note;
- `digest_values`: the datasheet values the check used, each with document and page;
- `not_published`, `assumptions`, `sources`, `bench_test`;
- `simulation`: the setup verdict, the measured verdict, each sanity check and the sim Results;
- `finding`: the id of the finding this check produced, when it produced one.

Passes are recorded too. The verifier samples them, the coverage table counts them, and
`python -m boardreview report --detail full` prints them in analysis.html. A pass that is not in
checks.json was not run.

## Not-published rule

1. Say what is missing and where you looked.
2. If a published or physical bound exists, run the check across it: at the two ends only when
   the result is monotonic in the missing value (say why), otherwise as a sweep that includes
   every value inside the bound where the result turns (for example the L that puts a resonance
   on fsw).
3. If the verdict holds across the bound, record it with the bound as an assumption. A range
   that is an engineering default rather than a published or physical bound (for example 0.5x
   to 2x a typical value) cannot make a pass: the result stays unknown, with the range named.
4. If it does not, or there is no bound: the result is unknown. Require a footprint that lets
   the bench fix it, and a bench test that settles it. File a finding at the severity the failure
   would have.
5. Never record pass on an unknown, and never drop the check.

## Failure-mode index

Checklists are organized by block; this table finds every item for a failure mode.

| Failure mode | Items | Calculators |
|---|---|---|
| loop_instability | BR-1, BR-2, BR-4, BR-10, BR-11, LDO-2 | calc.buck, calc.loop, sim.setups.run_loop_gain |
| reverse_current | CR-1, BR-5, LDO-5 | calc.buck, sim.setups.run_startup |
| back_power | IO-3, CSI-4, RST-3 | calc.divider |
| lc_resonance | FLT-1, FLT-2, FLT-5, FLT-6, PDN-4, PROT-5 | calc.lc_tank, sim.setups.run_impedance |
| insufficient_capacitance | PDN-1, PDN-2, BR-8 | calc.mlcc_bias |
| saturation | BR-7, FLT-3 | calc.buck |
| dropout | LDO-1, CR-3 | calc.buck, calc.divider |
| threshold_margin | EN-2, EN-3, RST-1, RST-2, STR-1, IO-1 | calc.divider |
| level_mismatch | IO-1, CLK-1, EN-8 | calc.divider |
| leakage | EN-6, RST-2, BR-9 | calc.divider |
| abs_max | IO-2, EN-5, CR-4, CLK-1, PROT-2 | calc.divider, calc.protection |
| strap_conflict | STR-1, STR-2, STR-3, STR-4, ETH-1 | calc.divider |
| boot_mode | STR-5 | calc.divider |
| reset_hazard | RST-5, RST-6, RST-7, MEM-5 | calc.timing |
| sequencing | EN-4, EN-7, CR-5, CSI-3 | calc.timing, sim.setups.run_startup |
| wrong_value | EN-1, NET-6 | calc.divider |
| net_short | NET-1, NET-2, MEM-1 | model.compare |
| open_net | NET-5, ETH-3 | lint.run_all |
| missing_sheet | NET-3 | model.compare |
| pin_swap | IO-5, MEM-2, ETH-4, CSI-1, NET-8 | none |
| missing_pullup | IO-7, RST-4, EN-8 | calc.i2c, calc.divider |
| timing_margin | MEM-6, CSI-2, CSI-5, CLK-3 | calc.timing |
| clock_fault | CLK-2, CLK-3, CLK-5, CLK-6, ETH-2 | calc.crystal |
| protection_gap | PROT-1 to PROT-7, ETH-6 | calc.protection |
| thermal_overstress | TH-1 to TH-6, LDO-3 | calc.thermal |
| footprint_mismatch | NET-8, PROT-3, RST-9 | none |
| mechanical_interference | LAY-6, CSI-6 | none |
| signal_integrity | LAY-4, LAY-5, CSI-5, PROT-7 | calc.timing |
| missing_rework_option | BR-3, MEM-7, LAY-8 | calc.loop.cff_lead |
| rf_mismatch | RF-1, RF-2, RF-10, RF-12, RF-14 | calc.rf.element_impedance, calc.rf.match_sweep, calc.rf.mismatch, calc.rf.dc_block, calc.rf.pad, sim.touchstone.return_loss |
| rf_instability | RF-6 | calc.rf.stability |
| spur_in_band | RF-4, ADC-5, ADC-10, CKD-13, SPUR-1 to SPUR-6 | calc.spur, calc.jitter.ripple_sideband, calc.jitter.spur_transfer, calc.jitter.vc_noise |
| jitter_budget | CKD-5, CKD-6, CKD-8, CKD-12, ADC-1, ADC-2 | calc.jitter, calc.clock_term.ac_coupling |
| termination_error | CKD-1 to CKD-5, CKD-8 | calc.clock_term |
| sync_fault | ADC-8, ADC-9, CKD-10, CKD-11 | calc.converter.jesd_lane_rate, calc.converter.sysref, calc.jitter.ssc_emi |
| loop_instability | CKD-7 | calc.pll.loop_filter_check, calc.pll.loop_filter_design |
| lc_resonance | RF-7 | calc.rf.network_impedance |
| insufficient_capacitance | ADC-3 | calc.mlcc_bias.mlcc_effective |
| level_mismatch | RF-13, ADC-6 | calc.rf.cascade, calc.divider.divider_output |
| sequencing | RF-3, RF-5 | calc.rf.element_impedance, calc.timing.budget |
| leakage | RF-8 | calc.divider |
| protection_gap | RF-9 | calc.rf.shunt_c, calc.rf.peak_voltage |
| mechanical_interference | RF-11 | calc.rf.cavity_modes |
| timing_margin | ADC-4, ADC-7 | calc.converter.sar_rc, calc.timing.rc_edge |
| clock_fault | CKD-9 | calc.crystal |
| pin_swap | ADC-11 | none |

## When to simulate

Simulate when a closed-form calculator cannot answer:
- a loop whose plant or compensation is not published (nominal estimate and sensitivity only);
- interactions between regulators: start-up, returned current, input filters;
- PDN and filter impedance with real parasitics.

Do not simulate what a calculator answers (dividers, tanks, levels, timing sums).

A simulation is a nominal estimate of a model. It can confirm a failure. It cannot pass a loop
whose real compensation is unknown; that stays unknown with a bench test.

## Simulation sanity checks

`sim` automates the parts named below; the agent confirms each before quoting a result:
1. Netlist matches the board: every model pin connected as on the board, no floating pins
   (`sim.sanity.check_netlist`).
2. Operating point matches hand calculation: VOUT and duty against
   `calc.divider.regulator_output` and `calc.buck.duty_cycle`; fsw within 5 percent of the value
   from the timing resistor (`sim.sanity.check_run`).
3. Loop gain by injection: amplitude a few mV and under the inductor slew limit
   (`sim.sanity.injection_slew_check`); halving it changes gain by under 0.5 dB and phase by
   under 3 deg (`sim.setups.linearity_check`); injection frequencies away from fsw/n
   (`sim.setups.injection_frequencies`).
4. Model limits written in the finding: ideal comparators, missing parasitics, typical silicon.
5. Corners run, not only nominal.

Every `sim` result carries two verdicts: the setup (netlist, run, injection, settling) and the
measured result (margins, ring, settling, overshoot, impedance). Quote the measured verdict only
when the setup verdict is pass; a marginal or unknown setup makes the result unknown. A ring-down
PM estimate is informational; quote PM from the loop gain.

See [simulation setup errors](../lessons/simulation-setup-errors.md).

## Candidate findings

Write each failure as a finding JSON (schemas/finding.schema.json) with `verification.status`
PENDING and the `check` id. Lint results arrive this way in `lint_findings.json` from stage 1,
mapped to a checklist item and one severity step below blocker; confirm each against the
datasheet, set its severity, and keep the ones that hold. Also list the passes of high-risk
items (BR-1, BR-2, CR-1, EN-2, STR-1, RST-1, RST-2) with their numbers; the verifier samples
them.

Severity: blocker if the board fails as built; major if it fails at a corner, over life or in a
likely fault; minor for bounded margin or cost; note for firmware, test or next-spin items.

A candidate that rests on missing data ends UNVERIFIABLE in stage 5, and the report shows it as
an open question, not a problem, with the severity it would have if it holds
(workflow/60_report.md). Give it `not_published` and a `bench_test` so the report can say what
is missing and what settles it.
