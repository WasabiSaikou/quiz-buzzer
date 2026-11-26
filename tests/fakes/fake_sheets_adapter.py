"""FakeSheetsAdapter: an in-memory SheetsAdapter fed from tests/fixtures/sheets/ (research R9).

Formats:
- ``*.json``: ``{spreadsheetId, title, tabs: [{sheetId, title, index, grid, merges}]}``
- ``*.csv``: one single-tab spreadsheet; spreadsheetId = title = file stem, tab sheetId 0,
  title "Sheet1", index 0, no merges (CSV cannot carry merges).

``*.expected.json`` files hold hand-written expected parse results and are not loaded.
Returned data is always a deep copy, so callers can never modify the stored fixtures (FR-005).
"""

from __future__ import annotations

import copy
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

import re
from collections.abc import Sequence

from quizbuzzer.models import CellWrite, Merge, SpreadsheetInfo, TabData, TabInfo
from quizbuzzer.services.sheets_adapter import SheetNotFound, SheetReadOnly

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "sheets"
FAKE_SERVICE_ACCOUNT_EMAIL = "quiz-buzzer-test@example-project.iam.gserviceaccount.com"


@dataclass
class _Tab:
    sheet_id: int
    title: str
    index: int
    grid: list[list[str]]
    merges: list[Merge] = field(default_factory=list)


@dataclass
class _Spreadsheet:
    spreadsheet_id: str
    title: str
    tabs: list[_Tab]


class FakeSheetsAdapter:
    """Implements quizbuzzer.services.sheets_adapter.SheetsAdapter without network access."""

    def __init__(
        self,
        fixtures_dir: Path | None = FIXTURES_DIR,
        service_account_email: str = FAKE_SERVICE_ACCOUNT_EMAIL,
    ) -> None:
        self._email = service_account_email
        self._sheets: dict[str, _Spreadsheet] = {}
        self._failure: Exception | None = None
        self.calls: list[tuple[str, tuple]] = []
        # Feature 003: the fake is also a SheetsWriter (003 research R9).
        self.writes: list[tuple[str, int, str, tuple[CellWrite, ...]]] = []
        self._read_only: set[str] = set()
        if fixtures_dir is not None:
            self.load_dir(fixtures_dir)

    # --- SheetsAdapter -------------------------------------------------------------

    @property
    def service_account_email(self) -> str:
        return self._email

    def list_tabs(self, spreadsheet_id: str) -> SpreadsheetInfo:
        self.calls.append(("list_tabs", (spreadsheet_id,)))
        sheet = self._get(spreadsheet_id)
        return SpreadsheetInfo(
            spreadsheet_id=sheet.spreadsheet_id,
            title=sheet.title,
            tabs=tuple(
                TabInfo(sheet_id=t.sheet_id, title=t.title, index=t.index)
                for t in sorted(sheet.tabs, key=lambda t: t.index)
            ),
        )

    def read_tab(self, spreadsheet_id: str, sheet_id: int) -> TabData:
        self.calls.append(("read_tab", (spreadsheet_id, sheet_id)))
        sheet = self._get(spreadsheet_id)
        for tab in sheet.tabs:
            if tab.sheet_id == sheet_id:
                return TabData(
                    spreadsheet_id=sheet.spreadsheet_id,
                    spreadsheet_title=sheet.title,
                    sheet_id=tab.sheet_id,
                    title=tab.title,
                    grid=copy.deepcopy(tab.grid),
                    merges=list(tab.merges),
                )
        raise SheetNotFound(f"No tab with id {sheet_id} in spreadsheet {spreadsheet_id}.")

    # --- SheetsWriter (feature 003) ---------------------------------------------------

    def write_cells(
        self, spreadsheet_id: str, sheet_id: int, tab_title: str, cells: Sequence[CellWrite]
    ) -> int:
        """Store each text verbatim (like RAW) in the tab found by sheet_id; one log entry per call.

        Checks everything before changing anything, so a refused write leaves the grid intact.
        """
        self.calls.append(("write_cells", (spreadsheet_id, sheet_id, tab_title, len(cells))))
        sheet = self._get(spreadsheet_id)
        if spreadsheet_id in self._read_only:
            raise SheetReadOnly(self._email)
        tab = next((t for t in sheet.tabs if t.sheet_id == sheet_id), None)
        if tab is None:
            raise SheetNotFound(f"No tab with id {sheet_id} in spreadsheet {spreadsheet_id}.")
        targets = [(_a1_to_index(c.a1_ref), c.text) for c in cells]
        for (r, col), text in targets:
            while len(tab.grid) <= r:
                tab.grid.append([])
            row = tab.grid[r]
            while len(row) <= col:
                row.append("")
            row[col] = text
        self.writes.append((spreadsheet_id, sheet_id, tab_title, tuple(cells)))
        return len(cells)

    def make_read_only(self, spreadsheet_id: str) -> None:
        """Simulate a Viewer share: reads work, write_cells raises SheetReadOnly."""
        self._read_only.add(spreadsheet_id)

    def rename_tab(self, spreadsheet_id: str, sheet_id: int, title: str) -> None:
        for tab in self._sheets[spreadsheet_id].tabs:
            if tab.sheet_id == sheet_id:
                tab.title = title
                return
        raise KeyError(sheet_id)

    def delete_tab(self, spreadsheet_id: str, sheet_id: int) -> None:
        self._sheets[spreadsheet_id].tabs = [
            t for t in self._sheets[spreadsheet_id].tabs if t.sheet_id != sheet_id
        ]

    # --- Test controls ---------------------------------------------------------------

    def fail_with(self, exc: Exception | None) -> None:
        """Make every following adapter call raise ``exc`` (None clears it)."""
        self._failure = exc

    def add_spreadsheet(
        self, spreadsheet_id: str, title: str, tabs: list[dict]
    ) -> None:
        """Add a spreadsheet from dicts shaped like the JSON fixture tabs."""
        self._sheets[spreadsheet_id] = _Spreadsheet(
            spreadsheet_id=spreadsheet_id,
            title=title,
            tabs=[_tab_from_dict(t) for t in tabs],
        )

    def replace_tab(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        grid: list[list[str]],
        merges: list[Merge] | None = None,
    ) -> None:
        """Change a tab's contents, e.g. to simulate an edit between preview and confirm."""
        for tab in self._sheets[spreadsheet_id].tabs:
            if tab.sheet_id == sheet_id:
                tab.grid = copy.deepcopy(grid)
                tab.merges = [tuple(m) for m in (merges or [])]
                return
        raise KeyError(sheet_id)

    def snapshot(self) -> dict[str, list[tuple[int, list[list[str]], list[Merge]]]]:
        """Deep copy of all stored grids and merges, for read-only (FR-005) assertions."""
        return {
            sid: [(t.sheet_id, copy.deepcopy(t.grid), list(t.merges)) for t in s.tabs]
            for sid, s in self._sheets.items()
        }

    @property
    def spreadsheet_ids(self) -> list[str]:
        return sorted(self._sheets)

    # --- Loading ---------------------------------------------------------------------

    def load_dir(self, directory: Path) -> None:
        for path in sorted(Path(directory).iterdir()):
            if path.name.endswith(".expected.json") or not path.is_file():
                continue
            if path.suffix == ".json":
                self.load_json(path)
            elif path.suffix == ".csv":
                self.load_csv(path)

    def load_json(self, path: Path) -> None:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.add_spreadsheet(data["spreadsheetId"], data["title"], data["tabs"])

    def load_csv(self, path: Path) -> None:
        path = Path(path)
        with path.open(encoding="utf-8-sig", newline="") as f:
            grid = [list(row) for row in csv.reader(f)]
        self.add_spreadsheet(
            path.stem,
            path.stem,
            [{"sheetId": 0, "title": "Sheet1", "index": 0, "grid": grid, "merges": []}],
        )

    def _get(self, spreadsheet_id: str) -> _Spreadsheet:
        if self._failure is not None:
            raise self._failure
        try:
            return self._sheets[spreadsheet_id]
        except KeyError:
            raise SheetNotFound(f"Spreadsheet {spreadsheet_id} not found.") from None


_A1 = re.compile(r"^([A-Z]+)([0-9]+)$")


def _a1_to_index(a1: str) -> tuple[int, int]:
    """'B7' -> (6, 1): 0-based (row, column)."""
    m = _A1.match(a1)
    if m is None:
        raise ValueError(f"not an A1 cell reference: {a1!r}")
    col = 0
    for ch in m.group(1):
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return int(m.group(2)) - 1, col - 1


def _tab_from_dict(t: dict) -> _Tab:
    return _Tab(
        sheet_id=int(t["sheetId"]),
        title=str(t["title"]),
        index=int(t.get("index", 0)),
        grid=[[("" if c is None else str(c)) for c in row] for row in t.get("grid", [])],
        merges=[tuple(int(x) for x in m) for m in t.get("merges", [])],
    )
