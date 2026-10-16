"""Every CLI command writes UTF-8, so Ω, µ and ° never crash a cp1252 console or pipe on Windows."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from boardreview.model import serialize
from boardreview.model.board import BoardModel

ROOT = Path(__file__).resolve().parent.parent


def _model(tmp_path: Path) -> Path:
    m = BoardModel(pin_list_complete=True)
    m.add_pin("FB1", "1", "VIN", "")
    m.add_pin("FB1", "2", "VCC_µC", "")
    m.add_pin("U1", "1", "VCC_µC", "VDD")
    m.add_pin("U1", "2", "GND", "GND")
    m.add_pin("C1", "1", "VCC_µC")
    m.add_pin("C1", "2", "GND")
    m.add_pin("R1", "1", "SENSE_Ω")
    m.add_pin("R1", "2", "GND")
    m.component("C1").value = "10µF"
    m.component("R1").value = "4.7Ω"
    m.finalize()
    path = tmp_path / "board_Ω_°C.json"
    serialize.write_json(m, path)
    return path


def _run(tmp_path: Path, *argv: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(ROOT / "tools"), PYTHONIOENCODING="cp1252")
    return subprocess.run([sys.executable, *argv], capture_output=True, env=env, cwd=tmp_path)


@pytest.mark.parametrize("module, extra, needle", [
    ("boardreview", ["prep", "{model}", "--out", "facts"], "board_Ω_°C.json"),
    ("boardreview.blocks", ["{model}"], "VCC_µC"),
    ("boardreview.lint", ["{model}"], "SENSE_Ω"),
    ("boardreview.model", ["build", "{model}", "--out", "built"], ""),
])
def test_commands_write_utf8_on_a_cp1252_stream(tmp_path, module, extra, needle):
    model = _model(tmp_path)
    run = _run(tmp_path, "-m", module, *[a.replace("{model}", str(model)) for a in extra])
    assert b"UnicodeEncodeError" not in run.stderr, run.stderr.decode("utf-8", "replace")
    assert run.returncode in (0, 1)
    assert needle in run.stdout.decode("utf-8")


def test_validate_prints_unicode_errors_as_utf8(tmp_path):
    f = {"id": "F-001", "title": "R1 4.7Ω sense", "severity": "Ω", "block": "ldo", "failure_mode": "other",
         "claim": "A claim with µ in it.", "evidence": [{"kind": "bom", "ref": "R1"}], "fix": "Fix",
         "verification": {"status": "CONFIRMED"}}
    (tmp_path / "findings.json").write_text(json.dumps([f], ensure_ascii=False), encoding="utf-8")
    run = _run(tmp_path, "-m", "boardreview", "validate", str(tmp_path / "findings.json"))
    assert b"UnicodeEncodeError" not in run.stderr, run.stderr.decode("utf-8", "replace")
    assert run.returncode == 1 and "'Ω' not in" in run.stdout.decode("utf-8")
