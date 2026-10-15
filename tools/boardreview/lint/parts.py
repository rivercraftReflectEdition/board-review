"""Part checks against the BOM: fitted parts with no MPN, parts in only one of netlist and BOM."""

from __future__ import annotations

from boardreview.lint.base import Finding, Skip
from boardreview.model.board import BoardModel, natural_key
from boardreview.model.graph import Graph

NO_MPN_KINDS = {"mechanical", "testpoint"}
BOARD_MADE = NO_MPN_KINDS | {"jumper"}


def _has_part_data(model: BoardModel) -> bool:
    return any(s.get("kind") == "bom" for s in model.sources) or any(c.mpn for c in model.components.values())


def fitted_without_mpn(model: BoardModel, g: Graph) -> list[Finding]:
    """Fitted parts with no manufacturer part number; mechanical features and test points excluded."""
    if not _has_part_data(model):
        raise Skip("no BOM loaded and the netlist carries no MPN fields")
    refs = sorted((r for r, c in model.components.items() if c.fitted and not c.mpn and c.kind not in NO_MPN_KINDS),
                  key=natural_key)
    if not refs:
        return []
    return [Finding("fitted_without_mpn", "warning",
                    f"{len(refs)} fitted parts have no MPN: {', '.join(refs)}", components=refs)]


def bom_netlist_mismatch(model: BoardModel, g: Graph) -> list[Finding]:
    """Parts in the BOM with no pins in the netlist, and netlist parts the BOM does not list."""
    if not any(s.get("kind") == "bom" for s in model.sources):
        raise Skip("no BOM loaded")
    out = []
    bom_only = sorted((r for r, c in model.components.items() if c.attrs.get("bom_only")), key=natural_key)
    net_only = sorted((r for r, c in model.components.items() if c.attrs.get("in_bom") == "no"), key=natural_key)
    for refs, where, other in ((bom_only, "BOM", "netlist"), (net_only, "netlist", "BOM")):
        real = [r for r in refs if model.components[r].kind not in NO_MPN_KINDS]
        mech = [r for r in refs if r not in real]
        if real:
            out.append(Finding("bom_netlist_mismatch", "warning",
                               f"{len(real)} parts are in the {where} but not the {other}: {', '.join(real)}",
                               components=real))
        if mech:
            out.append(Finding("bom_netlist_mismatch", "info",
                               f"mechanical or test parts only in the {where}: {', '.join(mech)}", components=mech))
    excluded = sorted((r for r, c in model.components.items() if c.attrs.get("in_bom") == "excluded"), key=natural_key)
    if excluded:
        out.append(Finding("bom_netlist_mismatch", "info",
                           f"{len(excluded)} parts are excluded from the BOM in the schematic and absent from it as "
                           f"expected: {', '.join(excluded)}", components=excluded))
    bought = [r for r in excluded if model.components[r].fitted and model.components[r].kind not in BOARD_MADE]
    if bought:
        out.append(Finding("bom_netlist_mismatch", "warning",
                           f"{len(bought)} fitted parts are excluded from the BOM, so nobody buys or places them: "
                           f"{', '.join(bought)}; confirm each is made by the board itself or mark it DNP",
                           components=bought))
    for ref in sorted((r for r, c in model.components.items() if c.attrs.get("fitted_conflict")), key=natural_key):
        why = model.components[ref].attrs["fitted_conflict"]
        out.append(Finding("bom_netlist_mismatch", "warning",
                           f"{ref} fitted state differs between netlist and BOM ({why}); confirm which build is meant",
                           components=[ref], evidence={"fitted_conflict": why}))
    return out
