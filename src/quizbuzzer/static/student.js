// Student page (no build step). The server is authoritative (Principle IV): the page renders the
// latest `student.state` snapshot and nothing else decides the phase. All text is rendered with
// textContent, never innerHTML. Unsent answers stay in this page's memory only (spec Assumptions).

const $ = (id) => document.getElementById(id);
const SCREENS = ["none", "join", "waiting", "answering", "closed"];

const ui = {
  state: null, // latest StudentState from the server
  drafts: {}, // unitId -> { subPart: text } typed but not submitted (this device only)
  unitErrors: {}, // unitId -> message
  extraSubmitted: {}, // unitId -> own submission learned from an already_submitted error
  socket: null,
  retryDelay: 500,
  retryTimer: null,
};

// --- HTTP --------------------------------------------------------------------------------

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
  if (!res.ok) throw new ApiError(res.status, data.error);
  return data;
}

// --- WebSocket with reconnect (research R8: 0.5 s doubling to a 5 s cap) ---------------

function connect() {
  clearTimeout(ui.retryTimer);
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${scheme}://${location.host}/ws/student`);
  ui.socket = ws;
  ws.onopen = () => {
    ui.retryDelay = 500;
    $("conn").classList.add("hidden");
  };
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "student.state") render(msg.state);
  };
  ws.onclose = () => {
    if (ui.socket !== ws) return; // replaced on purpose by reconnectNow()
    $("conn").classList.remove("hidden");
    ui.retryTimer = setTimeout(connect, ui.retryDelay);
    ui.retryDelay = Math.min(ui.retryDelay * 2, 5000);
  };
}

// After join / change group the cookie changed: reopen the socket so the server re-keys it.
function reconnectNow() {
  const old = ui.socket;
  ui.socket = null;
  if (old) old.close();
  connect();
}

// --- Rendering ---------------------------------------------------------------------------

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else node.setAttribute(k, v);
  }
  for (const c of children) node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return node;
}

function showMessage(text, kind = "error") {
  const box = $("message");
  box.textContent = text;
  box.className = `banner ${kind}`;
}

function hideMessage() {
  $("message").className = "banner hidden";
}

function show(screen) {
  for (const s of SCREENS) $(`screen-${s}`).classList.toggle("hidden", s !== screen);
}

function renderMembers(list, members) {
  list.replaceChildren(...members.map((m) => el("li", {}, m)));
}

function answerList(submission, kind) {
  return el(
    "ul",
    { class: "answers" },
    ...submission.answers.map((a) => el("li", {}, (kind === "SINGLE" ? "" : `（${a.subPart}）`) + a.text)),
  );
}

function render(state) {
  ui.state = state;
  const { activity, membership, group } = state;
  renderResults(state.results, membership); // 003: present only for members of a CLOSED activity
  if (!activity) return show("none");
  if (!membership) return renderJoin(activity);
  if (activity.phase === "DRAFT") return renderWaiting(membership, group);
  if (activity.phase === "OPEN") return renderAnswering(activity, membership, group);
  return renderClosed(membership, group);
}

function renderJoin(activity) {
  const select = $("join-group");
  const previous = select.value;
  select.replaceChildren(
    ...Array.from({ length: activity.groupCount }, (_, i) => el("option", { value: i + 1 }, `Group ${i + 1}`)),
  );
  if (previous && Number(previous) <= activity.groupCount) select.value = previous;
  show("join");
}

function renderWaiting(membership, group) {
  $("waiting-group").textContent = membership.groupNumber;
  renderMembers($("waiting-members"), group.members);
  show("waiting");
}

function submittedFor(unitId, group) {
  return group.submissions.find((s) => s.unitId === unitId) || ui.extraSubmitted[unitId] || null;
}

function renderAnswering(activity, membership, group) {
  $("answering-group").textContent = membership.groupNumber;
  renderMembers($("answering-members"), group.members);
  const cards = activity.units.map((unit) => {
    const done = submittedFor(unit.unitId, group);
    const title = el("h3", {}, `Question ${unit.number}` + (unit.kind === "GROUP_SET" ? " (題組)" : ""));
    if (done) {
      // A teammate's (or our own) submission: read-only from now on (US4 AS2).
      delete ui.drafts[unit.unitId];
      return el(
        "div",
        { class: "unit done" },
        title,
        answerList(done, unit.kind),
        el("p", { class: "muted" }, `Submitted by ${done.submittedBy}`),
      );
    }
    return unitForm(unit, title);
  });
  $("units").replaceChildren(...cards);
  show("answering");
}

function unitForm(unit, title) {
  const draft = (ui.drafts[unit.unitId] ||= {});
  const form = el("form", { class: "unit" }, title);
  if (ui.unitErrors[unit.unitId]) form.append(el("div", { class: "banner error" }, ui.unitErrors[unit.unitId]));
  for (const k of unit.subParts) {
    const input = el("input", { type: "text", maxlength: "200", "aria-label": `Question ${unit.number} part ${k}` });
    input.value = draft[k] || "";
    input.addEventListener("input", () => (draft[k] = input.value));
    form.append(el("div", { class: "slot" }, el("span", { class: "k" }, unit.kind === "SINGLE" ? "" : `（${k}）`), input));
  }
  const button = el("button", { class: "primary", type: "submit" }, "Submit for my group");
  form.append(button);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitUnit(unit, button);
  });
  return form;
}

function renderClosed(membership, group) {
  $("closed-group").textContent = membership.groupNumber;
  $("closed-units").replaceChildren(
    ...group.submissions.map((s) =>
      el("div", { class: "unit done" }, el("h3", {}, `Question ${s.unitNumber}`), answerList(s, s.answers.length > 1 ? "GROUP_SET" : "SINGLE")),
    ),
  );
  $("closed-none").classList.toggle("hidden", group.submissions.length > 0);
  show("closed");
}

// --- Results (feature 003; present only once the activity is CLOSED) ---------------------

function answerText(answers, kind) {
  return answers.map((a) => (kind === "SINGLE" ? "" : `（${a.subPart}）`) + a.text).join("\n");
}

function renderResults(results, membership) {
  const box = $("results");
  if (!results) {
    box.classList.add("hidden");
    return;
  }
  const mine = membership?.groupNumber;
  $("results-units").replaceChildren(
    ...results.units.map((unit) => {
      const title = el("h3", {}, `Question ${unit.number}` + (unit.kind === "GROUP_SET" ? " (題組)" : ""));
      if (unit.submissions.length === 0) {
        return el("div", { class: "unit" }, title, el("p", { class: "muted" }, "無人作答"));
      }
      const winner = unit.submissions[0];
      const rows = unit.submissions.map((e) =>
        el(
          "tr",
          { class: e.groupNumber === mine ? "mine" : "" },
          el("td", {}, String(e.rank)),
          el("td", {}, `Group ${e.groupNumber}`),
          el("td", { class: "answer" }, answerText(e.answers, unit.kind)),
        ),
      );
      return el(
        "div",
        { class: "unit" },
        title,
        el(
          "div",
          { class: "winner" },
          el("strong", {}, `Winner: Group ${winner.groupNumber}`),
          el("div", { class: "answer" }, answerText(winner.answers, unit.kind)),
        ),
        el(
          "table",
          { class: "order" },
          el("thead", {}, el("tr", {}, el("th", {}, "Rank"), el("th", {}, "Group"), el("th", {}, "Answer"))),
          el("tbody", {}, ...rows),
        ),
      );
    }),
  );
  box.classList.remove("hidden");
}

// --- Actions -----------------------------------------------------------------------------

$("join-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  hideMessage();
  const activity = ui.state?.activity;
  if (!activity) return;
  $("join-button").disabled = true;
  try {
    const state = await api("POST", "/api/student/join", {
      activityId: activity.id,
      groupNumber: Number($("join-group").value),
      displayName: $("join-name").value,
    });
    render(state);
    reconnectNow();
  } catch (err) {
    if (err.code === "already_joined") reconnectNow();
    else showMessage(err.message);
  } finally {
    $("join-button").disabled = false;
  }
});

$("change-group").addEventListener("click", async () => {
  hideMessage();
  try {
    await api("DELETE", "/api/student/membership");
    reconnectNow();
  } catch (err) {
    showMessage(err.message);
    if (err.code === "not_a_member") reconnectNow();
  }
});

async function submitUnit(unit, button) {
  hideMessage();
  delete ui.unitErrors[unit.unitId];
  const draft = ui.drafts[unit.unitId] || {};
  button.disabled = true;
  try {
    const submission = await api("POST", "/api/student/submissions", {
      unitId: unit.unitId,
      answers: unit.subParts.map((k) => ({ subPart: k, text: draft[k] || "" })),
    });
    ui.extraSubmitted[unit.unitId] = submission;
  } catch (err) {
    if (err.code === "already_submitted" && err.details.submission) {
      ui.extraSubmitted[unit.unitId] = err.details.submission;
      showMessage(err.message, "info");
    } else if (err.code === "not_a_member") {
      showMessage(err.message);
      reconnectNow();
    } else {
      ui.unitErrors[unit.unitId] = err.message;
    }
  } finally {
    button.disabled = false;
    if (ui.state) render(ui.state);
  }
}

connect();
