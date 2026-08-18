"""Export service: convert query results to CSV/JSON file content."""

import csv
import io
import json
from datetime import date, datetime
from typing import Any

from app.models.schemas import QueryResult

# Supported export formats mapped to their MIME types
SUPPORTED_FORMATS: dict[str, str] = {
    "csv": "text/csv",
    "json": "application/json",
}


def _cell_value(value: Any) -> Any:
    """Normalize a single cell value for serialization."""
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def result_to_csv(result: QueryResult) -> str:
    """
    Format a query result as CSV.

    Column order follows result.columns; nulls become empty strings,
    datetimes become ISO-8601 strings. Quote/escape rules come from the
    stdlib csv module (quote-minimal, "" escaping).
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    headers = [col.name for col in result.columns]
    writer.writerow(headers)
    for row in result.rows:
        writer.writerow([_cell_value(row.get(header)) for header in headers])

    return buffer.getvalue()


def result_to_json(result: QueryResult) -> str:
    """
    Format a query result as a JSON array of row objects.

    Datetime/date values are serialized as ISO-8601 strings. Non-ASCII
    characters are kept as-is (ensure_ascii=False).
    """
    return json.dumps(
        [_json_safe_row(row) for row in result.rows],
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def _json_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert datetime values in a row to ISO strings for stable JSON output."""
    return {
        key: value.isoformat() if isinstance(value, (datetime, date)) else value
        for key, value in row.items()
    }


def build_filename(database_name: str, export_format: str, timestamp: str | None = None) -> str:
    """
    Build the download filename for an export.

    Format: {database_name}_{timestamp}.{ext}, matching the frontend naming
    convention (ISO timestamp with ':' and '.' replaced by '-').
    """
    if timestamp is None:
        timestamp = datetime.now().isoformat(timespec="seconds").replace(":", "-").replace(".", "-")
    return f"{database_name}_{timestamp}.{export_format}"


def format_result(result: QueryResult, export_format: str) -> str:
    """Format a query result in the requested export format."""
    if export_format not in SUPPORTED_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_FORMATS))
        raise ValueError(f"Unsupported export format '{export_format}'. Supported: {supported}")
    if export_format == "csv":
        return result_to_csv(result)
    return result_to_json(result)
