"""Database management for EU5 syntax data."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

# Default database location
DEFAULT_DB_PATH = Path(__file__).parent / "data" / "eu5_syntax.db"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Get a database connection."""
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_database(db_path: Optional[Path] = None) -> None:
    """Initialize the database schema."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Schema version tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)

    # Data source tracking (wiki pages, digests, etc.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS data_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            source_type TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            game_version TEXT,
            content_hash TEXT,
            UNIQUE(url, fetched_at)
        )
    """)

    # Game versions for tracking changes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL UNIQUE,
            release_date TEXT,
            notes TEXT
        )
    """)

    # Scope types (country, character, location, etc.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scope_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            parent_scope TEXT,
            added_version TEXT,
            deprecated_version TEXT
        )
    """)

    # Effects (actions that change game state)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS effects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            description TEXT,
            syntax TEXT,
            scope_type TEXT,
            parameters TEXT,
            example TEXT,
            added_version TEXT,
            deprecated_version TEXT,
            source_id INTEGER,
            FOREIGN KEY (source_id) REFERENCES data_sources(id)
        )
    """)

    # Triggers (conditions that check game state)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS triggers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            description TEXT,
            syntax TEXT,
            scope_type TEXT,
            parameters TEXT,
            example TEXT,
            added_version TEXT,
            deprecated_version TEXT,
            source_id INTEGER,
            FOREIGN KEY (source_id) REFERENCES data_sources(id)
        )
    """)

    # Scopes (iterators and scope changers)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scopes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            scope_type TEXT,
            target_type TEXT,
            description TEXT,
            syntax TEXT,
            parameters TEXT,
            is_iterator INTEGER DEFAULT 0,
            iterator_type TEXT,
            added_version TEXT,
            deprecated_version TEXT,
            source_id INTEGER,
            FOREIGN KEY (source_id) REFERENCES data_sources(id)
        )
    """)

    # Modifiers (game stat modifiers)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS modifiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            description TEXT,
            modifier_type TEXT,
            scope_type TEXT,
            is_boolean INTEGER DEFAULT 0,
            default_value TEXT,
            color TEXT,
            percent INTEGER DEFAULT 0,
            added_version TEXT,
            deprecated_version TEXT,
            source_id INTEGER,
            FOREIGN KEY (source_id) REFERENCES data_sources(id)
        )
    """)

    # On-actions (event hooks)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS on_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            description TEXT,
            scope_type TEXT,
            parameters TEXT,
            example TEXT,
            added_version TEXT,
            deprecated_version TEXT,
            source_id INTEGER,
            FOREIGN KEY (source_id) REFERENCES data_sources(id)
        )
    """)

    # Defines (game constants)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS defines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            description TEXT,
            default_value TEXT,
            value_type TEXT,
            added_version TEXT,
            deprecated_version TEXT,
            source_id INTEGER,
            FOREIGN KEY (source_id) REFERENCES data_sources(id)
        )
    """)

    # Localization keys
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS localization_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern TEXT NOT NULL,
            context TEXT,
            description TEXT,
            example TEXT,
            source_id INTEGER,
            FOREIGN KEY (source_id) REFERENCES data_sources(id)
        )
    """)

    # Syntax templates (common patterns)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS syntax_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            template TEXT NOT NULL,
            description TEXT,
            parameters TEXT,
            example TEXT,
            source_id INTEGER,
            FOREIGN KEY (source_id) REFERENCES data_sources(id)
        )
    """)

    # Change log for tracking modifications across versions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS change_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_version TEXT NOT NULL,
            change_type TEXT NOT NULL,
            item_type TEXT NOT NULL,
            item_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            description TEXT,
            recorded_at TEXT NOT NULL,
            source_id INTEGER,
            FOREIGN KEY (source_id) REFERENCES data_sources(id)
        )
    """)

    # Create indexes for fast searching
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_effects_name ON effects(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_effects_category ON effects(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_effects_scope ON effects(scope_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_triggers_name ON triggers(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_triggers_category ON triggers(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_triggers_scope ON triggers(scope_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scopes_name ON scopes(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scopes_type ON scopes(scope_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_modifiers_name ON modifiers(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_modifiers_category ON modifiers(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_on_actions_name ON on_actions(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_change_log_version ON change_log(game_version)")

    # Full-text search tables (standalone, manually synced)
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS effects_fts USING fts5(
            name, category, description, syntax, parameters
        )
    """)
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS triggers_fts USING fts5(
            name, category, description, syntax, parameters
        )
    """)
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS scopes_fts USING fts5(
            name, scope_type, target_type, description, syntax
        )
    """)
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS modifiers_fts USING fts5(
            name, category, description, modifier_type
        )
    """)

    # Record schema version
    cursor.execute("""
        INSERT OR IGNORE INTO schema_version (version, applied_at)
        VALUES (1, ?)
    """, (datetime.now().isoformat(),))

    conn.commit()
    conn.close()


def record_data_source(
    url: str,
    source_type: str,
    game_version: Optional[str] = None,
    content_hash: Optional[str] = None,
    db_path: Optional[Path] = None
) -> int:
    """Record a data source fetch and return its ID."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO data_sources (url, source_type, fetched_at, game_version, content_hash)
        VALUES (?, ?, ?, ?, ?)
    """, (url, source_type, datetime.now().isoformat(), game_version, content_hash))
    source_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return source_id


def rebuild_fts_indexes(db_path: Optional[Path] = None) -> None:
    """Rebuild full-text search indexes."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Rebuild effects FTS
    cursor.execute("DELETE FROM effects_fts")
    cursor.execute("""
        INSERT INTO effects_fts(rowid, name, category, description, syntax, parameters)
        SELECT id, name, category, description, syntax, parameters FROM effects
    """)

    # Rebuild triggers FTS
    cursor.execute("DELETE FROM triggers_fts")
    cursor.execute("""
        INSERT INTO triggers_fts(rowid, name, category, description, syntax, parameters)
        SELECT id, name, category, description, syntax, parameters FROM triggers
    """)

    # Rebuild scopes FTS
    cursor.execute("DELETE FROM scopes_fts")
    cursor.execute("""
        INSERT INTO scopes_fts(rowid, name, scope_type, target_type, description, syntax)
        SELECT id, name, scope_type, target_type, description, syntax FROM scopes
    """)

    # Rebuild modifiers FTS
    cursor.execute("DELETE FROM modifiers_fts")
    cursor.execute("""
        INSERT INTO modifiers_fts(rowid, name, category, description, modifier_type)
        SELECT id, name, category, description, modifier_type FROM modifiers
    """)

    conn.commit()
    conn.close()
