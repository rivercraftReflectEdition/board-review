# Working on this repo

For agents changing the skill, the Python package or the evals. To run a board review, use the
skill (`skill/SKILL.md`), not this page.

Read `docs/CONVENTIONS.md` first and follow it: code, data, writing and git rules.

## Setup and tests

```
python -m pip install -e ".[test]"
python -m pytest -q
```

Slow tests (LTspice and other external tools) run only with `BOARDREVIEW_SLOW=1`. Tests that need
a tool or local data that is absent (`kicad-cli`, KiCad demos, `tests/local/`) skip.

## Where things are

- `skill/`: the installed skill. Every path in its text must resolve inside `skill/`, because
  the folder is linked into `~/.claude/skills` and `~/.codex/skills`; `tests/test_evals_docs.py`
  and `tests/test_skill_names.py` check links, cited Python names and commands.
- `tools/boardreview/`: the package behind `python -m boardreview prep` and `validate`.
- `evals/`: expected findings and the scorer. Held-out boards are never read while editing
  checklists or lessons (`evals/README.md`).

## Data

Never commit board files, netlists, BOMs, schematics, PDFs, KiCad projects or anything under
`tests/local/` or `evals/*/local/`. Committed fixtures are synthetic.
