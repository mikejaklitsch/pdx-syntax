"""Seed the database with initial data."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from .database import get_connection, init_database, rebuild_fts_indexes
from .data.initial_data import (
    SCOPE_TYPES,
    FLOW_TRIGGERS,
    VARIABLE_TRIGGERS,
    GAME_STATE_TRIGGERS,
    ITERATOR_SCOPES,
    EFFECTS,
    ON_ACTIONS,
    MODIFIERS,
    SYNTAX_TEMPLATES,
    VERSION_CHANGES,
)


def seed_database(db_path: Optional[Path] = None, force: bool = False) -> dict:
    """
    Seed the database with initial data.

    Returns statistics about what was seeded.
    """
    init_database(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()

    stats = {
        "scope_types": 0,
        "triggers": 0,
        "scopes": 0,
        "effects": 0,
        "modifiers": 0,
        "on_actions": 0,
        "templates": 0,
        "changes": 0,
    }

    # Check if already seeded
    if not force:
        cursor.execute("SELECT COUNT(*) FROM triggers")
        if cursor.fetchone()[0] > 0:
            print("Database already seeded. Use force=True to reseed.")
            conn.close()
            return stats

    # Record the seed as a data source
    cursor.execute("""
        INSERT INTO data_sources (url, source_type, fetched_at, game_version)
        VALUES (?, ?, ?, ?)
    """, ("initial_seed", "seed", datetime.now().isoformat(), "1.1.0"))
    source_id = cursor.lastrowid

    # Seed scope types
    for scope_type in SCOPE_TYPES:
        cursor.execute("""
            INSERT OR REPLACE INTO scope_types (name, description)
            VALUES (?, ?)
        """, (scope_type["name"], scope_type["description"]))
        stats["scope_types"] += 1
    conn.commit()

    # Seed triggers (flow, variable, game state)
    all_triggers = FLOW_TRIGGERS + VARIABLE_TRIGGERS + GAME_STATE_TRIGGERS
    for trigger in all_triggers:
        cursor.execute("""
            INSERT OR REPLACE INTO triggers (name, category, description, syntax, scope_type, parameters, source_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            trigger["name"],
            trigger.get("category"),
            trigger.get("description"),
            trigger.get("syntax"),
            trigger.get("scope_type"),
            trigger.get("parameters"),
            source_id,
        ))
        stats["triggers"] += 1
    conn.commit()

    # Seed iterator scopes
    for scope in ITERATOR_SCOPES:
        cursor.execute("""
            INSERT OR REPLACE INTO scopes
            (name, scope_type, target_type, description, syntax, parameters, is_iterator, iterator_type, source_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            scope["name"],
            scope.get("scope_type"),
            scope.get("target_type"),
            scope.get("description"),
            scope.get("syntax"),
            scope.get("parameters"),
            scope.get("is_iterator", 0),
            scope.get("iterator_type"),
            source_id,
        ))
        stats["scopes"] += 1
    conn.commit()

    # Seed effects
    for effect in EFFECTS:
        cursor.execute("""
            INSERT OR REPLACE INTO effects (name, category, description, syntax, scope_type, parameters, source_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            effect["name"],
            effect.get("category"),
            effect.get("description"),
            effect.get("syntax"),
            effect.get("scope_type"),
            effect.get("parameters"),
            source_id,
        ))
        stats["effects"] += 1
    conn.commit()

    # Seed modifiers
    for modifier in MODIFIERS:
        cursor.execute("""
            INSERT OR REPLACE INTO modifiers
            (name, category, description, modifier_type, scope_type, is_boolean, default_value, color, percent, source_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            modifier["name"],
            modifier.get("category"),
            modifier.get("description"),
            modifier.get("modifier_type"),
            modifier.get("scope_type"),
            modifier.get("is_boolean", 0),
            modifier.get("default_value"),
            modifier.get("color"),
            modifier.get("percent", 0),
            source_id,
        ))
        stats["modifiers"] += 1
    conn.commit()

    # Seed on_actions
    for on_action in ON_ACTIONS:
        cursor.execute("""
            INSERT OR REPLACE INTO on_actions (name, category, description, scope_type, parameters, source_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            on_action["name"],
            on_action.get("category"),
            on_action.get("description"),
            on_action.get("scope_type"),
            on_action.get("parameters"),
            source_id,
        ))
        stats["on_actions"] += 1
    conn.commit()

    # Seed syntax templates
    for template in SYNTAX_TEMPLATES:
        cursor.execute("""
            INSERT OR REPLACE INTO syntax_templates (name, category, template, description, parameters, source_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            template["name"],
            template.get("category"),
            template.get("template"),
            template.get("description"),
            template.get("parameters"),
            source_id,
        ))
        stats["templates"] += 1
    conn.commit()

    # Seed version changes
    for change in VERSION_CHANGES:
        cursor.execute("""
            INSERT INTO change_log (game_version, change_type, item_type, item_name, description, recorded_at, source_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            change["game_version"],
            change["change_type"],
            change["item_type"],
            change["item_name"],
            change.get("description"),
            datetime.now().isoformat(),
            source_id,
        ))
        stats["changes"] += 1
    conn.commit()

    conn.close()

    # Rebuild FTS indexes
    rebuild_fts_indexes(db_path)

    return stats


def reset_and_seed(db_path: Optional[Path] = None) -> dict:
    """Reset the database and reseed with initial data."""
    from .database import DEFAULT_DB_PATH

    path = db_path or DEFAULT_DB_PATH
    if path.exists():
        path.unlink()

    return seed_database(db_path, force=True)
