// Teacher page (no build step). All sheet text is rendered with textContent, never innerHTML.
// The server is authoritative: the page shows whatever /ws/teacher says is current.

const $ = (id) => document.getElementById(id);

const state = {
  url: "",
  sheetId: null,
  preview: null,
  current: null, // full Activity of the current (DRAFT/OPEN) activity, or null
};

// --- HTTP ------------------------------------------------------------------------------

class ApiError extends Error {
  constructor(status, error) {
    super(error?.message || `Request failed (${status})`);
    this.status = status;
    this.code = error?.code || "unknown";
    this.details = error?.details || {};
  }
}

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, data.error);
  return data;
}

// --- Rendering helpers ------------------------------------------------------------------

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else node.setAttribute(k, v);
  }
  for (const c of children) node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return node;
}

function showMessage(box, text, kind = "error", extra = null) {
  box.replaceChildren(document.createTextNode(text));
  if (extra) box.append(document.createElement("br"), extra);
  box.className = `banner ${kind}`;
}

function hideMessage(box) {
  box.className = "banner hidden";
  box.replaceChildren();
}

function showApiError(box, err) {
  if (err.code === "not_shared" && err.details.serviceAccountEmail) {
    showMessage(box, err.message, "error", el("code", {}, err.details.serviceAccountEmail));
  } else {
    showMessage(box, err.message || String(err));
  }
}

function kindLabel(kind) {
  return el("span", { class: kind === "GROUP_SET" ? "tag group" : "tag" }, kind === "GROUP_SET" ? "題組" : "Single");
}

function slotCells(unit, tabTitle) {
  return unit.slots
    .map((s) => (unit.kind === "GROUP_SET" ? `（${s.subPart}）` : "") + `${tabTitle}!${s.a1Ref}`)
    .join("  ");
}

function unitRows(units, tabTitle) {
  return units.map((u) =>
    el("tr", {}, el("td", {}, u.number), el("td", {}, kindLabel(u.kind)), el("td", {}, u.slots.length), el("td", {}, slotCells(u, tabTitle))),
  );
}

// --- Import: tabs + preview -------------------------------------------------------------

async function loadTabs(url) {
  hideMessage($("import-message"));
  $("preview-section").classList.add("hidden");
  const data = await api("POST", "/api/teacher/import/tabs", { url });
  state.url = url;
  const select = $("tab-select");
  select.replaceChildren(...data.tabs.map((t) => el("option", { value: String(t.sheetId) }, t.title)));
  select.value = String(data.preselectedSheetId);
  $("tab-row").classList.remove("hidden");
  await loadPreview(data.preselectedSheetId);
}

async function loadPreview(sheetId) {
  hideMessage($("import-message"));
  state.sheetId = Number(sheetId);
  const preview = await api("POST", "/api/teacher/import/preview", { url: state.url, sheetId: state.sheetId });
  renderPreview(preview);
}

function renderPreview(p) {
  state.preview = p;
  $("preview-title").textContent = `Preview — ${p.spreadsheetTitle ?? ""} / ${p.tabTitle ?? ""}`;
  $("total-units").textContent = p.totals.units;
  $("total-slots").textContent = p.totals.slots;
  $("total-errors").textContent = p.totals.errors;
  $("total-warnings").textContent = p.totals.warnings;

  const issues = [...p.issues].sort((a, b) => (a.severity === b.severity ? 0 : a.severity === "error" ? -1 : 1));
  $("issues").replaceChildren(
    ...issues.map((i) => {
      const where = [i.rows.length ? `Row ${i.rows.join(", ")}` : "", i.cells.length ? `Cell ${i.cells.join(", ")}` : ""]
        .filter(Boolean)
        .join(" · ");
      return el(
        "li",
        { class: i.severity },
        el("strong", {}, i.severity === "error" ? "Error: " : "Warning: "),
        i.message,
        where ? el("div", { class: "where" }, where) : "",
      );
    }),
  );
  $("units").replaceChildren(...unitRows(p.units, p.tabTitle));
  $("preview-section").classList.remove("hidden");
  resetConfirm();
}

// --- Confirm (US2) ------------------------------------------------------------------------

function resetConfirm() {
  const p = state.preview;
  hideMessage($("confirm-message"));
  $("ack-warnings").checked = false;
  $("ack-row").classList.toggle("hidden", !p || p.totals.warnings === 0);
  updateConfirmButton();
}

function updateConfirmButton() {
  const p = state.preview;
  const hint = $("confirm-hint");
  let ok = Boolean(p);
  if (p && !p.canConfirm) {
    ok = false;
    hint.textContent = "Fix the errors in the sheet, then refresh the preview.";
  } else if (p && p.totals.warnings > 0 && !$("ack-warnings").checked) {
    ok = false;
    hint.textContent = "Acknowledge the warnings to continue.";
  } else {
    hint.textContent = "";
  }
  $("confirm-button").disabled = !ok;
}

async function confirmCreate() {
  const p = state.preview;
  const groupCount = Number($("group-count").value);
  hideMessage($("confirm-message"));
  if (!Number.isInteger(groupCount) || groupCount < 2 || groupCount > 12) {
    showMessage($("confirm-message"), "Choose between 2 and 12 groups.");
    return;
  }
  $("confirm-button").disabled = true;
  try {
    const activity = await api("POST", "/api/teacher/activities", {
      url: state.url,
      sheetId: p.sheetId,
      groupCount,
      fingerprint: p.fingerprint,
      acknowledgeWarnings: $("ack-warnings").checked,
    });
    showCurrent(activity); // the WebSocket push will confirm this shortly
  } catch (err) {
    if ((err.code === "preview_changed" || err.code === "import_errors") && err.details.preview) {
      renderPreview(err.details.preview);
    }
    showApiError($("confirm-message"), err);
    if (err.code !== "preview_changed" && err.code !== "import_errors") updateConfirmButton();
  }
}

// --- Current activity (driven by /ws/teacher) ----------------------------------------------

function showCurrent(activity) {
  state.current = activity;
  const hasCurrent = Boolean(activity);
  $("current-section").classList.toggle("hidden", !hasCurrent);
  $("import-section").classList.toggle("hidden", hasCurrent);
  if (hasCurrent) $("preview-section").classList.add("hidden");
  if (!hasCurrent) return;
  $("current-title").textContent = activity.title;
  const phase = $("current-phase");
  phase.textContent = activity.phase;
  phase.className = `tag ${activity.phase}`;
  $("current-meta").textContent =
    `${activity.groupCount} groups · ${activity.totals.units} questions · ${activity.totals.slots} answer slots · imported ${activity.importedAt}`;
  $("current-units").replaceChildren(...unitRows(activity.units, activity.source.tabTitle));
}

async function onActivityState(summary) {
  if (!summary) {
    showCurrent(null);
    return;
  }
  try {
    showCurrent(await api("GET", `/api/teacher/activities/${summary.id}`));
  } catch (err) {
    showApiError($("current-message"), err);
  }
}

function connectLive(delay = 500) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/ws/teacher`);
  ws.addEventListener("open", () => {
    $("live-status").textContent = "Live updates connected.";
    delay = 500;
  });
  ws.addEventListener("message", (ev) => {
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (msg.type === "activity.state") onActivityState(msg.activity);
  });
  ws.addEventListener("close", () => {
    $("live-status").textContent = "Live updates disconnected — reconnecting…";
    setTimeout(() => connectLive(Math.min(delay * 2, 10000)), delay);
  });
}

// --- Wiring -----------------------------------------------------------------------------

$("url-form").addEventListener("submit", (ev) => {
  ev.preventDefault();
  loadTabs($("sheet-url").value.trim()).catch((err) => showApiError($("import-message"), err));
});

$("tab-select").addEventListener("change", (ev) => {
  loadPreview(ev.target.value).catch((err) => showApiError($("import-message"), err));
});

$("refresh-preview").addEventListener("click", () => {
  loadPreview($("tab-select").value).catch((err) => showApiError($("import-message"), err));
});

$("ack-warnings").addEventListener("change", updateConfirmButton);

$("confirm-form").addEventListener("submit", (ev) => {
  ev.preventDefault();
  confirmCreate();
});

connectLive();
