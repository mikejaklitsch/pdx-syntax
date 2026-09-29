"""Search functionality for EU5 syntax database."""

import sqlite3
from datetime import datetime
from typing import Optional
from pathlib import Path

from rapidfuzz import fuzz, process

from .database import get_connection, DEFAULT_DB_PATH


def rank(results, query):
    """Sort in place: exact name first, then names that start with the query,
    then fuzzy score. For a dotted name (Country.GetName) the member part
    counts too. An empty query sorts by name."""
    q = (query or "").lower()
    if not q:
        results.sort(key=lambda r: str(r.get("name") or ""))
        return

    def key(r):
        name = str(r.get("name") or "").lower()
        member = name.rsplit(".", 1)[-1]
        return (name == q, member == q,
                name.startswith(q) or member.startswith(q),
                r.get("_score", 0))
    results.sort(key=key, reverse=True)


def dedupe(results, limit=None, key=lambda r: r["name"]):
    """Keep the first (best-scored) row per key. A limit of 0 or None keeps all."""
    seen = set()
    out = []
    for r in results:
        k = key(r)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out[:limit] if limit else out


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
    rank(results, query)

    return dedupe(results, limit)


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

    rank(results, query)

    return dedupe(results, limit)


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

    rank(results, query)

    return dedupe(results, limit)


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

    rank(results, query)

    # One name can be several links: 'province' reads from a country (with
    # data) and from a location. Keep each link. A "Saved from code" row adds
    # nothing when a documented row of the same name exists.
    documented = {r["name"] for r in results if r.get("description") != "Saved from code"}
    results = [r for r in results
               if r.get("description") != "Saved from code" or r["name"] not in documented]
    return dedupe(results, limit,
                  key=lambda r: (r["name"], r.get("scope_type") or "", r.get("target_type") or ""))


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

    rank(results, query)

    return dedupe(results, limit)


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

    rank(results, query)

    return dedupe(results, limit)


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
        # SQLite reads a negative LIMIT as no limit.
        cursor.execute(sql, (query, limit if limit else -1))
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


def get_scope_type(name: str, db_path: Optional[Path] = None) -> Optional[dict]:
    """Get a single scope type with its full metadata, or None."""
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scope_types WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


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


def get_all_by_name(
    name: str,
    item_type: str,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Get every row with this exact name (a scope link can have several)."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {item_type} WHERE name = ? ORDER BY id", (name,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def search_data_types(
    query: str,
    parent_type: Optional[str] = None,
    source_category: Optional[str] = None,
    source_categories: Optional[list[str]] = None,
    definition_type: Optional[str] = None,
    return_type: Optional[str] = None,
    limit: int = 10,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Search data types by name, usage (description), or return type.

    The query is matched against name, description AND return type, so a GUI
    function can be found by what it does or what it returns, not only by an
    exact fragment of its name. Filters:
      * parent_type       - the owning type (e.g. Country, PdxGuiWidget)
      * source_category   - a single category (script, gui, internal_gui, ...)
      * source_categories - a list of categories (OR'd); use for "gui + internal"
      * definition_type   - Function, Promote, Type, ...
      * return_type       - what the function returns (bool, CString, ...)
    """
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

    if source_categories:
        placeholders = ", ".join("?" for _ in source_categories)
        sql += f" AND source_category IN ({placeholders})"
        params.extend(source_categories)

    if definition_type:
        sql += " AND definition_type = ?"
        params.append(definition_type)

    if return_type:
        sql += " AND return_type = ?"
        params.append(return_type)

    # Pre-filter with LIKE (across name, description and return type) to avoid
    # fuzzy-scoring 25k+ rows while still allowing usage/return-type queries.
    # An empty query means "everything matching the filters".
    if query:
        sql += " AND (name LIKE ? OR description LIKE ? OR return_type LIKE ?)"
        like = f"%{query}%"
        params.extend([like, like, like])

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        row_dict = dict(row)
        if query:
            searchable = " ".join(str(row_dict.get(c, "") or "") for c in
                                  ("name", "description", "return_type"))
            score = fuzz.partial_ratio(query.lower(), searchable.lower())
            if score < 50:
                continue
        else:
            score = 100
        row_dict["_score"] = score
        results.append(row_dict)

    rank(results, query)

    # The same name can be listed in several categories (gui and script, for
    # example); each is a separate fact about where it can be used.
    return dedupe(results, limit,
                  key=lambda r: (r["name"], r.get("parent_type"), r.get("source_category")))


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

    rank(results, query)

    return dedupe(results, limit)


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


