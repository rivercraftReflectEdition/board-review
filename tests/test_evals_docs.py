import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill"
LESSONS = ROOT / "docs" / "lessons"
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def _docs():
    return sorted(list(SKILL.rglob("*.md")) + list(LESSONS.glob("*.md")) + list((ROOT / "evals").rglob("*.md")))


def test_relative_links_resolve():
    broken = []
    for doc in _docs():
        for target in LINK.findall(doc.read_text(encoding="utf-8")):
            if target.startswith("http"):
                continue
            if not (doc.parent / target).resolve().exists():
                broken.append(f"{doc.relative_to(ROOT)} -> {target}")
    assert broken == []


def test_lessons_state_a_rule_and_link_a_checklist_item():
    pages = [p for p in LESSONS.glob("*.md") if p.name != "README.md"]
    assert len(pages) >= 10
    for p in pages:
        text = p.read_text(encoding="utf-8")
        assert "**Rule:**" in text, p.name
        assert "skill/checklists/" in text or "skill/workflow/" in text, p.name
        assert p.name in (LESSONS / "README.md").read_text(encoding="utf-8"), p.name


def test_checklist_examples_point_at_lessons():
    for p in (SKILL / "checklists").glob("*.md"):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith("- Example:"):
                assert "docs/lessons/" in line, (p.name, line)


def test_checklists_have_no_board_specific_thresholds():
    for p in (SKILL / "checklists").glob("*.md"):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith("- Example:"):
                continue
            assert "Sauron" not in line, (p.name, line)


def test_every_item_has_check_why_compute_pass():
    for p in (SKILL / "checklists").glob("*.md"):
        items = re.split(r"\n## ", p.read_text(encoding="utf-8"))[1:]
        assert items, p.name
        for item in items:
            head = item.splitlines()[0]
            for field in ("- Check:", "- Why:", "- Compute:", "- Pass:"):
                assert field in item, (p.name, head, field)


def test_no_em_or_en_dashes():
    for doc in _docs():
        text = doc.read_text(encoding="utf-8")
        assert "—" not in text and "–" not in text, doc.name


def test_skill_frontmatter_and_length():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: board-review\ndescription: ")
    assert len(text.splitlines()) < 150
