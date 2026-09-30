import csv
import io

from .contracts import Cell, DatasetMetadata, ManualDataset, Row, number
from .errors import Problem


def parse_csv(content: bytes, metadata: DatasetMetadata) -> ManualDataset:
    if len(content) > 1048576:
        raise Problem("PAYLOAD_TOO_LARGE", "CSV files must be 1 MiB or smaller.", 413)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Problem("CSV_ENCODING_INVALID", "Save the CSV using UTF-8 encoding.", 400) from None
    if "\x00" in text:
        raise Problem("CSV_SYNTAX_INVALID", "CSV files cannot contain null bytes.", 400)
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error:
        raise Problem("CSV_SYNTAX_INVALID", "Check the CSV quoting and comma delimiters.", 400) from None
    while rows and not rows[-1]:
        rows.pop()
    if not rows or len(rows[0]) != 2 or len(set(rows[0])) != 2:
        raise Problem("CSV_SCHEMA_INVALID", "Use two distinct column headers.")
    by_position = sorted(metadata.columns, key=lambda c: c.position)
    if rows[0] != [c.name for c in by_position]:
        raise Problem(
            "CSV_SCHEMA_INVALID",
            "CSV headers must exactly match the two variable names in their selected positions.",
        )
    if not 2 <= len(rows) - 1 <= 5000:
        raise Problem("CSV_SCHEMA_INVALID", "Include 2–5,000 measurements.")
    xindex = next(c.position for c in metadata.columns if c.role == "independent")
    points = []
    for index, row in enumerate(rows[1:]):
        if len(row) != 2:
            raise Problem("CSV_SCHEMA_INVALID", f"Data row {index + 1} must have exactly two cells.")
        try:
            cells = [Cell(raw=cell.strip(), value=number(cell.strip())) for cell in row]
        except Problem as exc:
            raise Problem(exc.code, f"Data row {index + 1}: {exc.message}") from None
        points.append(Row(x=cells[xindex], y=cells[1 - xindex]))
    return ManualDataset(**metadata.model_dump(), rows=points)
