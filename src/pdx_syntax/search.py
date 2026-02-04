"""Search functionality for EU5 syntax database."""

import sqlite3
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
    return results[:limit]


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
    return results[:limit]


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
    return results[:limit]


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
    return results[:limit]


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
    return results[:limit]


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
    return results[:limit]


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
