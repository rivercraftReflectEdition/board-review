"""Part checks against the BOM: fitted parts with no MPN, parts in only one of netlist and BOM."""

from __future__ import annotations

from boardreview.lint.base import Finding, Skip
from boardreview.model.board import BoardModel, natural_key
from boardreview.model.graph import Graph

NO_MPN_KINDS = {"mechanical", "testpoint"}


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
    return out
