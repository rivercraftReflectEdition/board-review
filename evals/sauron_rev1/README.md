# Sauron rev1

Star tracker carrier: STM32N657 MCU, LTC3633A dual buck (3V3, 1V8) after an LT8640 12 V to 4 V
buck, ADIN1200 Ethernet PHY in RMII, S28HS01GT octal NOR, S80KS5123 PSRAM, IMX900 camera module.
Split: **dev**. Its reviews and bring-up notes were read to write the checklists and
[lessons](../../docs/lessons/README.md).

## Local files (ignored by git)

- `local/expected.json`: expected findings for the released package (Rev 1.5, 2026-08-31), the
  design that was built. Manifest name `sauron_rev1`.
- `local/expected_2026-07-29.json`: expected findings for the schematic as it stood at the first
  full review (2026-07-29). Manifest name `sauron_rev1_2026-07-29`.
- `sources.local.json`: paths to the released package, the review staging folders and the
  datasheets on the owner's machine.

Both expected files are written from the lessons; each item names its lesson. Each also carries
`known_good` items, such as the grounded oscillator output in bypass mode and the ESD array's
open grounds, which a review must not flag.

## Lessons not scored here

- Sheet dropped from the compile and fix batch regressions: the intermediate project states were
  not preserved as snapshots.
- I2C pins crossed and the module keepout: found in later intermediate snapshots
  (2026-07-31 and 2026-08-24); UNSURE whether they existed on 2026-07-29.
- Simulation setup errors and the verifier dispute: process lessons with no board finding.

## Scoring

Run the skill on the matching snapshot, save its findings as `<reviews dir>/sauron_rev1.json`
(or `sauron_rev1_2026-07-29.json`), then:

```
python evals/score.py --manifest evals/manifest.json --reviews <reviews dir>
```
