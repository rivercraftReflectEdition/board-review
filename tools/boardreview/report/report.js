const DATA = JSON.parse(document.getElementById("br-data").textContent);
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const LS = "br-status-" + DATA.key;
const FIDS = DATA.findings;
const BIDS = DATA.bench;
const names = {};
let status = {};
let local = {};
let canWrite = true;

function stateOf(id) { return status[id] || {}; }
function loadLocal() { try { return JSON.parse(localStorage.getItem(LS) || "{}") || {}; } catch (e) { return {}; } }
function saveLocal() { try { localStorage.setItem(LS, JSON.stringify(local)); } catch (e) {} }
function saveNote(text) { const el = $("#br-save"); if (el) el.textContent = text; }

function withLocal(base) {
  const out = {};
  for (const id of FIDS.concat(BIDS)) {
    const b = base[id] || {}, mine = local[id];
    out[id] = mine && (!b.at || (mine.at || "") > b.at) ? { ...b, done: mine.done, at: mine.at, ...(mine.by ? { by: mine.by } : {}) } : { ...b };
  }
  return out;
}

function shortDate(iso) {
  const d = new Date(iso);
  return isNaN(d) ? "" : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function statusText(id) {
  const s = stateOf(id);
  const bits = [];
  if (s.verified === true) bits.push('<span class="ok">Confirmed in the data</span>' + (s.verifyNote ? " · " + esc(s.verifyNote) : ""));
  else if (s.verified === false) bits.push('<span class="bad">Re-review did not find the fix</span>' + (s.verifyNote ? " · " + esc(s.verifyNote) : ""));
  else if (s.verifyNote) bits.push(esc(s.verifyNote));
  if (s.done) {
    const who = s.by && names[s.by] ? names[s.by] : "";
    const when = s.at ? shortDate(s.at) : "";
    bits.push("Marked fixed" + (who ? " by " + esc(who) : "") + (when ? ", " + esc(when) : ""));
  }
  return bits.join(" · ");
}

function renderProgress() {
  const n = FIDS.length || 1;
  const fixed = FIDS.filter(id => stateOf(id).done).length;
  const ver = FIDS.filter(id => stateOf(id).verified === true).length;
  const bench = BIDS.filter(id => stateOf(id).done).length;
  $("#br-nfix").textContent = fixed;
  $("#br-nver").textContent = ver;
  $("#br-nbench").textContent = bench;
  $("#br-barver").style.width = (ver / n * 100) + "%";
  $("#br-barfix").style.width = (Math.max(0, fixed - ver) / n * 100) + "%";
  const sum = $("#br-bench-sum");
  if (sum) sum.textContent = BIDS.length ? `${bench} of ${BIDS.length} done` : "No bench steps";
}

function refreshStatus() {
  for (const id of FIDS) {
    const s = stateOf(id), el = document.getElementById(id);
    if (!el) continue;
    el.classList.toggle("is-done", !!s.done);
    el.classList.toggle("is-verified", s.verified === true);
    const c = document.getElementById("chk-" + id);
    if (c) { c.checked = !!s.done; c.disabled = !canWrite; }
    const st = document.getElementById("st-" + id);
    if (st) st.innerHTML = statusText(id);
  }
  for (const id of BIDS) {
    const s = stateOf(id), li = document.getElementById("bench-" + id);
    if (!li) continue;
    li.classList.toggle("is-done", !!s.done);
    const c = document.getElementById("chk-" + id);
    if (c) { c.checked = !!s.done; c.disabled = !canWrite; }
  }
  renderProgress();
}

function minimap(marked, active, label) {
  const P = DATA.place;
  if (!P || !P.extent) return "";
  const [x0, y0, x1, y1] = P.extent;
  const w = Math.max(x1 - x0, 1e-3), h = Math.max(y1 - y0, 1e-3);
  const W = 180, m = 16, H = Math.round(Math.min(240, Math.max(80, (W - 2 * m) * h / w + 2 * m)));
  const s = Math.min((W - 2 * m) / w, (H - 2 * m) / h);
  const ox = (W - w * s) / 2, oy = (H - h * s) / 2;
  const X = x => ox + (x - x0) * s, Y = y => oy + (y1 - y) * s;
  const dot = (p, r, color, on) => {
    const at = `cx="${X(p[0]).toFixed(1)}" cy="${Y(p[1]).toFixed(1)}" r="${r}"`;
    if (p[2] === "b") return `<circle ${at} style="fill:${on ? "var(--blocker-soft)" : "none"};stroke:${color};stroke-width:${on ? 2.4 : 1.2}"/>`;
    return `<circle ${at} style="fill:${color}${on ? ";stroke:var(--sheet);stroke-width:1.5" : ""}"/>`;
  };
  const markedSet = new Set(marked), activeSet = new Set(active);
  let bg = "", mid = "", top = "";
  for (const [ref, p] of Object.entries(P.parts)) {
    if (activeSet.has(ref)) top += dot(p, 5.5, "var(--blocker)", true);
    else if (markedSet.has(ref)) mid += dot(p, 3.2, "var(--ink-2)", false);
    else bg += dot(p, 1.6, "var(--rule-strong)", false);
  }
  const first = active.map(r => P.parts[r]).find(Boolean);
  let text = "";
  if (first) {
    const lw = 7 * label.length, px = X(first[0]), py = Y(first[1]);
    const tx = px + 9 + lw < W - 4 ? px + 9 : px - 9 - lw;
    const ty = py - 8 > 12 ? py - 8 : py + 17;
    text = `<text x="${Math.max(4, tx).toFixed(1)}" y="${ty.toFixed(1)}" font-size="11" style="fill:var(--ink);font-family:var(--f-mono);paint-order:stroke;stroke:var(--board);stroke-width:3">${esc(label)}</text>`;
  }
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Board map with ${esc(label)} marked"><rect x="2" y="2" width="${W - 4}" height="${H - 4}" rx="6" style="fill:var(--board);stroke:var(--board-edge);stroke-width:1.2"/>${bg}${mid}${top}${text}</svg>`;
}

function showPointer(fid, idx, btn) {
  const panel = document.getElementById("p-" + fid);
  const open = btn.getAttribute("aria-expanded") === "true";
  document.querySelectorAll(`.part[data-f="${CSS.escape(fid)}"]`).forEach(b => b.setAttribute("aria-expanded", "false"));
  if (open) { panel.hidden = true; return; }
  btn.setAttribute("aria-expanded", "true");
  const chips = DATA.pointers[fid] || [];
  const c = chips[idx];
  if (!c) return;
  const all = chips.flatMap(x => x.refs);
  const rows = c.dl.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("");
  const map = minimap(all, c.refs, c.label);
  const cap = DATA.place ? `<span class="cap">${esc(DATA.place.caption)} Rings are bottom-side parts.</span>` : "";
  panel.innerHTML = `<dl>${rows}</dl>` + (map ? `<div class="minimap">${map}${cap}</div>` : `<div class="minimap"><span class="cap">${esc(DATA.placeNote || "No placement data.")}</span></div>`) +
    `<div class="acts"><button class="btn" type="button" data-copy="${esc(all.join(" "))}">Copy designators</button><span class="small">Paste into Altium's Find Component or KiCad's search, or ask the agent to cross-probe ${esc(fid)}.</span></div>`;
  panel.hidden = false;
}

function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast"; t.setAttribute("role", "status"); t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2200);
}

function exportText() {
  const items = {};
  for (const id of FIDS.concat(BIDS)) {
    const s = stateOf(id);
    if (Object.keys(s).length) items[id] = s;
  }
  return JSON.stringify({ board: DATA.board, revision: DATA.revision, findings_hash: DATA.hash, exported_at: new Date().toISOString(), items }, null, 1);
}

function saveBlob(name, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

document.addEventListener("change", e => {
  const t = e.target;
  if (t.classList && t.classList.contains("check")) setDone(t.dataset.id, t.checked);
});
document.addEventListener("click", e => {
  const t = e.target.closest("button");
  if (!t) return;
  if (t.dataset.more) {
    const d = document.getElementById("d-" + t.dataset.more);
    d.hidden = !d.hidden;
    t.setAttribute("aria-expanded", String(!d.hidden));
    t.textContent = d.hidden ? "More" : "Less";
  } else if (t.dataset.p !== undefined) showPointer(t.dataset.f, Number(t.dataset.p), t);
  else if (t.dataset.copy !== undefined) {
    const txt = t.dataset.copy;
    if (navigator.clipboard) navigator.clipboard.writeText(txt).then(() => toast("Copied " + txt)).catch(() => toast(txt));
    else toast(txt);
  } else if (t.id === "br-export") exportStatus();
});
