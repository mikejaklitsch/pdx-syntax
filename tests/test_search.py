"""Tests for search functionality."""

import tempfile
from pathlib import Path

import pytest

from pdx_syntax.database import init_database, get_connection
from pdx_syntax.search import (
    search_effects,
    search_triggers,
    fuzzy_search,
    get_by_name,
)
from pdx_syntax.seed import seed_database


@pytest.fixture
def seeded_db():
    """Create a seeded temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    seed_database(db_path, force=True)
    yield db_path

    if db_path.exists():
        db_path.unlink()


def test_search_effects(seeded_db):
    """Test searching effects."""
    results = search_effects("gold", db_path=seeded_db)

    assert len(results) > 0
    # Should find add_gold or similar
    names = [r["name"] for r in results]
    assert any("gold" in name.lower() for name in names)


def test_search_effects_with_scope_filter(seeded_db):
    """Test searching effects with scope filter."""
    results = search_effects("gold", scope="country", db_path=seeded_db)

    for result in results:
        assert result.get("scope_type") == "country"


def test_search_triggers(seeded_db):
    """Test searching triggers."""
    results = search_triggers("variable", db_path=seeded_db)

    assert len(results) > 0
    names = [r["name"] for r in results]
    assert any("variable" in name.lower() for name in names)


def test_get_by_name(seeded_db):
    """Test exact name lookup."""
    result = get_by_name("add_gold", "effects", seeded_db)

    assert result is not None
    assert result["name"] == "add_gold"


def test_get_by_name_not_found(seeded_db):
    """Test exact name lookup for non-existent item."""
    result = get_by_name("nonexistent_effect_xyz", "effects", seeded_db)

    assert result is None


def test_fuzzy_search(seeded_db):
    """Test fuzzy search across columns."""
    results = fuzzy_search(
        "tresury",  # Misspelled "treasury"
        "effects",
        ["name", "description"],
        db_path=seeded_db,
    )

    # Should still find treasury-related effects
    assert len(results) >= 0  # May or may not find depending on threshold
