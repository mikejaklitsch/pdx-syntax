"""Tests for database functionality."""

import tempfile
from pathlib import Path

import pytest

from pdx_syntax.database import init_database, get_connection, record_data_source


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


def test_init_database(temp_db):
    """Test database initialization."""
    init_database(temp_db)

    conn = get_connection(temp_db)
    cursor = conn.cursor()

    # Check tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}

    expected = {
        "schema_version",
        "data_sources",
        "game_versions",
        "scope_types",
        "effects",
        "triggers",
        "scopes",
        "modifiers",
        "on_actions",
        "defines",
        "localization_patterns",
        "syntax_templates",
        "change_log",
    }

    assert expected.issubset(tables)
    conn.close()


def test_record_data_source(temp_db):
    """Test recording a data source."""
    init_database(temp_db)

    source_id = record_data_source(
        url="https://example.com/test",
        source_type="test",
        game_version="1.0.0",
        db_path=temp_db,
    )

    assert source_id is not None
    assert source_id > 0

    conn = get_connection(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM data_sources WHERE id = ?", (source_id,))
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row["url"] == "https://example.com/test"
    assert row["source_type"] == "test"
    assert row["game_version"] == "1.0.0"
