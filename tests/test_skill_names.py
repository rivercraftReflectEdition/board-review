"""Every tool name the skill text cites resolves by import, so the text cannot drift from the code."""

import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill"
PACKAGES = ("calc", "sim", "model", "lint", "blocks", "report")
RELATIVE = re.compile(r"(?<![\w/.])((?:" + "|".join(PACKAGES) + r")(?:\.[A-Za-z_]\w*)+)")
ABSOLUTE = re.compile(r"\bboardreview(?:\.[A-Za-z_]\w*)+")
RESULT = re.compile(r"(?<![\w.])Result\.([A-Za-z_]\w*)")
CLI = re.compile(r"python -m (boardreview(?:\.\w+)*)(?: ([a-z_]+(?:-[a-z_]+)*)(?![\w-]|\.\w))?")
PATH = re.compile(r"\btools/boardreview(?:/\w+)*")
FILE_EXT = {"json", "md", "csv", "py", "txt", "net", "xml", "ipc", "raw", "log", "asc"}


def _texts() -> dict[str, str]:
    files = sorted(SKILL.rglob("*.md")) + sorted((SKILL / "schemas").glob("*.json"))
    files += [ROOT / "README.md"] + sorted((ROOT / "docs").rglob("*.md"))
    return {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8") for p in files}


def _cited() -> dict[str, set[str]]:
    names: dict[str, set[str]] = {}
    for doc, text in _texts().items():
        found = [f"boardreview.{m}" for m in RELATIVE.findall(text) if m.rsplit(".", 1)[-1] not in FILE_EXT]
        found += [m for m in ABSOLUTE.findall(text) if m.rsplit(".", 1)[-1] not in FILE_EXT]
        found += [f"boardreview.calc.base.Result.{m}" for m in RESULT.findall(text)]
        for name in found:
            names.setdefault(name, set()).add(doc)
    return names


def _cli() -> dict[tuple[str, str], set[str]]:
    out: dict[tuple[str, str], set[str]] = {}
    for doc, text in _texts().items():
        for module, sub in CLI.findall(text):
            out.setdefault((module, sub), set()).add(doc)
    return out


def resolve(name: str):
    """Import the longest module prefix of a dotted name, then follow the rest as attributes."""
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:i]))
        except ModuleNotFoundError:
            continue
        for attr in parts[i:]:
            obj = getattr(obj, attr)
        return obj
    raise ModuleNotFoundError(name)


CITED = _cited()
COMMANDS = _cli()


def test_the_scan_finds_the_citations():
    assert len(CITED) > 40
    for name in ("boardreview.calc.protection.tvs_standoff", "boardreview.sim.setups.run_loop_gain",
                 "boardreview.model.compare", "boardreview.calc.base.Result.to_markdown"):
        assert name in CITED, name


@pytest.mark.parametrize("name", sorted(CITED))
def test_cited_name_resolves(name):
    try:
        resolve(name)
    except (ImportError, AttributeError) as exc:
        pytest.fail(f"{name} cited in {sorted(CITED[name])} does not resolve: {exc}")


@pytest.mark.parametrize("old", ["boardreview.calc.tvs", "boardreview.sim.loop_gain", "boardreview.sim.pdn",
                                 "boardreview.calc.buck.gate_drive"])
def test_resolver_rejects_names_that_do_not_exist(old):
    with pytest.raises((ImportError, AttributeError)):
        resolve(old)


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_cited_command_runs(command, capsys):
    module, sub = command
    main = importlib.import_module(f"{module}.__main__").main
    if not sub:
        return
    with pytest.raises(SystemExit) as stop:
        main([sub, "--help"])
    assert stop.value.code == 0, f"python -m {module} {sub} cited in {sorted(COMMANDS[command])}"


def test_cited_paths_exist():
    for doc, text in _texts().items():
        for path in PATH.findall(text):
            assert (ROOT / path).exists(), f"{doc}: {path}"


def _bullet(name: str) -> str:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    return re.search(rf"^- `{name}`:(.*?)(?=^- |\Z)", text, re.M | re.S).group(1)


def test_skill_lists_every_calculator_module():
    listed = set(re.findall(r"`([a-z_][a-z0-9_]*)`", _bullet("calc")))
    modules = {p.stem for p in (ROOT / "tools" / "boardreview" / "calc").glob("*.py")} - {"__init__", "base", "curves"}
    assert listed == modules


def test_skill_sim_setups_exist():
    setups = importlib.import_module("boardreview.sim.setups")
    names = [n for n in re.findall(r"`(\w+)`", _bullet("sim")) if n.startswith("run_")]
    assert names
    for n in names:
        assert hasattr(setups, n), n
