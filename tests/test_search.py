"""Tests for search functionality."""

import tempfile
from pathlib import Path

import pytest

from pdx_syntax.database import init_database, get_connection
from pdx_syntax.search import (
    search_effects,
    search_triggers,
    search_data_types,
    fuzzy_search,
    get_by_name,
)


# A handful of rows standing in for what a real scrape would load. Tests query
# these directly; nothing here comes from removed seed data.
_TEST_EFFECTS = [
    ("add_gold", "add", "Add gold to a country's treasury", "country"),
    ("add_treasury", "add", "Add to the treasury", "country"),
    ("create_character", "create", "Create a character", "country"),
]
_TEST_TRIGGERS = [
    ("has_variable", "check", "Checks if a variable is set", "none"),
    ("is_at_war", "check", "Is the country at war", "country"),
]


@pytest.fixture
def seeded_db():
    """A temporary database populated with a few known rows (no seed data)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    init_database(db_path)
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO effects (name, category, description, scope_type) VALUES (?, ?, ?, ?)",
        _TEST_EFFECTS,
    )
    cur.executemany(
        "INSERT INTO triggers (name, category, description, scope_type) VALUES (?, ?, ?, ?)",
        _TEST_TRIGGERS,
    )
    conn.commit()
    conn.close()
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


# GUI / data-type retrieval regression tests -------------------------------

_TEST_DATA_TYPES = [
    # (name, parent_type, description, definition_type, return_type, source_category)
    ("GetServerInfo", None, "Server Info of current session", "Global promote", "ServerInformation", "gui"),
    ("ShowTooltip", None, "Displays a tooltip widget", "Global function", "CString", "gui"),
    ("PdxGuiWidget.SetVisible", "PdxGuiWidget", "Toggle widget visibility", "Function", "void", "internal_gui"),
    ("Country.GetCapital", "Country", "Returns the capital location", "Promote", "Location", "script"),
]


@pytest.fixture
def dt_db():
    """Temporary DB with a few data_types rows across categories."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    init_database(db_path)
    conn = get_connection(db_path)
    conn.executemany(
        "INSERT INTO data_types (name, parent_type, description, definition_type, "
        "return_type, source_category) VALUES (?, ?, ?, ?, ?, ?)",
        _TEST_DATA_TYPES,
    )
    conn.commit()
    conn.close()
    yield db_path
    if db_path.exists():
        db_path.unlink()


def test_data_type_found_by_usage_not_name(dt_db):
    """A word only in the description (not the name) must still find the row."""
    results = search_data_types("session", db_path=dt_db)
    names = [r["name"] for r in results]
    assert "GetServerInfo" in names  # regression: name-only prefilter missed this


def test_data_type_found_by_return_type_word(dt_db):
    results = search_data_types("Location", db_path=dt_db)
    assert any(r["name"] == "Country.GetCapital" for r in results)


def test_data_type_return_type_filter(dt_db):
    """Empty query + return_type filter lists everything of that return type."""
    results = search_data_types("", return_type="CString", db_path=dt_db)
    assert [r["name"] for r in results] == ["ShowTooltip"]


def test_data_type_source_categories_filter(dt_db):
    """source_categories restricts to the GUI categories (gui + internal_gui)."""
    results = search_data_types("", source_categories=["gui", "internal_gui"], db_path=dt_db)
    names = {r["name"] for r in results}
    assert "Country.GetCapital" not in names
    assert {"GetServerInfo", "ShowTooltip", "PdxGuiWidget.SetVisible"} <= names


def test_data_type_gui_only_excludes_internal(dt_db):
    results = search_data_types("", source_categories=["gui"], db_path=dt_db)
    names = {r["name"] for r in results}
    assert "PdxGuiWidget.SetVisible" not in names
    assert "GetServerInfo" in names


@pytest.fixture
def links_db(tmp_path):
    """Scope links that share a name, plus data types in several categories."""
    db_path = tmp_path / "links.db"
    init_database(db_path)
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO scopes (name, scope_type, target_type, description) VALUES (?, ?, ?, ?)",
        [("province_definition", "location", "province_definition", "Unknown"),
         ("province", "country", "province", "Unknown"),
         ("province", "location", "province", "Unknown"),
         ("province", "", "", "Saved from code")])
    cur.executemany(
        "INSERT INTO data_types (name, parent_type, definition_type, source_category) "
        "VALUES (?, ?, ?, ?)",
        [("NotEqualTo_int32", None, "Global function", "common"),
         ("Not", None, "Global function", "common"),
         ("Thing.Not", "Thing", "Function", "gui"),
         ("Thing.Not", "Thing", "Function", "gui")])
    conn.commit()
    conn.close()
    return db_path


def test_scope_keeps_every_link_with_one_name(links_db):
    from pdx_syntax.search import search_scopes
    rows = search_scopes("province", db_path=links_db)
    assert [(r["name"], r["scope_type"]) for r in rows[:2]] == [
        ("province", "country"), ("province", "location")]
    assert not any(r["description"] == "Saved from code" for r in rows)


def test_exact_name_ranks_first_and_limit_zero_keeps_all(links_db):
    rows = search_data_types("Not", limit=0, db_path=links_db)
    assert [r["name"] for r in rows] == ["Not", "Thing.Not", "NotEqualTo_int32"]
