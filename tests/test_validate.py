import json

import pytest

from boardreview.__main__ import main
from boardreview.schema import SCHEMAS, check_file


def _finding(**kw):
    f = {"id": "F-001", "title": "R11 value stops U1", "severity": "blocker", "block": "enable_uvlo_sequencing",
         "failure_mode": "wrong_value", "claim": "R11 is 10 ohm, the converter never enables.",
         "evidence": [{"kind": "bom", "ref": "R11"}], "fix": "R11 to 10k", "verification": {"status": "CONFIRMED"}}
    f.update(kw)
    return f


def test_schemas_are_found_from_the_package():
    assert (SCHEMAS / "finding.schema.json").exists()


@pytest.mark.parametrize("wrap", [lambda fs: fs, lambda fs: {"findings": fs}])
def test_valid_findings_pass(tmp_path, wrap, capsys):
    path = tmp_path / "findings.json"
    path.write_text(json.dumps(wrap([_finding()])), encoding="utf-8")
    assert check_file(path) == []
    assert main(["validate", str(path)]) == 0
    assert "1 findings, 0 errors" in capsys.readouterr().out


def test_errors_name_the_finding_and_the_field(tmp_path, capsys):
    path = tmp_path / "findings.json"
    path.write_text(json.dumps([_finding(), _finding(id="F-002", severity="huge", verification={})]),
                    encoding="utf-8")
    errors = check_file(path)
    assert any(e.startswith("F-002: $.severity") for e in errors)
    assert any(e.startswith("F-002: $.verification: missing status") for e in errors)
    assert main(["validate", str(path)]) == 1
    assert "F-002" in capsys.readouterr().out


def test_digest_schema_by_name(tmp_path):
    path = tmp_path / "digest.json"
    path.write_text(json.dumps({"mpn": "X"}), encoding="utf-8")
    assert check_file(path, "digest")


def test_not_json_is_an_error(tmp_path):
    path = tmp_path / "findings.json"
    path.write_text("{not json", encoding="utf-8")
    assert check_file(path)[0].startswith("not valid JSON")


def _check(**kw):
    c = {"id": "U2.BR-1", "block": "buck_regulator", "instance": "U2", "item": "BR-1", "verdict": "pass"}
    c.update(kw)
    return c


@pytest.mark.parametrize("wrap", [lambda cs: cs, lambda cs: {"board": "x", "checks": cs}])
def test_checks_validate_as_a_list_or_under_checks(tmp_path, wrap, capsys):
    path = tmp_path / "checks.json"
    path.write_text(json.dumps(wrap([_check(), _check(id="U2.BR-2", item="BR-2", verdict="unknown",
                                                     reason="No datasheet.")])), encoding="utf-8")
    assert check_file(path, "checks") == []
    assert main(["validate", "--schema", "checks", str(path)]) == 0
    assert "2 checks, 0 errors" in capsys.readouterr().out


def test_check_errors_name_the_check_and_duplicate_ids(tmp_path, capsys):
    path = tmp_path / "checks.json"
    path.write_text(json.dumps([_check(), _check(verdict="unknown"), _check(id="X.BR-9", item="bad")]),
                    encoding="utf-8")
    errors = check_file(path, "checks")
    assert any(e.startswith("U2.BR-1: $: missing reason") for e in errors)
    assert any(e.startswith("X.BR-9: $.item") for e in errors)
    assert "check id U2.BR-1 is used twice" in errors
    assert main(["validate", "--schema", "checks", str(path)]) == 1
    assert "3 checks" in capsys.readouterr().out


def test_a_checks_file_that_is_not_a_list_is_an_error(tmp_path):
    path = tmp_path / "checks.json"
    path.write_text(json.dumps({"board": "x"}), encoding="utf-8")
    assert check_file(path, "checks") == ["$: expected a list of checks or an object with a checks list"]
