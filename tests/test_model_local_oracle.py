"""Generated digests against hand-made ones kept in tests/local/oracle/<board>/ (git-ignored); skips when absent."""

import re
from pathlib import Path

import pytest

from boardreview.model import compare, digest, loaders, naming
from boardreview.model.board import BoardModel

ORACLE = Path(__file__).parent / "local" / "oracle"
BOARDS = sorted(d for d in ORACLE.glob("*") if d.is_dir() and any(d.glob("*.ipc")) and (d / "nets_by_net.md").exists()) \
    if ORACLE.exists() else []
pytestmark = pytest.mark.skipif(not BOARDS, reason="no local oracle boards in tests/local/oracle")
NET_LINE = re.compile(r"\*\*(.+?)\*\* \((\d+)\): (.*)")


def _parse_nets(path: Path) -> dict[str, set[str]]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = NET_LINE.match(line)
        if m and m.group(1) != "?":
            pins = {k.strip() for k in m.group(3).split(",") if k.strip()}
            assert len(pins) == int(m.group(2)), f"hand digest count is off for {m.group(1)}"
            out[m.group(1)] = pins
    return out


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


@pytest.mark.parametrize("board", BOARDS, ids=lambda d: d.name)
def test_generated_digest_reads_back_as_the_model(board):
    model = _generated(board)
    text = digest.nets_by_net(model)
    parsed = {m.group(1): set(m.group(3).split(", ")) for m in map(NET_LINE.match, text.splitlines()) if m}
    assert parsed == {n.name: set(n.pins) for n in model.nets.values()}


@pytest.mark.parametrize("board", BOARDS, ids=lambda d: d.name)
def test_pin_agreement_with_hand_digest(board):
    pair = compare.compare([("hand", _oracle_model(board)), ("generated", _generated(board))]).pairs[0]
    a, b = _oracle_model(board), _generated(board)
    common = [p.key for p in a.pins.values() if (p.refdes, p.number) in b.pins]
    agree = len(common) - len(pair.moved)
    assert agree / len(common) >= 0.98, f"{agree} of {len(common)} pins agree"


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


@pytest.mark.parametrize("board", BOARDS, ids=lambda d: d.name)
def test_bom_mpns_agree_with_hand_table(board):
    path = board / "bom_table.md"
    if not path.exists():
        pytest.skip("no bom_table.md")
    gen = _generated(board)
    rows = dict(re.findall(r"^- (\S+) \| (.*?) \|", path.read_text(encoding="utf-8"), re.M))
    shared = [r for r in rows if r in gen.components]
    same = [r for r in shared if gen.components[r].mpn == rows[r].strip()]
    assert len(same) / len(shared) >= 0.95, f"{len(same)} of {len(shared)} MPNs agree"
