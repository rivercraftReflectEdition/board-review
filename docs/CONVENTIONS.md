# Conventions

Everyone writing here (people and agents) follows these.

## Code

- Python 3.11+. Dependencies: numpy and scipy only. Anything else needs a reason in the PR.
- Every calculator returns `boardreview.calc.base.Result`: name, formula as text, inputs and outputs
  as `Quantity` with units, a `Verdict`, the reason, references and assumptions. A review prints
  `Result.to_markdown()` so the math is visible.
- SI units in floats. Argument names carry the unit: `_v _a _hz _s _f _h _ohm _w _deg _db _c`.
- Short functions, no hidden state, no I/O inside calculators.
- Comments: default to none. When one is needed, one short line that states a specific reason.
  Docstrings: one line.
- Tests: pytest under `tests/`. Every calculator has at least one worked example with its source
  (datasheet page, or a bench record) and an explicit tolerance. Real bench cases from the Sauron
  bring-up are the best tests.

## Data

- Never commit board files, BOMs, schematics, netlists or vendor PDFs (see `.gitignore`).
- Local fixtures go in `tests/local/` or `evals/<board>/local/` (ignored). Committed fixtures are
  synthetic.
- Datasheet digests and curve CSVs may be committed once reviewed; each cites document number,
  revision and page.

## Writing

- Plain engineer prose. Short sentences. No em dashes, no metaphors, no filler.
- Mark anything unverified UNSURE and say what would settle it.

## Git

- One-line imperative commit messages. Author River Dowdy. No trailers.
- Work on a branch per piece; merge to main after review.
