// Teacher page (no build step). All sheet text is rendered with textContent, never innerHTML.

const $ = (id) => document.getElementById(id);

const state = {
  url: "",
  sheetId: null,
  preview: null,
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

// --- Import: tabs + preview -------------------------------------------------------------

async function loadTabs(url) {
  hideMessage($("import-message"));
  $("preview-section").classList.add("hidden");
  const data = await api("POST", "/api/teacher/import/tabs", { url });
  state.url = url;
  const select = $("tab-select");
  select.replaceChildren(
    ...data.tabs.map((t) => el("option", { value: String(t.sheetId) }, t.title)),
  );
  select.value = String(data.preselectedSheetId);
  $("tab-row").classList.remove("hidden");
  await loadPreview(data.preselectedSheetId);
}

async function loadPreview(sheetId) {
  hideMessage($("import-message"));
  state.sheetId = Number(sheetId);
  const preview = await api("POST", "/api/teacher/import/preview", {
    url: state.url,
    sheetId: state.sheetId,
  });
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
      const where = [
        i.rows.length ? `Row ${i.rows.join(", ")}` : "",
        i.cells.length ? `Cell ${i.cells.join(", ")}` : "",
      ].filter(Boolean).join(" · ");
      return el(
        "li",
        { class: i.severity },
        el("strong", {}, i.severity === "error" ? "Error: " : "Warning: "),
        i.message,
        where ? el("div", { class: "where" }, where) : "",
      );
    }),
  );

  $("units").replaceChildren(
    ...p.units.map((u) =>
      el(
        "tr",
        {},
        el("td", {}, u.number),
        el("td", {}, el("span", { class: u.kind === "GROUP_SET" ? "tag group" : "tag" }, u.kind === "GROUP_SET" ? "題組" : "Single")),
        el("td", {}, u.slots.length),
        el(
          "td",
          {},
          u.slots
            .map((s) => (u.kind === "GROUP_SET" ? `（${s.subPart}）` : "") + `${p.tabTitle}!${s.a1Ref}`)
            .join("  "),
        ),
      ),
    ),
  );
  $("preview-section").classList.remove("hidden");
  onPreviewRendered(p);
}

// Hook for the confirm step (US2).
function onPreviewRendered(_p) {}

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
