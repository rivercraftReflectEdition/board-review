# 2. Datasheets

Goal: one digest per MPN with every fact the checklists need, each with its page, and an explicit
list of what the documents do not publish.

## Get the documents

With network access, run `python -m boardreview datasheets` with `--download` on the stage 1
facts (`--help` lists its inputs). It collects the MPN and datasheet URL fields from the netlist
or BOM, downloads each PDF into the review folder, and records a response that is not a PDF as
unavailable. Then read the PDFs as below. A URL field can point at a product page or an old
revision; check what arrived.

Without network access, use the PDFs the user supplied and ask once for the others the checks
need. When the user says a PDF is unavailable, do not ask again: write a source_unavailable
record for it (below) and go on.

## One digest per MPN

- File: `<review folder>/digests/<MPN>.json`, validated against
  `schemas/datasheet_digest.schema.json`. Curves go next to it as CSV.
- One digest per orderable variant when the suffix changes behavior (light-load mode, supply
  voltage code, threshold option, temperature grade). Record the variants in
  `orderable_variants` and check which one the BOM orders.
- Record document number, revision and date. Check the vendor's site for a newer revision and
  for an errata sheet that matches the silicon revision on the board. Offline, say in
  `read_from.notes` that neither was checked.

## Source unavailable is not "not published"

`not_published` says the documents were read and lack a value. It is a fact about the vendor's
documents. When no document was read for an MPN (no URL, a download that returned a web page, no
network, or the user said the PDF is unavailable), write `<review folder>/digests/<MPN>.json`
with `status` set to `source_unavailable` and an `unavailable` block: the reason, what was tried,
the checklist items that need the part, and the consequence. The record needs no pages and no
pin table, and it holds no values from memory. It says nothing about what the vendor publishes.
Every check that needs the part stays unknown, the action is to get the document, and the report
lists these MPNs apart from values the vendor does not publish.

## Read from page images

Render the pages to images and read the image. Text extraction may help find a value, but tables
smear columns, footnotes detach and figure labels move. A value goes in the digest only after it
is read on the page image. List the pages read in `read_from.pages_read`.

Render with whatever is installed, for example `pdftoppm -r 150 -f 12 -l 12 -png ds.pdf page`
(poppler) or PyMuPDF (`fitz`). Claude Code reads a PNG, or a PDF page range, with its file read
tool; Codex opens a PNG with its image viewer tool. An agent that cannot see images marks every
value it could not read on a page image UNSURE. When the Python that runs `boardreview` has no
renderer, another installed Python may render the pages (workflow/setup.md).

## Required content

- **Pin table** with type, reference supply (domain), function, internal pull with its range,
  what to do when unused, and page.
- **Straps**: every pin sampled at reset, its levels, the network per level, when it is sampled,
  and whether software can override it.
- **Absolute maximum** and **recommended operating** rows with conditions.
- **Relative limits**: a bound stated against another pin goes in `relative_limits` with the
  pins it uses, for example OUT abs max `min(VIN + 0.3, 3.6)` with references `VIN`, or EN at most
  `VIN`. Leave that bound out of `min` and `max`: a fixed 3.6 V there would pass 3.5 V on OUT
  while VIN is at 1.8 V or off.
- **Electrical** rows the checks use: thresholds (enable, UVLO, VIH and VIL formulas), leakage
  with its test voltage and temperature, VOL with its test current, timing limits, whether each
  value is guaranteed or typical, and how a guaranteed value is backed from the table notes:
  production test, design, characterization or statistical analysis; `mixed` when the notes name
  several methods without saying which row uses which; `unspecified` when they do not say.
- **Equations** the checks use (output voltage, frequency, ripple, slope, current limit,
  soft-start), with their valid range.
- **Layout rules** stated in the datasheet.
- **Errata** that apply.
- **Example envelope** for every regulator: one entry per example or typical application circuit
  with VIN range, VOUT, IOUT, L, COUT as drawn (with part types), fsw for a switcher, light-load
  mode, and the computed up-slew `(VIN * Dmax - VOUT) / L` when Dmax is given for the variant. An
  LDO example sets `topology` to `linear` and needs no fsw. A generic fixed-output figure that
  prints no VOUT is recorded at the ordered variant's VOUT, said so in `notes`. If no example
  uses the board's compensation mode and output setting, record that under not_published. Keep
  three things apart:
  - `compensation.mode`: the controller's own compensation, internal or external (a network on a
    COMP or ITH pin).
  - `compensation.feedback_shaping`: a Cff or other part on an external divider. It shapes the
    loop but is not external compensation; a part with no COMP pin stays internal.
  - `output_setting`: adjustable (external divider) or fixed (the divider is inside the part).
    An adjustable example's Cff network does not carry over to a fixed-output variant.
- **Not published**: explicit entries for every value a check needs and the documents lack.

## Conflicts inside one document

A datasheet can disagree with itself: a repeated table with other pin labels, prose that rounds
a limit, a figure that differs from its table. Precedence:

1. Which pin a row is about: the pin configuration and functions table wins.
2. A value: the electrical characteristics, absolute maximum and recommended operating tables
   win over prose, application sections and figure labels.
3. Two tables that still disagree: neither wins. Use the more conservative value and say so.
4. A newer revision or a matching erratum overrides all of these.

Keep every row under `conflicts` with its page and which one the digest uses. Mark checks that
depend on it UNSURE and add a vendor question.

## Not published

Write what is missing, where you looked, and the consequence: a footprint, a bench test, a vendor
question, or a model. Common ones: internal compensation network; error amplifier to current
gain; bead inductance at low frequency and its DC-bias drop; sink current in a given mode;
guaranteed minimum on and off times; internal pull tolerance; leakage at the board's bias; VF at
cold at the real current. A check that needs a missing value must not be skipped or passed. See
[bead tank at the switching frequency](../lessons/bead-tank-at-switching-frequency.md),
where a missing bead value led a reviewer to stay silent.

## Capacitor limits

Record whether a capacitance limit is nominal or effective, and at which bias.

- Nominal: a table gives COUT 0.47 to 22 uF, and a note says the range already allows for about
  50 percent loss to bias, tolerance and temperature. Compare the BOM's nominal value with it.
  Requiring 0.47 uF effective would count the derating twice.
- Effective: a note asks for at least 2.2 uF effective over bias and temperature. Compare
  `calc.mlcc_bias.mlcc_effective` at the board's bias and both temperature corners.
- Out of condition: a minimum of 5.75 uF stated at 1.8 V bias, on a rail that runs at 3.3 V.
  Keep the 1.8 V condition in the digest. Derate the board's capacitor at 3.3 V, never at 1.8 V,
  and compare. The datasheet does not say the minimum holds at 3.3 V, so the item stays unknown
  with a vendor question even when the capacitor clears it.

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

One agent per MPN, in parallel where the agent allows it (subagents in any agent that has them,
separate `codex exec` runs in Codex), or one MPN after another. Each gets the schema and the
questions its block checklist will ask of that part. The main agent then spot-checks three values
per digest against the page image, and checks each digest, and each source_unavailable record,
with `python -m boardreview validate <digest>.json --schema digest`.
Reviewed digests may be committed to the repo per docs/CONVENTIONS.md and reused on later boards
after checking the revision.
