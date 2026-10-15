function setDone(id, done) {
  local = { ...local, [id]: { done, at: new Date().toISOString() } };
  saveLocal();
  status = withLocal(DATA.status);
  refreshStatus();
}

function exportStatus() {
  saveBlob("status.json", exportText());
  toast("Saved status.json. Pass it to the report with --status.");
}

local = loadLocal();
status = withLocal(DATA.status);
saveNote("Checkmarks are saved in this browser only. Export status to hand them to the next review.");
refreshStatus();
