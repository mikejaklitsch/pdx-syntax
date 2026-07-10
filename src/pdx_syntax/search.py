"""Search functionality for EU5 syntax database."""

import sqlite3
from datetime import datetime
from typing import Optional
from pathlib import Path

from rapidfuzz import fuzz, process

from .database import get_connection, DEFAULT_DB_PATH


def fuzzy_search(
    query: str,
    table: str,
    columns: list[str],
    limit: int = 10,
    threshold: int = 60,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """
    Perform fuzzy search across specified columns.

    Args:
        query: Search term
        table: Database table to search
        columns: Columns to search in
        limit: Maximum results to return
        threshold: Minimum fuzzy match score (0-100)
        db_path: Optional database path

    Returns:
        List of matching rows as dictionaries
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Get all records for fuzzy matching
    col_list = ", ".join(["id"] + columns)
    cursor.execute(f"SELECT {col_list} FROM {table}")
    rows = cursor.fetchall()

    results = []
    for row in rows:
        row_dict = dict(row)
        # Combine searchable columns for matching
        searchable = " ".join(str(row_dict.get(col, "") or "") for col in columns)
        score = fuzz.partial_ratio(query.lower(), searchable.lower())

        if score >= threshold:
            # Fetch full record
            cursor.execute(f"SELECT * FROM {table} WHERE id = ?", (row_dict["id"],))
            full_row = cursor.fetchone()
            if full_row:
                result = dict(full_row)
                result["_score"] = score
                results.append(result)

    conn.close()

    # Sort by score descending and limit
    results.sort(key=lambda x: x["_score"], reverse=True)

    # Deduplicate by name, keeping highest score
    seen = set()
    deduped = []
    for r in results:
        if r["name"] not in seen:
            seen.add(r["name"])
            deduped.append(r)
    return deduped[:limit]


MAIN_TABLES = [
    "effects", "triggers", "scopes", "modifiers", "on_actions",
    "data_types", "custom_localizations",
]


def suggest_similar(
    query: str,
    item_type: str,
    limit: int = 5,
    threshold: int = 60,
    db_path: Optional[Path] = None,
) -> list[tuple[str, int]]:
    """Fuzzy-match query against all names in a table, for did-you-mean
    suggestions. Returns [(name, score)] best-first."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT name FROM {item_type}")
        names = [r[0] for r in cursor.fetchall()]
    except sqlite3.OperationalError:
        names = []
    finally:
        conn.close()
    if not names:
        return []
    matches = process.extract(query, names, scorer=fuzz.WRatio, limit=limit)
    return [(m, int(score)) for m, score, _ in matches if score >= threshold]


def find_in_other_tables(
    name: str,
    exclude: str,
    db_path: Optional[Path] = None,
) -> list[str]:
    """Exact-name lookup across all main tables except `exclude`.
    Returns table names that contain the entry."""
    hits = []
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        for table in MAIN_TABLES:
            if table == exclude:
                continue
            try:
                cursor.execute(f"SELECT 1 FROM {table} WHERE name = ? LIMIT 1",
                               (name,))
                if cursor.fetchone():
                    hits.append(table)
            except sqlite3.OperationalError:
                continue
    finally:
        conn.close()
    return hits


def search_effects(
    query: str,
    scope: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 10,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Search effects by name, description, or other attributes."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Build query with optional filters
    sql = "SELECT * FROM effects WHERE 1=1"
    params = []

    if scope:
        sql += " AND scope_type = ?"
        params.append(scope)

    if category:
        sql += " AND category = ?"
        params.append(category)

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    # Fuzzy filter results
    results = []
    for row in rows:
        row_dict = dict(row)
        searchable = f"{row_dict.get('name', '')} {row_dict.get('description', '')} {row_dict.get('syntax', '')}"
        score = fuzz.partial_ratio(query.lower(), searchable.lower())

        if score >= 50:
            row_dict["_score"] = score
            results.append(row_dict)

    results.sort(key=lambda x: x["_score"], reverse=True)

    # Deduplicate by name, keeping highest score
    seen = set()
    deduped = []
    for r in results:
        if r["name"] not in seen:
            seen.add(r["name"])
            deduped.append(r)
    return deduped[:limit]


def search_triggers(
    query: str,
    scope: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 10,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Search triggers by name, description, or other attributes."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    sql = "SELECT * FROM triggers WHERE 1=1"
    params = []

    if scope:
        sql += " AND scope_type = ?"
        params.append(scope)

    if category:
        sql += " AND category = ?"
        params.append(category)

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        row_dict = dict(row)
        searchable = f"{row_dict.get('name', '')} {row_dict.get('description', '')} {row_dict.get('syntax', '')}"
        score = fuzz.partial_ratio(query.lower(), searchable.lower())

        if score >= 50:
            row_dict["_score"] = score
            results.append(row_dict)

    results.sort(key=lambda x: x["_score"], reverse=True)

    # Deduplicate by name, keeping highest score
    seen = set()
    deduped = []
    for r in results:
        if r["name"] not in seen:
            seen.add(r["name"])
            deduped.append(r)
    return deduped[:limit]


def search_scopes(
    query: str,
    scope_type: Optional[str] = None,
    iterator_only: bool = False,
    limit: int = 10,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Search scopes by name or type."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    sql = "SELECT * FROM scopes WHERE 1=1"
    params = []

    if scope_type:
        sql += " AND scope_type = ?"
        params.append(scope_type)

    if iterator_only:
        sql += " AND is_iterator = 1"

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        row_dict = dict(row)
        searchable = f"{row_dict.get('name', '')} {row_dict.get('description', '')} {row_dict.get('target_type', '')}"
        score = fuzz.partial_ratio(query.lower(), searchable.lower())

        if score >= 50:
            row_dict["_score"] = score
            results.append(row_dict)

    results.sort(key=lambda x: x["_score"], reverse=True)

    # Deduplicate by name, keeping highest score
    seen = set()
    deduped = []
    for r in results:
        if r["name"] not in seen:
            seen.add(r["name"])
            deduped.append(r)
    return deduped[:limit]


def search_modifiers(
    query: str,
    category: Optional[str] = None,
    scope_type: Optional[str] = None,
    boolean_only: bool = False,
    limit: int = 10,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Search modifiers by name, category, or type."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    sql = "SELECT * FROM modifiers WHERE 1=1"
    params = []

    if category:
        sql += " AND category = ?"
        params.append(category)

    if scope_type:
        sql += " AND scope_type = ?"
        params.append(scope_type)

    if boolean_only:
        sql += " AND is_boolean = 1"

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        row_dict = dict(row)
        searchable = f"{row_dict.get('name', '')} {row_dict.get('description', '')} {row_dict.get('modifier_type', '')}"
        score = fuzz.partial_ratio(query.lower(), searchable.lower())

        if score >= 50:
            row_dict["_score"] = score
            results.append(row_dict)

    results.sort(key=lambda x: x["_score"], reverse=True)

    # Deduplicate by name, keeping highest score
    seen = set()
    deduped = []
    for r in results:
        if r["name"] not in seen:
            seen.add(r["name"])
            deduped.append(r)
    return deduped[:limit]


def search_on_actions(
    query: str,
    scope_type: Optional[str] = None,
    limit: int = 10,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Search on_actions by name or description."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    sql = "SELECT * FROM on_actions WHERE 1=1"
    params = []

    if scope_type:
        sql += " AND scope_type = ?"
        params.append(scope_type)

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        row_dict = dict(row)
        searchable = f"{row_dict.get('name', '')} {row_dict.get('description', '')}"
        score = fuzz.partial_ratio(query.lower(), searchable.lower())

        if score >= 50:
            row_dict["_score"] = score
            results.append(row_dict)

    results.sort(key=lambda x: x["_score"], reverse=True)

    # Deduplicate by name, keeping highest score
    seen = set()
    deduped = []
    for r in results:
        if r["name"] not in seen:
            seen.add(r["name"])
            deduped.append(r)
    return deduped[:limit]


def fts_search(
    query: str,
    item_type: str,
    limit: int = 10,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """
    Full-text search using SQLite FTS5.

    Args:
        query: Search query (supports FTS5 query syntax)
        item_type: Type to search (effects, triggers, scopes, modifiers)
        limit: Maximum results
        db_path: Optional database path

    Returns:
        List of matching records
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    fts_table = f"{item_type}_fts"
    main_table = item_type

    # Use FTS5 match query
    sql = f"""
        SELECT {main_table}.*, bm25({fts_table}) as rank
        FROM {fts_table}
        JOIN {main_table} ON {fts_table}.rowid = {main_table}.id
        WHERE {fts_table} MATCH ?
        ORDER BY rank
        LIMIT ?
    """

    try:
        cursor.execute(sql, (query, limit))
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
    except sqlite3.OperationalError:
        # FTS table might not exist or be populated
        results = []

    conn.close()
    return results


def list_categories(
    item_type: str,
    db_path: Optional[Path] = None,
) -> list[str]:
    """List all unique categories for an item type."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(f"SELECT DISTINCT category FROM {item_type} WHERE category IS NOT NULL ORDER BY category")
    rows = cursor.fetchall()
    conn.close()

    return [row["category"] for row in rows]


def list_scope_types(db_path: Optional[Path] = None) -> list[str]:
    """List all scope types in the database."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM scope_types ORDER BY name")
    rows = cursor.fetchall()
    conn.close()

    return [row["name"] for row in rows]


def get_by_name(
    name: str,
    item_type: str,
    db_path: Optional[Path] = None,
) -> Optional[dict]:
    """Get an exact match by name."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(f"SELECT * FROM {item_type} WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def search_data_types(
    query: str,
    parent_type: Optional[str] = None,
    source_category: Optional[str] = None,
    definition_type: Optional[str] = None,
    limit: int = 10,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Search data types by name or description."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    sql = "SELECT * FROM data_types WHERE 1=1"
    params: list = []

    if parent_type:
        sql += " AND parent_type = ?"
        params.append(parent_type)

    if source_category:
        sql += " AND source_category = ?"
        params.append(source_category)

    if definition_type:
        sql += " AND definition_type = ?"
        params.append(definition_type)

    # Pre-filter with LIKE to avoid fuzzy scoring 25k+ rows
    sql += " AND name LIKE ?"
    params.append(f"%{query}%")

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        row_dict = dict(row)
        searchable = f"{row_dict.get('name', '')} {row_dict.get('description', '')}"
        score = fuzz.partial_ratio(query.lower(), searchable.lower())

        if score >= 50:
            row_dict["_score"] = score
            results.append(row_dict)

    results.sort(key=lambda x: x["_score"], reverse=True)

    seen = set()
    deduped = []
    for r in results:
        if r["name"] not in seen:
            seen.add(r["name"])
            deduped.append(r)
    return deduped[:limit]


def search_custom_localizations(
    query: str,
    scope: Optional[str] = None,
    search_entries: bool = False,
    limit: int = 10,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Search custom localizations by name, or by entries content.

    When *search_entries* is True, filters rows whose entries text
    contains the query (SQL LIKE) and ranks by name similarity.
    Otherwise fuzzy-matches on name only.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    sql = "SELECT * FROM custom_localizations WHERE 1=1"
    params: list = []

    if scope:
        sql += " AND scope = ?"
        params.append(scope)

    if search_entries:
        sql += " AND entries LIKE ?"
        params.append(f"%{query}%")

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        row_dict = dict(row)
        searchable = row_dict.get("name", "")
        score = fuzz.partial_ratio(query.lower(), searchable.lower())

        if search_entries or score >= 50:
            row_dict["_score"] = score
            results.append(row_dict)

    results.sort(key=lambda x: x["_score"], reverse=True)

    seen = set()
    deduped = []
    for r in results:
        if r["name"] not in seen:
            seen.add(r["name"])
            deduped.append(r)
    return deduped[:limit]


def add_note(
    item_type: str,
    item_name: str,
    content: str,
    author: str = "user",
    db_path: Optional[Path] = None,
) -> int:
    """Add a note to an item. Returns the note ID."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notes (item_type, item_name, content, author, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (item_type, item_name, content, author, datetime.now().isoformat()))
    note_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return note_id


def get_notes(
    item_type: str,
    item_name: str,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Get all notes for an item."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM notes
        WHERE item_type = ? AND item_name = ?
        ORDER BY created_at
    """, (item_type, item_name))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_notes(db_path: Optional[Path] = None) -> list[dict]:
    """Get all notes across all items."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notes ORDER BY item_type, item_name, created_at")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_note(note_id: int, db_path: Optional[Path] = None) -> bool:
    """Delete a note by ID. Returns True if a row was deleted."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_changes_for_version(
    version: str,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Get all changes recorded for a specific game version."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM change_log
        WHERE game_version = ?
        ORDER BY item_type, item_name
    """, (version,))
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]
