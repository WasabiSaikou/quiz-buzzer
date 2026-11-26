"""Parse a pasted Google Sheets link (FR-002, FR-003; research R5).

Called by ActivityService before any adapter call, so an invalid link never reaches Google.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from quizbuzzer.services.sheets_adapter import InvalidSheetUrl

_HOST = "docs.google.com"
# /spreadsheets/d/<id>[/...], optionally with a /u/<n> account segment before /d/.
_PATH = re.compile(r"^/spreadsheets(?:/u/\d+)?/d/([A-Za-z0-9_-]+)(?:/.*)?$")
_GID = re.compile(r"(?:^|[&#?])gid=(\d+)(?:$|&)")

_MESSAGE = (
    "This is not a Google Sheets spreadsheet link. Paste the link from the browser address bar "
    "while the sheet is open (it starts with https://docs.google.com/spreadsheets/d/)."
)


def parse_spreadsheet_url(url: str) -> tuple[str, int | None]:
    """Return (spreadsheet_id, gid or None). Raise InvalidSheetUrl for anything else."""
    if not isinstance(url, str):
        raise InvalidSheetUrl(_MESSAGE)
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or parts.hostname != _HOST:
        raise InvalidSheetUrl(_MESSAGE)
    match = _PATH.match(parts.path)
    if not match:
        raise InvalidSheetUrl(_MESSAGE)
    return match.group(1), _find_gid(parts.query, parts.fragment)


def _find_gid(query: str, fragment: str) -> int | None:
    # The fragment (#gid=) names the tab the teacher was looking at, so it wins over ?gid=.
    for text in (fragment, query):
        m = _GID.search(text)
        if m:
            return int(m.group(1))
    gids = parse_qs(query).get("gid")
    if gids and gids[0].isdigit():
        return int(gids[0])
    return None
