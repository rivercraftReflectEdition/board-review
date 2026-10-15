let db = null, user = null, me = null, downloads = null;
let docs = {};

function withDocs() {
  const out = {};
  for (const id of FIDS.concat(BIDS)) out[id] = { ...(DATA.status[id] || {}), ...(docs[id] || {}) };
  return out;
}

async function setDone(id, done) {
  const prev = stateOf(id);
  const patch = { done, at: new Date().toISOString() };
  if (me) patch.by = me;
  if (!db) {
    local = { ...local, [id]: patch };
    saveLocal();
    status = withLocal(DATA.status);
    refreshStatus();
    return;
  }
  status = { ...status, [id]: { ...prev, ...patch } };
  refreshStatus();
  try {
    const ref = db.doc("status/" + id);
    if (docs[id]) await ref.update(patch);
    else await ref.set({ ...(DATA.status[id] || {}), ...patch });
  } catch (e) {
    if (e && e.code === "invalid_argument") {
      canWrite = false; status = { ...status, [id]: prev }; refreshStatus();
      toast("You can view this review but not mark items.");
    } else toast("Could not save. Try again.");
  }
}

async function exportStatus() {
  const text = exportText();
  if (downloads) {
    try { await downloads.save({ filename: "status.json", data: text }); toast("Saved status.json."); return; }
    catch (e) { if (e && e.code === "declined") return; }
  }
  try { saveBlob("status.json", text); }
  catch (e) {
    if (navigator.clipboard) navigator.clipboard.writeText(text).then(() => toast("Copied the status JSON.")).catch(() => toast("Export is not available here."));
  }
}

async function resolveNames() {
  if (!user) return;
  const ids = [...new Set(Object.values(status).map(s => s.by).filter(Boolean))].filter(i => !(i in names));
  if (!ids.length) return;
  try {
    const ps = await user.profiles(ids);
    for (const i of ids) names[i] = (ps[i] && ps[i].name) || "Someone";
    refreshStatus();
  } catch (e) {}
}

function useLocal() {
  canWrite = true;
  local = loadLocal();
  status = withLocal(DATA.status);
  saveNote("Checkmarks are saved in this browser only. Export status to hand them to the next review.");
  refreshStatus();
}

async function connect() {
  if (!window.claude || !window.claude.use) { useLocal(); return; }
  const [d, u, dl] = await Promise.all([window.claude.use("db"), window.claude.use("user"), window.claude.use("downloads")]);
  db = d; user = u; downloads = dl;
  if (!db) { useLocal(); return; }
  canWrite = true;
  if (user) {
    try { me = await user.id(); } catch (e) {}
    try { const w = await user.can("data.write"); if (w === false) canWrite = false; } catch (e) {}
  }
  saveNote(canWrite ? "Checkmarks are saved with this page and shared with everyone who opens it." : "View only. Ask the owner for Contributor access to mark items.");
  db.collection("status").onSnapshot(snap => {
    const next = {};
    snap.docs.forEach(doc => { if (doc.exists) next[doc.id] = doc.data(); });
    docs = next; status = withDocs(); refreshStatus(); resolveNames();
  }, () => saveNote("Saving is unavailable right now."));
}

canWrite = false;
status = withDocs();
refreshStatus();
connect();
