// Teacher page (no build step). All sheet text is rendered with textContent, never innerHTML.
// The server is authoritative: the page shows whatever /ws/teacher says is current.

const $ = (id) => document.getElementById(id);

const state = {
  url: "",
  sheetId: null,
  preview: null,
  current: null, // full Activity of the current (DRAFT/OPEN) activity, or null
  mode: "create", // "create" a new activity, or "reimport" into state.current (US3)
  dashboard: null, // latest dashboard.state for state.current (002)
  importAfterClose: false, // teacher chose "Import a new worksheet" under a CLOSED activity
  socket: null,
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
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new ApiError(res.status, data.error);
    if (err.code === "teacher_required") showLock(); // 002 FR-001: unlock first
    throw err;
  }
  return data;
}

// --- Passcode lock (002 FR-001 – FR-003) ------------------------------------------------

function showLock(message = null) {
  $("lock-section").classList.remove("hidden");
  for (const id of ["import-section", "preview-section", "current-section", "dashboard-section"]) {
    $(id).classList.add("hidden");
  }
  if (message) showMessage($("lock-message"), message);
  $("passcode").focus();
}

$("lock-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  hideMessage($("lock-message"));
  try {
    await api("POST", "/api/teacher/session", { passcode: $("passcode").value });
    $("passcode").value = ""; // never kept in the page (FR-004)
    $("lock-section").classList.add("hidden");
    $("import-section").classList.remove("hidden");
    reconnectLive();
  } catch (err) {
    showMessage($("lock-message"), err.message);
  }
});

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
  const path =
    state.mode === "reimport"
      ? `/api/teacher/activities/${state.current.id}/reimport/preview`
      : "/api/teacher/import/preview";
  try {
    renderPreview(await api("POST", path, { url: state.url, sheetId: state.sheetId }));
  } catch (err) {
    if (err.code === "reimport_refused") exitReimport(err.message);
    throw err;
  }
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
  const reimport = state.mode === "reimport" && state.current;
  $("group-count-field").classList.toggle("hidden", Boolean(reimport));
  $("confirm-button").textContent = reimport ? "Replace questions" : "Create DRAFT activity";
  if (p && !p.canConfirm) {
    ok = false;
    hint.textContent = "Fix the errors in the sheet, then refresh the preview.";
  } else if (p && p.totals.warnings > 0 && !$("ack-warnings").checked) {
    ok = false;
    hint.textContent = "Acknowledge the warnings to continue.";
  } else if (p && reimport) {
    const old = state.current.totals;
    hint.textContent =
      `This replaces all ${old.units} questions (${old.slots} slots) of "${state.current.title}" ` +
      `with ${p.totals.units} questions (${p.totals.slots} slots). Phase and group count stay the same.`;
  } else {
    hint.textContent = "";
  }
  $("confirm-button").disabled = !ok;
}

async function confirmReplace() {
  const p = state.preview;
  hideMessage($("confirm-message"));
  if (!window.confirm(`Replace the questions of "${state.current.title}"?`)) return;
  $("confirm-button").disabled = true;
  try {
    const activity = await api("PUT", `/api/teacher/activities/${state.current.id}/questions`, {
      url: state.url,
      sheetId: p.sheetId,
      fingerprint: p.fingerprint,
      acknowledgeWarnings: $("ack-warnings").checked,
    });
    exitReimport();
    showCurrent(activity);
    showMessage($("current-message"), "Questions replaced.", "info");
  } catch (err) {
    if ((err.code === "preview_changed" || err.code === "import_errors") && err.details.preview) {
      renderPreview(err.details.preview);
    }
    if (err.code === "reimport_refused" || err.code === "not_found") {
      exitReimport(err.message);
      return;
    }
    showApiError($("confirm-message"), err);
    if (err.code !== "preview_changed" && err.code !== "import_errors") updateConfirmButton();
  }
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
  if (!activity || !state.current || activity.id !== state.current.id) {
    state.dashboard = null;
    state.importAfterClose = false;
  }
  state.current = activity;
  const hasCurrent = Boolean(activity);
  if (state.mode === "reimport" && (!hasCurrent || activity.phase !== "DRAFT")) {
    exitReimport(hasCurrent ? `Re-import cancelled: the activity is now ${activity.phase}.` : null);
  }
  const reimporting = state.mode === "reimport";
  const closed = hasCurrent && activity.phase === "CLOSED";
  const importing = !hasCurrent || reimporting || (closed && state.importAfterClose);
  $("current-section").classList.toggle("hidden", !hasCurrent || reimporting);
  $("import-section").classList.toggle("hidden", !importing);
  if (!importing) $("preview-section").classList.add("hidden");
  renderDashboard();
  if (!hasCurrent) return;
  $("reimport-button").classList.toggle("hidden", activity.phase !== "DRAFT");
  $("open-button").classList.toggle("hidden", activity.phase !== "DRAFT");
  $("cancel-button").classList.toggle("hidden", activity.phase !== "DRAFT");
  $("end-button").classList.toggle("hidden", activity.phase !== "OPEN");
  $("new-import-button").classList.toggle("hidden", !closed || state.importAfterClose);
  $("current-title").textContent = activity.title;
  const phase = $("current-phase");
  phase.textContent = activity.phase;
  phase.className = `tag ${activity.phase}`;
  $("current-meta").textContent =
    `${activity.groupCount} groups · ${activity.totals.units} questions · ${activity.totals.slots} answer slots · imported ${activity.importedAt}`;
  $("current-units").replaceChildren(...unitRows(activity.units, activity.source.tabTitle));
}

// --- Live dashboard (002 FR-026 – FR-029) ------------------------------------------------

function formatTime(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString(undefined, { hour12: false }) + "." + String(d.getMilliseconds()).padStart(3, "0");
}

function renderDashboard() {
  const d = state.dashboard;
  // Shown in every phase: in DRAFT it lists the groups' members as students join (FR-028).
  const visible = Boolean(d && state.current && d.activityId === state.current.id);
  $("dashboard-section").classList.toggle("hidden", !visible);
  if (!visible) return;
  $("dashboard-title").textContent = d.phase === "CLOSED" ? "Final results (activity closed)" : "Live dashboard";
  $("dashboard-groups").replaceChildren(
    ...d.groups.map((g) =>
      el("div", {}, el("strong", {}, `Group ${g.number}`), ` (${g.memberCount})`, el("div", { class: "muted" }, g.members.join("、") || "—")),
    ),
  );
  $("dashboard-units").replaceChildren(
    ...d.units.map((u) => {
      const head = el("h3", {}, `Question ${u.number}`, " ", kindLabel(u.kind));
      if (u.submissions.length === 0) return el("div", { class: "dash-unit" }, head, el("p", { class: "muted" }, "No submissions yet"));
      const rows = u.submissions.map((s) =>
        el(
          "tr",
          {},
          el("td", {}, s.isWinner ? el("span", { class: "tag winner" }, `#${s.rank} winner`) : `#${s.rank}`),
          el("td", {}, `Group ${s.groupNumber}`),
          el("td", {}, s.submittedBy),
          el("td", {}, s.answers.map((a) => (u.kind === "GROUP_SET" ? `（${a.subPart}）` : "") + a.text).join("  ")),
          el("td", {}, formatTime(s.receivedAt)),
        ),
      );
      return el(
        "div",
        { class: "dash-unit" },
        head,
        el("table", {}, el("thead", {}, el("tr", {}, ...["Rank", "Group", "Submitted by", "Answer", "Received"].map((h) => el("th", {}, h)))), el("tbody", {}, ...rows)),
      );
    }),
  );
}

async function phaseAction(button, method, path, question) {
  if (!window.confirm(question)) return; // FR-007: these actions cannot be undone
  hideMessage($("current-message"));
  button.disabled = true;
  try {
    const activity = await api(method, path);
    if (activity) showCurrent(activity); // pushes will follow; the server stays authoritative
  } catch (err) {
    showApiError($("current-message"), err);
  } finally {
    button.disabled = false;
  }
}

$("open-button").addEventListener("click", (ev) =>
  phaseAction(ev.target, "POST", `/api/teacher/activities/${state.current.id}/open`,
    `Open "${state.current.title}" for students now? This cannot be undone: questions can no longer be re-imported.`),
);
$("end-button").addEventListener("click", (ev) =>
  phaseAction(ev.target, "POST", `/api/teacher/activities/${state.current.id}/end`,
    `End "${state.current.title}" now? This cannot be undone: no more answers will be accepted.`),
);
$("cancel-button").addEventListener("click", (ev) =>
  phaseAction(ev.target, "DELETE", `/api/teacher/activities/${state.current.id}`,
    `Cancel "${state.current.title}"? It is deleted with its questions, groups and student memberships. This cannot be undone.`),
);
$("new-import-button").addEventListener("click", () => {
  state.importAfterClose = true;
  showCurrent(state.current);
});

function enterReimport() {
  state.mode = "reimport";
  state.preview = null;
  hideMessage($("current-message"));
  hideMessage($("import-message"));
  $("import-heading").textContent = "Re-import questions";
  $("reimport-note").textContent =
    `Into "${state.current.title}" (DRAFT). Paste the same or another sheet link; nothing changes until you confirm.`;
  $("reimport-note").classList.remove("hidden");
  $("cancel-reimport").classList.remove("hidden");
  $("tab-row").classList.add("hidden");
  $("preview-section").classList.add("hidden");
  $("current-section").classList.add("hidden");
  $("import-section").classList.remove("hidden");
}

function exitReimport(message = null) {
  const was = state.mode === "reimport";
  state.mode = "create";
  state.preview = null;
  $("import-heading").textContent = "Import a Guided Notes worksheet";
  $("reimport-note").classList.add("hidden");
  $("cancel-reimport").classList.add("hidden");
  $("tab-row").classList.add("hidden");
  $("preview-section").classList.add("hidden");
  hideMessage($("import-message"));
  if (was && state.current) {
    $("import-section").classList.add("hidden");
    $("current-section").classList.remove("hidden");
  }
  if (message) showMessage($("current-message"), message);
}

async function onActivityState(summary) {
  if (!summary) {
    showCurrent(null);
    return;
  }
  try {
    const activity = await api("GET", `/api/teacher/activities/${summary.id}`);
    showCurrent(activity);
    if (!state.dashboard || state.dashboard.activityId !== activity.id) {
      api("GET", `/api/teacher/activities/${activity.id}/dashboard`).then(onDashboardState, () => {});
    }
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
    else if (msg.type === "dashboard.state") onDashboardState(msg.dashboard);
  });
  ws.addEventListener("close", (ev) => {
    if (state.socket !== ws) return; // replaced on purpose
    if (ev.code === 4401) {
      // Not unlocked (or the server restarted): wait for the passcode (002 FR-003).
      $("live-status").textContent = "Locked.";
      state.socket = null;
      showLock();
      return;
    }
    $("live-status").textContent = "Live updates disconnected — reconnecting…";
    setTimeout(() => connectLive(Math.min(delay * 2, 10000)), delay);
  });
  state.socket = ws;
}

function reconnectLive() {
  const old = state.socket;
  state.socket = null;
  if (old) old.close();
  connectLive();
}

function onDashboardState(dashboard) {
  state.dashboard = dashboard;
  renderDashboard();
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
  if (state.mode === "reimport") confirmReplace();
  else confirmCreate();
});

$("reimport-button").addEventListener("click", enterReimport);
$("cancel-reimport").addEventListener("click", () => exitReimport());

connectLive();
