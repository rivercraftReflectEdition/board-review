# 2. Datasheets

Goal: one digest per MPN with every fact the checklists need, each with its page, and an explicit
list of what the documents do not publish.

## One digest per MPN

- File: `<review folder>/digests/<MPN>.json`, validated against
  `schemas/datasheet_digest.schema.json`. Curves go next to it as CSV.
- One digest per orderable variant when the suffix changes behavior (light-load mode, supply
  voltage code, threshold option, temperature grade). Record the variants in
  `orderable_variants` and check which one the BOM orders.
- Record document number, revision and date. Check the vendor's site for a newer revision and
  for an errata sheet that matches the silicon revision on the board.

## Read from page images

Render the pages to images and read the image. Text extraction may help find a value, but tables
smear columns, footnotes detach and figure labels move. A value goes in the digest only after it
is read on the page image. List the pages read in `read_from.pages_read`.

## Required content

- **Pin table** with type, reference supply (domain), function, internal pull with its range,
  what to do when unused, and page.
- **Straps**: every pin sampled at reset, its levels, the network per level, when it is sampled,
  and whether software can override it.
- **Absolute maximum** and **recommended operating** rows with conditions.
- **Electrical** rows the checks use: thresholds (enable, UVLO, VIH and VIL formulas), leakage
  with its test voltage and temperature, VOL with its test current, timing limits, whether each
  value is guaranteed or typical, and how a guaranteed value is backed (production test, design
  or characterization) from the table notes.
- **Equations** the checks use (output voltage, frequency, ripple, slope, current limit,
  soft-start), with their valid range.
- **Layout rules** stated in the datasheet.
- **Errata** that apply.
- **Example envelope** for every regulator: one entry per example or typical application circuit
  with VIN range, VOUT, IOUT, fsw, L, COUT as drawn (with part types), compensation mode and
  values, light-load mode, and the computed up-slew `(VIN * Dmax - VOUT) / L`. If no example uses
  the board's compensation mode, record that under not_published.
- **Not published**: explicit entries for every value a check needs and the documents lack.

## Not published

Write what is missing, where you looked, and the consequence: a footprint, a bench test, a vendor
question, or a model. Common ones: internal compensation network; error amplifier to current
gain; bead inductance at low frequency and its DC-bias drop; sink current in a given mode;
guaranteed minimum on and off times; internal pull tolerance; leakage at the board's bias; VF at
cold at the real current. A check that needs a missing value must not be skipped or passed. See
[bead tank at the switching frequency](../../docs/lessons/bead-tank-at-switching-frequency.md),
where a missing bead value led a reviewer to stay silent.

## Curves

Digitize the curves the checks use (MLCC bias, bead impedance against current, dropout against
current, PSRR against frequency, VF against temperature, leakage against temperature) to CSV with
page, conditions and method, and state the read error. Prefer vendor data files or simulators
when they exist.

## Conditions

Keep the test conditions with every value: leakage at which reverse voltage and temperature, VF
at which current, thresholds at which supply. Many wrong findings, and many wrong passes, come
from a value used outside its conditions.

## Running it

One agent per MPN, in parallel, each given the schema and the questions its block checklist will
ask of that part. The main agent then spot-checks three values per digest against the page image.
Reviewed digests may be committed to the repo per docs/CONVENTIONS.md and reused on later boards
after checking the revision.
