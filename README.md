# board-review

An agent skill for schematic and board reviews that catch what a pin-and-net check misses:
loop stability, LC tanks, sink capability between rails, straps, reset margins, abs-max under
real conditions. Altium first (through eda-agent), KiCad next, one board model for both. It runs
in Claude Code, OpenAI Codex CLI and any agent that reads `SKILL.md` skills and has a shell.

## Principles

1. **Facts before judgment.** Scripts build the board model and datasheet facts. The model judges,
   and every judgment cites a pin, a net, a datasheet page, or a calculator result.
2. **Show the math.** Every check that has a number runs a calculator and prints the formula,
   inputs and result.
3. **"Not published" is an answer.** When a datasheet hides a value (internal compensation, bead
   SRF), the finding becomes a required footprint or a bench test, never a guess.
4. **Every finding survives a refutation pass** by a second agent before it is reported.
5. **Measured by real misses.** The eval set is boards we already know the bugs of. A review that
   misses one is a checklist bug.

## Layout

```
skill/                    installable skill (see Install)
  SKILL.md                entry point: setup, when to use, workflow, rules, finding format
  agents/openai.yaml      Codex UI metadata
  workflow/               one page per stage: intake, extract, datasheets, blocks, checks, verify, report
  checklists/             one page per circuit block (buck, ldo, ferrite/LC, pdn, clocks, resets,
                          io levels, straps, ethernet, csi, xspi memory, protection, sequencing, thermal)
  schemas/                board_model, datasheet_digest, finding, check_result (JSON Schema)
  lessons/                one page per real miss: what, why, which check now catches it
tools/boardreview/        Python package the skill calls (python -m boardreview prep, report,
                          verify-fixes, validate)
  model/                  netlist, BOM and pin map from Altium, KiCad and IPC-D-356; 3-way compare;
                          part position, side and sheet from IPC-D-356, KiCad position files and XML
  lint/                   deterministic checks: single-pin nets, open IC pins, floating grounds, names
  blocks/                 find regulators, filters, clocks, resets, I2C buses and straps in the netlist
  calc/                   calculators: buck, loop (Bode, PM/GM, Cff), lc_tank, mlcc_bias, divider,
                          crystal, i2c, protection (TVS), thermal, timing
  sim/                    LTspice batch runs (ngspice optional): loop-gain injection, load step,
                          PDN and filter impedance, with netlist sanity checks before trusting a run
  report/                 report.html with fix and bench checkboxes, the artifact page, report.md,
                          ticket drafts, analysis.html with every check and plot; verify-fixes
tests/                    calculator and model tests with worked numbers
evals/                    expected findings per board and the scorer (board data stays local)
docs/                     conventions for people and agents working on this repo
```

## Install

One-time setup, from a clone of this repo. Python 3.11 or newer.

```
python -m pip install -e <path to board-review>
python -m boardreview --help
```

Then link the `skill/` folder into each agent's skills folder. The link keeps the skill current
with the repo; the editable install does the same for the Python package.

Windows (cmd.exe; junctions need no admin rights):

```
mkdir "%USERPROFILE%\.claude\skills" "%USERPROFILE%\.codex\skills"
mklink /J "%USERPROFILE%\.claude\skills\board-review" "C:\path\to\board-review\skill"
mklink /J "%USERPROFILE%\.codex\skills\board-review" "C:\path\to\board-review\skill"
```

From PowerShell, run each `mklink` through cmd: `cmd /c 'mklink /J "<link>" "<target>"'`.

macOS and Linux:

```
mkdir -p ~/.claude/skills ~/.codex/skills
ln -s /path/to/board-review/skill ~/.claude/skills/board-review
ln -s /path/to/board-review/skill ~/.codex/skills/board-review
```

Claude Code reads `~/.claude/skills/<name>/SKILL.md`; Codex CLI reads
`~/.codex/skills/<name>/SKILL.md` (or `$CODEX_HOME/skills`). Restart the agent after linking. KiCad
boards also need `kicad-cli` (KiCad 8 or newer; skill/workflow/10_extract.md). Altium boards need
the eda-agent MCP server configured in the agent.

## Data policy

See docs/CONVENTIONS.md for code and writing rules.

Board files, BOMs, schematics and vendor PDFs are never committed. Evals point to local paths
listed in `evals/<board>/sources.local.json` (ignored by git). Datasheet digests (our own notes with
page citations) and curve CSVs from vendor tools may be committed once reviewed.
