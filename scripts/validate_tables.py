#!/usr/bin/env python3
"""Validate the project-specific structure of the implementation tables."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path


STATUS_CLASSES = {"success", "warning", "danger", "info"}


@dataclass
class Cell:
    tag: str
    line: int
    attributes: dict[str, str]
    text_parts: list[str] = field(default_factory=list)
    links: list[str | None] = field(default_factory=list)
    check_icons: int = 0
    span_balance: int = 0

    @property
    def text(self) -> str:
        return " ".join("".join(self.text_parts).split())

    @property
    def classes(self) -> set[str]:
        return set(self.attributes.get("class", "").split())


@dataclass
class Row:
    line: int
    in_header: bool
    cells: list[Cell] = field(default_factory=list)


@dataclass
class Table:
    line: int
    classes: set[str]
    rows: list[Row] = field(default_factory=list)


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[Table] = []
        self.errors: list[str] = []
        self.table: Table | None = None
        self.row: Row | None = None
        self.cell: Cell | None = None
        self.in_header = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value or "" for name, value in attrs}
        line = self.getpos()[0]

        if tag == "table":
            if self.table is not None:
                self.errors.append(f"line {line}: nested tables are not supported")
                return
            self.table = Table(line, set(attributes.get("class", "").split()))
        elif tag == "thead" and self.table is not None:
            self.in_header = True
        elif tag == "tr" and self.table is not None:
            if self.row is not None:
                self.errors.append(f"line {line}: nested <tr> inside row from line {self.row.line}")
            self.row = Row(line, self.in_header)
        elif tag in {"th", "td"} and self.row is not None:
            if self.cell is not None:
                self.errors.append(
                    f"line {line}: <{tag}> is nested inside <{self.cell.tag}> "
                    f"from line {self.cell.line}"
                )
            self.cell = Cell(tag, line, attributes)
            self.row.cells.append(self.cell)
        elif self.cell is not None:
            if tag == "a":
                self.cell.links.append(attributes.get("href"))
            elif tag == "span":
                self.cell.span_balance += 1
                classes = set(attributes.get("class", "").split())
                if {"glyphicon", "glyphicon-ok"} <= classes:
                    self.cell.check_icons += 1

    def handle_endtag(self, tag: str) -> None:
        line = self.getpos()[0]

        if tag in {"th", "td"} and self.row is not None:
            if self.cell is None:
                self.errors.append(f"line {line}: closing </{tag}> has no open table cell")
            elif self.cell.tag != tag:
                self.errors.append(
                    f"line {line}: closing </{tag}> does not match <{self.cell.tag}> "
                    f"from line {self.cell.line}"
                )
                self.cell = None
            else:
                self.cell = None
        elif tag == "span" and self.cell is not None:
            self.cell.span_balance -= 1
        elif tag == "tr" and self.table is not None:
            if self.row is not None:
                if self.cell is not None:
                    self.errors.append(
                        f"line {line}: row closes before <{self.cell.tag}> "
                        f"from line {self.cell.line}"
                    )
                    self.cell = None
                self.table.rows.append(self.row)
                self.row = None
        elif tag == "thead" and self.table is not None:
            self.in_header = False
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.text_parts.append(data)


TABLES = {
    "language servers": [
        "Language",
        "Maintainer",
        "Repository",
        "Code completion",
        "Hover",
        "Jump to def",
        "Workspace symbols",
        "Find references",
        "Diagnostics",
        "Additional capabilities",
    ],
    "LSP clients": [
        "Editor/client",
        "Maintainer",
        "Repository",
        "Code completion",
        "Hover",
        "Jump to def",
        "Find references",
        "Symbol search",
        "Diagnostics",
    ],
}


def validate_table(name: str, table: Table, headers: list[str]) -> list[str]:
    errors: list[str] = []
    width = len(headers)
    header_rows = [row for row in table.rows if row.in_header]
    body_rows = [row for row in table.rows if not row.in_header]

    if table.classes != {"table", "table-striped", "sticky-header"}:
        errors.append(
            f"line {table.line}: {name} table must have classes "
            "'table table-striped sticky-header'"
        )

    if len(header_rows) != 1:
        errors.append(f"line {table.line}: {name} must have exactly one header row")
    elif [cell.text for cell in header_rows[0].cells] != headers:
        errors.append(f"line {header_rows[0].line}: {name} headers do not match the required layout")
    elif any(cell.tag != "th" for cell in header_rows[0].cells):
        errors.append(f"line {header_rows[0].line}: every {name} header cell must be <th>")

    section_rows = 0
    entry_rows = 0
    for row in body_rows:
        if len(row.cells) == 1 and row.cells[0].attributes.get("colspan"):
            section_rows += 1
            cell = row.cells[0]
            if cell.tag != "th" or cell.attributes.get("colspan") != str(width):
                errors.append(f"line {row.line}: section row must span all {width} columns")
            if cell.text.lower() != "work in progress":
                errors.append(f"line {row.line}: unexpected section row {cell.text!r}")
            continue

        entry_rows += 1
        if len(row.cells) != width:
            errors.append(
                f"line {row.line}: {name} entry has {len(row.cells)} cells; expected {width}"
            )
            continue

        expected_tags = ["th"] + ["td"] * (width - 1)
        actual_tags = [cell.tag for cell in row.cells]
        if actual_tags != expected_tags:
            errors.append(
                f"line {row.line}: {name} entry cells must be one <th> followed by "
                f"{width - 1} <td> cells"
            )

        for cell in row.cells:
            if cell.span_balance != 0:
                errors.append(f"line {cell.line}: unbalanced <span> in table cell")
            if any(not href for href in cell.links):
                errors.append(f"line {cell.line}: link is missing an href")

        if not row.cells[0].text:
            errors.append(f"line {row.line}: entry name must not be empty")
        if not row.cells[1].text:
            errors.append(f"line {row.line}: maintainer must not be empty")
        if "repo" not in row.cells[2].classes:
            errors.append(f"line {row.cells[2].line}: repository cell must have class 'repo'")
        if not row.cells[2].links:
            errors.append(f"line {row.cells[2].line}: repository cell must contain a link")

        for cell in row.cells[3:9]:
            statuses = cell.classes & STATUS_CLASSES
            if len(statuses) != 1 or cell.classes != statuses:
                errors.append(
                    f"line {cell.line}: capability cell must have exactly one status class: "
                    f"{', '.join(sorted(STATUS_CLASSES))}"
                )
                continue
            status = next(iter(statuses))
            expected_icons = 1 if status == "success" else 0
            if cell.check_icons != expected_icons:
                errors.append(
                    f"line {cell.line}: {status} capability cell has {cell.check_icons} check "
                    f"icons; expected {expected_icons}"
                )
            if cell.text:
                errors.append(f"line {cell.line}: capability cell must not contain text")

    if section_rows != 1:
        errors.append(
            f"line {table.line}: {name} must have exactly one Work in Progress section row"
        )
    if entry_rows == 0:
        errors.append(f"line {table.line}: {name} has no entries")

    return errors


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("index.html")
    parser = TableParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()

    errors = parser.errors
    validated: list[tuple[str, int]] = []
    for name, headers in TABLES.items():
        matches = [
            table
            for table in parser.tables
            if table.rows
            and table.rows[0].in_header
            and table.rows[0].cells
            and table.rows[0].cells[0].text == headers[0]
        ]
        if len(matches) != 1:
            errors.append(f"{name}: expected one matching table, found {len(matches)}")
            continue
        table = matches[0]
        errors.extend(validate_table(name, table, headers))
        entries = sum(
            1
            for row in table.rows
            if not row.in_header and not (len(row.cells) == 1 and row.cells[0].attributes.get("colspan"))
        )
        validated.append((name, entries))

    if errors:
        print(f"{path}: table validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    details = ", ".join(f"{count} {name}" for name, count in validated)
    print(f"{path}: table layout is valid ({details})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
