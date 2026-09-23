"""Read the four data tabs from Google Sheets and turn them into row dicts.

Each tab has a title and description above the header row, so tables are
located by header name rather than fixed position. Where a header cell is
blank (a merged group header, e.g. Risks "mitigations"), the cell above it
supplies the name.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

TABS = ("Hazards", "Situations", "Mitigations", "Risks")

# First column of each tab's header row; used to find the header.
KEY_HEADER = {
    "Hazards": "hazard_id",
    "Situations": "situation_id",
    "Mitigations": "mitigation_id",
    "Risks": "risk_id",
}

# Header spellings in the sheet that differ from the model field names.
HEADER_ALIASES = {"situtation": "situation"}

Grid = list[list[str]]


@dataclass
class Row:
    tab: str
    number: int  # 1-based row number as shown in the spreadsheet
    values: dict[str, str]

    def get(self, key: str) -> str:
        return self.values.get(key, "")

    def where(self) -> str:
        ident = self.get(KEY_HEADER[self.tab])
        return f"{self.tab} row {self.number}" + (f" ({ident})" if ident else "")


class SheetFormatError(Exception):
    pass


def _norm(header: str) -> str:
    h = header.strip().lower()
    return HEADER_ALIASES.get(h, h)


def parse_tab(tab: str, grid: Grid) -> list[Row]:
    key = KEY_HEADER[tab]
    header_idx = next(
        (i for i, row in enumerate(grid) if key in (_norm(c) for c in row)), None
    )
    if header_idx is None:
        raise SheetFormatError(f"{tab}: no header row containing '{key}'")

    above = grid[header_idx - 1] if header_idx > 0 else []
    columns: dict[int, str] = {}
    for col, cell in enumerate(grid[header_idx]):
        name = _norm(cell)
        if not name and col < len(above):
            name = _norm(above[col])
        if name:
            columns[col] = name

    rows = []
    for i in range(header_idx + 1, len(grid)):
        cells = grid[i]
        values = {
            name: cells[col].strip() for col, name in columns.items() if col < len(cells)
        }
        rows.append(Row(tab, i + 1, values))
    return rows


def fetch(sheet_key: str, credentials: str | None = None) -> dict[str, Grid]:
    """Pull every tab's raw cell grid (formatted values) from Google Sheets."""
    import gspread

    client = (
        gspread.service_account(filename=credentials)
        if credentials
        else gspread.service_account()
    )
    book = client.open_by_key(sheet_key)
    return {tab: book.worksheet(tab).get_all_values() for tab in TABS}


def save_grids(grids: dict[str, Grid], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(grids, indent=1))


def load_grids(path: Path) -> dict[str, Grid]:
    grids = json.loads(path.read_text())
    missing = [t for t in TABS if t not in grids]
    if missing:
        raise SheetFormatError(f"{path}: missing tabs {', '.join(missing)}")
    return grids
