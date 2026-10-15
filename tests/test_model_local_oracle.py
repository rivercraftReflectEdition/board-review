"""Generated digests against hand-made ones kept in tests/local/oracle/<board>/ (git-ignored); skips when absent."""

import re
from pathlib import Path

import pytest

from boardreview.model import compare, digest, loaders, naming
from boardreview.model.board import BoardModel

ORACLE = Path(__file__).parent / "local" / "oracle"
BOARDS = sorted(d for d in ORACLE.glob("*") if d.is_dir() and any(d.glob("*.ipc")) and (d / "nets_by_net.md").exists()) \
    if ORACLE.exists() else []
needs_data = pytest.mark.skipif(not BOARDS, reason="no local oracle boards in tests/local/oracle")
NET_LINE = re.compile(r"\*\*(.+?)\*\* \((\d+)\): (.*)")
OPEN_LINE = re.compile(r"^- (\S+): (.*)$")
TOOL_NAME = re.compile(r"^Net[A-Za-z]")
ABSENT = "<absent>"
AGREEMENT_FLOOR = 0.96


def _parse_nets(path: Path) -> dict[str, set[str]]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = NET_LINE.match(line)
        if m and m.group(1) != "?":
            pins = {k.strip() for k in m.group(3).split(",") if k.strip()}
            assert len(pins) == int(m.group(2)), f"hand digest count is off for {m.group(1)}"
            out[m.group(1)] = pins
    return out


def _identity(nets: dict[str, set[str]], open_pins: set[str] = frozenset()) -> dict[str, object]:
    """Pin -> net as the oracle defines it: a person's name, the member set for a tool name, None when alone."""
    out: dict[str, object] = {k: None for k in open_pins}
    for name, pins in nets.items():
        ident = None if len(pins) == 1 else frozenset(pins) if TOOL_NAME.match(name) else name
        out.update({k: ident for k in pins})
    return out


def _hand(board: Path) -> dict[str, object]:
    """Hand digest pins; a pin listed only under '?' is unknown to the hand digest and left out."""
    return _identity(_parse_nets(board / "nets_by_net.md"))


def _parse_digest(text: str) -> tuple[dict[str, set[str]], set[str]]:
    """Nets and open pins read back from a generated nets_by_net.md, by its text alone."""
    nets = {m.group(1): set(m.group(3).split(", ")) for m in map(NET_LINE.match, text.splitlines()) if m}
    section = text.split("## Pins with no net", 1)[1] if "## Pins with no net" in text else ""
    open_pins = {f"{m.group(1)}.{item.split(' (')[0].strip()}" for m in map(OPEN_LINE.match, section.splitlines())
                 if m for item in m.group(2).split(", ")}
    return nets, open_pins


def _disagreements(expected: dict[str, object], got: dict[str, object]) -> list[str]:
    keys = sorted(set(expected) | set(got))
    return [k for k in keys if expected.get(k, ABSENT) != got.get(k, ABSENT)]


def _check_agreement(board: Path, expected: dict[str, object], got: dict[str, object]) -> None:
    diff = _disagreements(expected, got)
    listed = [f"{k}: hand {expected.get(k, ABSENT)} -> generated {got.get(k, ABSENT)}" for k in diff]
    exact = board / "expected_differences.txt"
    if exact.exists():
        want = {ln.strip() for ln in exact.read_text(encoding="utf-8").splitlines() if ln.strip()}
        assert set(diff) == want, "\n".join(listed)
    total = len(set(expected) | set(got))
    assert 1 - len(diff) / total >= AGREEMENT_FLOOR, f"{len(diff)} of {total} pins disagree:\n" + "\n".join(listed)


def _oracle_model(board: Path) -> BoardModel:
    m = BoardModel(pin_list_complete=True)
    for net, pins in _parse_nets(board / "nets_by_net.md").items():
        for key in pins:
            ref, _, pin = key.partition(".")
            m.add_pin(ref, pin, net)
    return m.finalize()


def _generated(board: Path) -> BoardModel:
    netlist = next(board.glob("*.ipc"))
    bom = next(iter(sorted(board.glob("*.xlsx")) + sorted(board.glob("*.csv"))), None)
    return loaders.load_with_bom(netlist, bom)[0]


@needs_data
@pytest.mark.parametrize("board", BOARDS, ids=lambda d: d.name)
def test_generated_digest_text_agrees_with_hand_digest(board):
    nets, open_pins = _parse_digest(digest.nets_by_net(_generated(board)))
    _check_agreement(board, _hand(board), _identity(nets, open_pins))


@needs_data
@pytest.mark.parametrize("board", BOARDS, ids=lambda d: d.name)
def test_every_pin_of_either_source_agrees_with_hand_digest(board):
    gen = _generated(board)
    got = {p.key: p.net for p in gen.pins.values()}
    nets: dict[str, set[str]] = {}
    for key, net in got.items():
        if net is not None:
            nets.setdefault(net, set()).add(key)
    _check_agreement(board, _hand(board), _identity(nets, {k for k, n in got.items() if n is None}))


def test_oracle_rules_count_missing_extra_and_moved_pins():
    hand = _identity({"VCC": {"U1.1", "C1.1"}, "NetC2_1": {"C2.1", "U1.2"}, "NetU1_3": {"U1.3"}})
    same = _identity({"VCC": {"U1.1", "C1.1"}, "NetC2_2": {"C2.1", "U1.2"}}, {"U1.3"})
    assert _disagreements(hand, same) == []
    other = _identity({"VCC": {"U1.1"}, "GND": {"C1.1", "R9.1"}, "NetC2_1": {"C2.1", "U1.2"}})
    assert _disagreements(hand, other) == ["C1.1", "R9.1", "U1.1", "U1.3"]
    nets, open_pins = _parse_digest("**A** (2): R1.1, U1.1\n\n## Pins with no net (2)\n\n- U1: 7 (NC), 10\n")
    assert nets == {"A": {"R1.1", "U1.1"}} and open_pins == {"U1.7", "U1.10"}


@needs_data
@pytest.mark.parametrize("board", BOARDS, ids=lambda d: d.name)
def test_every_net_difference_is_explained_by_the_compare(board):
    hand, gen = _oracle_model(board), _generated(board)
    pair = compare.compare([("hand", hand), ("generated", gen)]).pairs[0]
    moved = {k for k, _, _ in pair.moved}
    gone = set(pair.only_a) | set(pair.only_b)
    for net in hand.nets.values():
        name = pair.net_map.get(net.name, net.name)
        ours = set(gen.nets[name].pins) if name in gen.nets else set()
        for key in set(net.pins) ^ ours:
            assert key in moved or key.partition(".")[0] in gone, f"{net.name}: {key} unexplained"


@needs_data
@pytest.mark.parametrize("board", BOARDS, ids=lambda d: d.name)
def test_hand_power_nets_appear_in_power_tree(board):
    path = board / "power_nets.md"
    if not path.exists():
        pytest.skip("no power_nets.md")
    gen = _generated(board)
    tree = digest.power_tree(gen)
    sections = set(re.findall(r"^## (\S+)", tree, re.M))
    for net in _parse_nets(path):
        if net in gen.nets and naming.net_kind(net) in ("rail", "ground", "chassis"):
            assert net in sections, net


@needs_data
@pytest.mark.parametrize("board", BOARDS, ids=lambda d: d.name)
def test_bom_mpns_agree_with_hand_table(board):
    path = board / "bom_table.md"
    if not path.exists():
        pytest.skip("no bom_table.md")
    gen = _generated(board)
    rows = {r: v.strip() for r, v in re.findall(r"^- (\S+) \| (.*?) \|", path.read_text(encoding="utf-8"), re.M)}
    got = {r: c.mpn for r, c in gen.components.items()}
    diff = _disagreements(rows, got)
    listed = [f"{r}: hand {rows.get(r, ABSENT)} -> generated {got.get(r, ABSENT)}" for r in diff]
    total = len(set(rows) | set(got))
    assert 1 - len(diff) / total >= 0.90, f"{len(diff)} of {total} parts disagree:\n" + "\n".join(listed)
