"""Unit tests for the query export API endpoint."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_session
from app.main import app
from app.models.database import ConnectionStatus, DatabaseConnection
from app.models.schemas import QueryColumn, QueryResult
from app.services.sql_validator import SqlValidationError


@pytest.fixture
def test_session():
    """Create an in-memory SQLite session for testing."""

    engine = create_engine(
        "sqlite:///file:test_export_db?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False, "uri": True},
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def client(test_session):
    """Create TestClient with test database session."""

    def get_test_session():
        return test_session

    app.dependency_overrides[get_session] = get_test_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_connection(test_session):
    """Create a sample database connection."""
    conn = DatabaseConnection(
        name="test_db",
        url="postgresql://user:pass@localhost/testdb",
        description="Test database",
        status=ConnectionStatus.ACTIVE,
        last_connected_at=datetime.now(UTC).replace(tzinfo=None),
    )
    test_session.add(conn)
    test_session.commit()
    test_session.refresh(conn)
    return conn


def make_mock_result() -> QueryResult:
    """Build the QueryResult returned by the mocked query service."""
    return QueryResult(
        columns=[
            QueryColumn(name="id", dataType="integer"),
            QueryColumn(name="name", dataType="character varying"),
        ],
        rows=[
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": 'Bob, "The Builder"'},
        ],
        rowCount=2,
        executionTimeMs=25,
        sql="SELECT id, name FROM users",
    )


class TestExportSqlQuery:
    """Test POST /api/v1/dbs/{name}/query/export."""

    @patch("app.api.v1.queries.execute_query_with_service")
    def test_export_csv_success(self, mock_execute, client, sample_connection):
        """CSV export returns an attachment with escaped values."""
        mock_execute.side_effect = AsyncMock(return_value=make_mock_result())

        response = client.post(
            "/api/v1/dbs/test_db/query/export?format=csv",
            json={"sql": "SELECT id, name FROM users"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        assert response.headers["content-disposition"].endswith('.csv"')
        lines = response.text.splitlines()
        assert lines[0] == "id,name"
        assert lines[1] == "1,Alice"
        assert lines[2] == '2,"Bob, ""The Builder"""'

    @patch("app.api.v1.queries.execute_query_with_service")
    def test_export_json_success(self, mock_execute, client, sample_connection):
        """JSON export returns an attachment with the rows array."""
        mock_execute.side_effect = AsyncMock(return_value=make_mock_result())

        response = client.post(
            "/api/v1/dbs/test_db/query/export?format=json",
            json={"sql": "SELECT id, name FROM users"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert "attachment" in response.headers["content-disposition"]
        assert response.headers["content-disposition"].endswith('.json"')
        parsed = json.loads(response.text)
        assert parsed == [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": 'Bob, "The Builder"'},
        ]

    @patch("app.api.v1.queries.execute_query_with_service")
    def test_export_defaults_to_csv(self, mock_execute, client, sample_connection):
        """Omitting the format parameter defaults to CSV."""
        mock_execute.side_effect = AsyncMock(return_value=make_mock_result())

        response = client.post(
            "/api/v1/dbs/test_db/query/export",
            json={"sql": "SELECT id, name FROM users"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert response.text.splitlines()[0] == "id,name"

    def test_export_invalid_format_rejected(self, client, sample_connection):
        """Unsupported formats are rejected with 422 by FastAPI validation."""
        response = client.post(
            "/api/v1/dbs/test_db/query/export?format=xml",
            json={"sql": "SELECT 1"},
        )

        assert response.status_code == 422

    def test_export_unknown_database_returns_404(self, client):
        """Exporting from an unknown database returns 404."""
        response = client.post(
            "/api/v1/dbs/unknown_db/query/export?format=csv",
            json={"sql": "SELECT 1"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @patch("app.api.v1.queries.execute_query_with_service")
    def test_export_sql_validation_error_returns_400(self, mock_execute, client, sample_connection):
        """SQL validation failures surface as 400 with the validator message."""
        mock_execute.side_effect = AsyncMock(
            side_effect=SqlValidationError("Only SELECT statements are allowed")
        )

        response = client.post(
            "/api/v1/dbs/test_db/query/export?format=csv",
            json={"sql": "DELETE FROM users"},
        )

        assert response.status_code == 400
        assert "Only SELECT" in response.json()["detail"]

    @patch("app.api.v1.queries.execute_query_with_service")
    def test_export_execution_error_returns_500(self, mock_execute, client, sample_connection):
        """Unexpected execution failures surface as 500."""
        mock_execute.side_effect = AsyncMock(side_effect=RuntimeError("connection refused"))

        response = client.post(
            "/api/v1/dbs/test_db/query/export?format=csv",
            json={"sql": "SELECT * FROM users"},
        )

        assert response.status_code == 500
        assert "Query execution failed" in response.json()["detail"]
