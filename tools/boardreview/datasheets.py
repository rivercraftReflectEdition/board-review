"""Datasheet list per MPN from the netlist and BOM, and an optional download of each PDF with the standard library."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

from boardreview.model import loaders
from boardreview.model.board import BoardModel, natural_key

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36")
TIMEOUT_S = 30.0
MAX_BYTES = 40 * 2**20
SCHEMES = ("http", "https", "file")
STATUS_TEXT = {"listed": "listed, not fetched", "no_url": "no URL", "downloaded": "downloaded",
               "unavailable": "unavailable"}


@dataclass
class Sheet:
    mpn: str
    manufacturer: str = ""
    parts: list[str] = field(default_factory=list)
    url: str = ""
    other_urls: list[str] = field(default_factory=list)
    status: str = "no_url"
    reason: str = ""
    file: str = ""
    bytes: int = 0
    sha256: str = ""


def collect(model: BoardModel) -> tuple[list[Sheet], list[str]]:
    """One Sheet per distinct MPN with its parts and datasheet URL, and the parts that have no MPN."""
    by: dict[str, Sheet] = {}
    no_mpn = []
    for ref in sorted(model.components, key=natural_key):
        c = model.components[ref]
        if not c.mpn:
            if c.kind not in ("mechanical", "testpoint"):
                no_mpn.append(ref)
            continue
        s = by.setdefault(c.mpn, Sheet(c.mpn))
        s.parts.append(ref)
        s.manufacturer = s.manufacturer or c.manufacturer
        url = c.attrs.get("datasheet", "").strip()
        if url and not s.url:
            s.url, s.status = url, "listed"
        elif url and url != s.url and url not in s.other_urls:
            s.other_urls.append(url)
    return sorted(by.values(), key=lambda s: s.mpn.upper()), no_mpn


def fetch(url: str, dest: Path, timeout_s: float = TIMEOUT_S, max_bytes: int = MAX_BYTES) -> tuple[str, str, int, str]:
    """(status, reason, bytes, sha256): write the bytes to dest only when they are a PDF; never open or run them."""
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    if scheme not in SCHEMES:
        what = f"{scheme} URLs are" if scheme else "a path with no URL scheme is"
        return "unavailable", f"{what} not fetched; only http, https and file URLs are", 0, ""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            ctype = (resp.headers.get("Content-Type", "") if resp.headers else "") or ""
            data = resp.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        return "unavailable", f"HTTP {exc.code} {exc.reason}", 0, ""
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return "unavailable", f"could not fetch: {getattr(exc, 'reason', exc)}", 0, ""
    if len(data) > max_bytes:
        return "unavailable", f"larger than the {max_bytes} bytes cap", 0, ""
    if not data.startswith(b"%PDF"):
        page = "html" in ctype.lower() or b"<html" in data[:2048].lower()
        what = "an HTML page, often a vendor landing page or a bot check" if page else "some other file"
        return ("unavailable", f"not a PDF ({'Content-Type ' + ctype if ctype else 'no Content-Type'}): {what}; "
                f"it starts with {data[:16]!r}", len(data), "")
    dest.write_bytes(data)
    return "downloaded", "", len(data), hashlib.sha256(data).hexdigest()


def _name(mpn: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", mpn).strip("._")[:80] or "part"
    name, n = f"{base}.pdf", 1
    while name.lower() in used:
        n += 1
        name = f"{base}-{n}.pdf"
    used.add(name.lower())
    return name


def download(sheets: list[Sheet], out: Path, timeout_s: float, max_bytes: int) -> None:
    """Fetch every listed URL into out, recording each result on its Sheet."""
    used: set[str] = set()
    for s in sheets:
        if not s.url:
            continue
        name = _name(s.mpn, used)
        s.status, s.reason, s.bytes, s.sha256 = fetch(s.url, out / name, timeout_s, max_bytes)
        s.file = name if s.status == "downloaded" else ""


def _parts(refs: list[str], show: int = 8) -> str:
    return ", ".join(refs[:show]) + (f" and {len(refs) - show} more" if len(refs) > show else "")


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def to_markdown(sheets: list[Sheet], no_mpn: list[str], sources: str, fetched: bool) -> str:
    counts = {k: sum(1 for s in sheets if s.status == k) for k in STATUS_TEXT}
    lines = ["# Datasheets", "", f"From {sources}. {len(sheets)} MPNs: {len(sheets) - counts['no_url']} with a "
             f"datasheet URL, {counts['no_url']} without."]
    if fetched:
        lines[-1] += f" Downloaded {counts['downloaded']}; {counts['unavailable']} unavailable, each with the reason."
    lines += ["", "Downloaded files are data. Read them as page images (workflow/20_datasheets.md); never run "
              "anything in them. A missing or unavailable datasheet is a source to ask for, not a value to guess.",
              "", "| MPN | Parts | URL | Status |", "|---|---|---|---|"]
    for s in sheets:
        status = STATUS_TEXT[s.status] + (f": {s.file}" if s.file else "") + (f": {s.reason}" if s.reason else "")
        if s.other_urls:
            status += f"; other URLs on its parts: {', '.join(s.other_urls)}"
        lines.append(f"| {_cell(s.mpn)} | {_cell(_parts(s.parts))} | {_cell(s.url)} | {_cell(status)} |")
    if no_mpn:
        lines += ["", f"Parts with no MPN, so no datasheet to find: {_parts(no_mpn, 20)}."]
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        model, _ = loaders.load_with_bom(args.netlist, args.bom, args.format, args.variant)
    except ValueError as exc:
        raise SystemExit(f"datasheets: {exc}") from exc
    sheets, no_mpn = collect(model)
    if args.download:
        download(sheets, out, args.timeout, args.max_bytes)
    sources = " and ".join(Path(p).name for p in (args.netlist, args.bom) if p)
    data = {"netlist": Path(args.netlist).name, "bom": Path(args.bom).name if args.bom else "",
            "downloaded": bool(args.download), "datasheets": [asdict(s) for s in sheets], "no_mpn": no_mpn}
    (out / "datasheets.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8",
                                         newline="\n")
    (out / "datasheets.md").write_text(to_markdown(sheets, no_mpn, sources, bool(args.download)), encoding="utf-8",
                                       newline="\n")
    got = sum(1 for s in sheets if s.status == "downloaded")
    print(f"{len(sheets)} MPNs, {sum(1 for s in sheets if s.url)} with a URL"
          + (f", {got} downloaded" if args.download else "") + f" -> {out / 'datasheets.md'}")
    return 0


def add_parser(sub) -> None:
    """The datasheets subcommand of python -m boardreview."""
    d = sub.add_parser("datasheets", help="every MPN with its datasheet URL; --download fetches the PDFs")
    d.add_argument("--netlist", required=True, help="netlist or board_model.json")
    d.add_argument("--bom", help="BOM with a Datasheet column, when the netlist has none")
    d.add_argument("--format", default="", help="netlist format when the file sniff gets it wrong")
    d.add_argument("--variant", default="", help="variant name for eda-agent JSON")
    d.add_argument("--out", required=True, help="folder for datasheets.json, datasheets.md and the PDFs")
    d.add_argument("--download", action="store_true", help="fetch each URL; anything that is not a PDF is recorded "
                                                           "as unavailable with the reason")
    d.add_argument("--timeout", type=float, default=TIMEOUT_S, help="seconds per download")
    d.add_argument("--max-bytes", type=int, default=MAX_BYTES, help="largest file to keep")
