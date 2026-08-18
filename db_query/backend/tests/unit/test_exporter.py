"""Unit tests for the export formatting service."""

from datetime import datetime

import pytest

from app.models.schemas import QueryColumn, QueryResult
from app.services.exporter import (
    SUPPORTED_FORMATS,
    build_filename,
    format_result,
    result_to_csv,
    result_to_json,
)


def make_result(rows, columns=None, sql="SELECT * FROM users") -> QueryResult:
    """Build a QueryResult from rows, inferring columns from the first row if omitted."""
    if columns is None:
        columns = [
            QueryColumn(name=key, dataType="text")
            for key in (rows[0].keys() if rows else [])
        ]
    return QueryResult(
        columns=columns,
        rows=rows,
        rowCount=len(rows),
        executionTimeMs=10,
        sql=sql,
    )


class TestResultToCsv:
    """Test CSV formatting."""

    def test_header_order_follows_columns(self):
        result = make_result(
            rows=[{"b": 2, "a": 1}],
            columns=[
                QueryColumn(name="a", dataType="integer"),
                QueryColumn(name="b", dataType="integer"),
            ],
        )
        lines = result_to_csv(result).splitlines()
        assert lines[0] == "a,b"
        assert lines[1] == "1,2"

    def test_null_becomes_empty_string(self):
        result = make_result(rows=[{"id": 1, "name": None}])
        lines = result_to_csv(result).splitlines()
        assert lines[1] == "1,"

    def test_special_characters_are_escaped(self):
        result = make_result(
            rows=[{"id": 1, "name": 'He said "hi", then left'}]
        )
        lines = result_to_csv(result).splitlines()
        assert lines[1] == '1,"He said ""hi"", then left"'

    def test_newline_in_value_is_quoted(self):
        result = make_result(rows=[{"id": 1, "name": "line1\nline2"}])
        content = result_to_csv(result)
        assert '"line1\nline2"' in content

    def test_datetime_becomes_iso_format(self):
        result = make_result(rows=[{"id": 1, "created_at": datetime(2026, 8, 17, 10, 30, 0)}])
        lines = result_to_csv(result).splitlines()
        assert "2026-08-17T10:30:00" in lines[1]

    def test_chinese_content_kept_as_is(self):
        result = make_result(rows=[{"id": 1, "name": "张三"}])
        assert "张三" in result_to_csv(result)

    def test_empty_result_has_header_only_if_columns_known(self):
        result = make_result(
            rows=[],
            columns=[QueryColumn(name="id", dataType="integer")],
        )
        assert result_to_csv(result).splitlines() == ["id"]


class TestResultToJson:
    """Test JSON formatting."""

    def test_exports_rows_array(self):
        rows = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        result = make_result(rows=rows)
        assert result_to_json(result).splitlines()[0] == "["
        import json

        parsed = json.loads(result_to_json(result))
        assert parsed == rows

    def test_datetime_becomes_iso_string(self):
        result = make_result(rows=[{"id": 1, "created_at": datetime(2026, 8, 17, 10, 30, 0)}])
        import json

        parsed = json.loads(result_to_json(result))
        assert parsed[0]["created_at"] == "2026-08-17T10:30:00"

    def test_non_ascii_not_escaped(self):
        result = make_result(rows=[{"id": 1, "name": "张三"}])
        assert "张三" in result_to_json(result)

    def test_null_preserved_as_null(self):
        result = make_result(rows=[{"id": 1, "name": None}])
        import json

        assert json.loads(result_to_json(result))[0]["name"] is None


class TestFormatResult:
    """Test format dispatch and filename building."""

    def test_dispatches_to_csv(self):
        result = make_result(rows=[{"id": 1}])
        assert format_result(result, "csv").splitlines()[0] == "id"

    def test_dispatches_to_json(self):
        result = make_result(rows=[{"id": 1}])
        assert format_result(result, "json").startswith("[")

    def test_unsupported_format_raises(self):
        result = make_result(rows=[{"id": 1}])
        with pytest.raises(ValueError, match="Unsupported export format"):
            format_result(result, "xml")

    def test_supported_formats_registry(self):
        assert SUPPORTED_FORMATS == {"csv": "text/csv", "json": "application/json"}

    def test_build_filename_format(self):
        filename = build_filename("interview_db", "csv", timestamp="2026-08-17T10-30-00")
        assert filename == "interview_db_2026-08-17T10-30-00.csv"

    def test_build_filename_defaults_to_now(self):
        assert build_filename("db", "json").startswith("db_")
        assert build_filename("db", "json").endswith(".json")
