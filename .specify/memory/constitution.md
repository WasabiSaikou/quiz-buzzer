# Quiz Buzzer (課堂搶答系統) Constitution

Quiz Buzzer is a local web application in which a teacher imports a Google Sheets Guided Notes
worksheet, opens a buzz-in activity, and student groups race to submit answers.

## Core Principles

### I. Server-Authoritative Fairness

- The server alone MUST decide submission order, using its own arrival sequence assigned inside a
  single atomic database transaction.
- Client clocks and client-sent timestamps MUST NOT be used for ranking, tie-breaking, or winner
  selection.
- Each question unit MUST have exactly one winner, including under simultaneous submissions; the
  transaction MUST make a second concurrent "winner" impossible, not merely unlikely.

**Rationale**: Students compete for a visible reward. Any reliance on client time or non-atomic
checks lets latency, clock skew, or tampering decide the outcome.

### II. Dynamic Guided Notes Handling (NON-NEGOTIABLE)

- Import and export MUST locate questions and answer cells by reading the sheet's structure:
  header labels 題號 / 作答, numbered rows, and （k） sub-part markers.
- Hardcoded cell addresses, row numbers, or column letters are FORBIDDEN in parser and exporter
  code.
- Every parser or exporter change MUST pass automated tests against at least three differently
  shaped sheets (e.g., different column positions, row offsets, and sub-part layouts).

**Rationale**: Teachers' worksheets vary. A parser tied to one layout silently writes answers into
the wrong cells, which corrupts the teacher's material.

### III. Information Hiding Until Close

- While an activity is not CLOSED, the server MUST NOT send a group any data about other groups'
  submissions — content, timing, count, order, or winner identity — through any channel
  (HTTP responses, real-time pushes, error messages).
- Enforcement MUST be server-side. Hiding data only in the UI does not satisfy this principle.

**Rationale**: Leaked answers or ordering destroy the fairness of the race; browser developer tools
make UI-only hiding trivial to bypass.

### IV. Single Source of Truth for Activity Phase

- The activity phase (DRAFT → OPEN → CLOSED) MUST live on the server; clients MUST NOT infer or
  persist it as authoritative.
- Every phase change MUST be pushed to all connected clients in real time.
- A client that reconnects MUST recover the current phase and its own group's state from the
  server without user intervention.
- Phase transitions MUST be forward-only unless the spec explicitly defines otherwise.

**Rationale**: Divergent views of the phase cause accepted-after-close submissions and disputes
over who answered in time.

### V. Test-First for Core Rules

- Automated tests MUST be written, and observed failing, before implementing: winner selection,
  phase transitions, visibility rules, Sheets parsing, and Sheets export.
- Every core feature MUST also have a manual verification record (date, tester, steps, observed
  result) committed alongside the feature.
- "The AI says it works" is NOT verification; only executed tests and recorded manual checks
  count.

**Rationale**: These rules carry the system's correctness and fairness guarantees; they must be
proven, not asserted.

### VI. Secrets Hygiene

- Credentials, API keys, service-account files, passcodes, and personal data (e.g., student names
  or emails) MUST NOT appear in code, docs, prompts, commits, or logs.
- Configuration MUST come from a gitignored `.env`; a committed `.env.example` MUST contain
  placeholders only.
- Directories holding secrets MUST be gitignored before any secret is placed in them.

**Rationale**: A leaked Google credential or student record cannot be un-published once committed.

### VII. Spec-Code-Diagram Consistency and Simplicity

- Code, spec, plan, tasks, and diagrams MUST agree. A change to any one MUST update the others in
  the same pull request.
- The simplest design that satisfies the spec MUST be preferred; features outside the spec MUST NOT
  be added.
- Every third-party dependency MUST be listed in the README with its license.

**Rationale**: Drift between artifacts makes review meaningless, and unrequested features add risk
without value.

### 原則 VIII：圖表生成 (Diagram Generation)

名稱：PlantUML 設計優先 (Design-First with PlantUML)
規則：
規格制定階段 (Specification Phase)：在 speckit.specify 階段，必須使用 PlantUML 語法生成組件圖 (Component diagram)、類別圖 (Class diagram) 和時序圖 (Sequence diagram)。這些圖表檔案 (.puml) 必須儲存在 ./diagrams/ 目錄中。
產物生成 (Artifact Generation)：檔案建立後，必須使用 PlantUML CLI (java -jar plantuml.jar "./diagrams/*.puml") 將所有 .puml 檔案轉換為 PNG 圖片，且輸出的圖片必須儲存在相同的目錄中。
規劃階段 (Planning Phase)：speckit.plan 階段必須將這些圖表作為主要藍圖，用以生成應用程式的架構與組件。
實作階段 (Implementation Phase)：在 speckit.implement 階段完成程式碼生成後，必須執行驗證步驟，以確保最終的程式碼與圖表完全一致。

**Implementation note**: In this repository the jar lives at `tools/plantuml.jar`, so the command
run is:

```text
java -jar tools/plantuml.jar "./diagrams/*.puml"
```

## Technical Constraints & Security

- Quiz Buzzer runs as a local web application; any network exposure beyond the classroom LAN is
  out of scope unless the spec adds it.
- Submission ordering and winner selection MUST be implemented in the database layer within one
  atomic transaction (Principle I).
- All responses and real-time messages sent to student groups MUST pass through a server-side
  visibility filter keyed on activity phase and requesting group (Principle III).
- Google Sheets access MUST use credentials loaded from `.env` or a gitignored file referenced by
  it (Principle VI).
- Logs MUST NOT contain credentials, passcodes, or student personal data.

## Development Workflow & Quality Gates

- **Spec flow**: `/speckit-specify` (including PlantUML diagrams and PNG generation) →
  `/speckit-plan` (diagrams as the primary blueprint) → `/speckit-tasks` → `/speckit-implement`
  (ending with a code-vs-diagram verification step).
- **Constitution Check**: every plan MUST pass a gate against Principles I–VIII; any deviation MUST
  be recorded with justification in the plan's complexity tracking.
- **Test gate**: a pull request touching winner selection, phase transitions, visibility rules,
  Sheets parsing, or Sheets export MUST include the failing-first tests and pass them in CI or a
  recorded local run.
- **Parser gate**: parser/exporter changes MUST show passing results against ≥ 3 differently shaped
  sheets (Principle II).
- **Consistency gate**: a pull request MUST update spec, plan, tasks, diagrams (.puml and PNG), and
  README dependency list together when any of them is affected (Principle VII).
- **Secrets gate**: reviewers MUST confirm no secrets or personal data appear in the diff.

## Governance

- This constitution overrides all other project practices and guidance. Where a conflict exists,
  the constitution wins.
- Amendments require the agreement of both SpecKit members, a written rationale, and a version bump
  in the same pull request.
- Versioning follows semantic versioning:
  - MAJOR: removal or backward-incompatible redefinition of a principle or governance rule.
  - MINOR: a new principle or section, or materially expanded guidance.
  - PATCH: clarifications, wording, and typo fixes with no semantic change.
- Every pull request MUST be reviewed by the other SpecKit member against these principles before
  merge; the review MUST explicitly note compliance or justified deviations.

**Version**: 1.0.0 | **Ratified**: 2026-11-26 | **Last Amended**: 2026-11-26
