"""Parse EU5 game-dumped log files and populate the database."""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..database import get_connection, init_database, record_data_source, rebuild_fts_indexes, set_meta
from .categories import categorize_item, categorize_modifier, categorize_on_action

# Paradox user directory (where the game dumps docs/ and logs/data_types/).
# Override with $PDX_USER_DIR on other machines.
EU5_USER_DIR = Path(os.environ.get(
    "PDX_USER_DIR",
    "/mnt/c/Users/Mjaklitsch/Documents/Paradox Interactive/Europa Universalis V"))
DEFAULT_DOCS_DIR = EU5_USER_DIR / "docs"
DEFAULT_DATA_TYPES_DIR = EU5_USER_DIR / "logs" / "data_types"

# Game install root (for the patch checksum). Override with $PDX_GAME_ROOT.
DEFAULT_GAME_ROOT = Path(os.environ.get(
    "PDX_GAME_ROOT",
    "/mnt/d/Program Files (x86)/Steam/steamapps/common/Europa Universalis V"))


def read_game_checksum(game_root: Optional[Path] = None) -> Optional[str]:
    """Current game patch checksum from binaries/checksum.txt, or None."""
    root = game_root or DEFAULT_GAME_ROOT
    try:
        text = (root / "binaries" / "checksum.txt").read_text(
            encoding="utf-8", errors="ignore").strip()
        return text or None
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_scopes(scope_string: str) -> str:
    """'Country, Location' -> 'country, location'; 'none' stays 'none'."""
    if not scope_string:
        return ""
    parts = [p.strip().lower() for p in scope_string.split(",") if p.strip()]
    return ", ".join(parts)


def _detect_iterator(name: str) -> tuple[bool, Optional[str]]:
    """Return (is_iterator, iterator_type) based on name prefix."""
    if name.startswith("any_"):
        return True, "trigger"
    if name.startswith("every_"):
        return True, "effect"
    if name.startswith("random_"):
        return True, "effect_random"
    if name.startswith("ordered_"):
        return True, "effect_ordered"
    return False, None


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_effects_log(content: str) -> list[dict]:
    """Parse effects.log -> list of dicts with name, description, scope_type, parameters."""
    entries = []
    # Split on ## headers (skip the file-level # header)
    blocks = re.split(r"\n## ", content)
    for block in blocks[1:]:  # skip preamble before first ##
        lines = block.strip().split("\n")
        name = lines[0].strip()

        desc_lines = []
        scope_type = ""
        targets = ""

        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith("**Supported Scopes**:"):
                scope_type = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("**Supported Targets**:"):
                targets = stripped.split(":", 1)[1].strip()
            elif stripped:
                desc_lines.append(stripped)

        entries.append({
            "name": name,
            "description": " ".join(desc_lines),
            "scope_type": _normalize_scopes(scope_type),
            "parameters": _normalize_scopes(targets),
        })
    return entries


def parse_triggers_log(content: str) -> list[dict]:
    """Parse triggers.log -> list of dicts with name, description, scope_type, parameters, traits."""
    entries = []
    blocks = re.split(r"\n## ", content)
    for block in blocks[1:]:
        lines = block.strip().split("\n")
        name = lines[0].strip()

        desc_lines = []
        scope_type = ""
        targets = ""
        traits = ""

        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith("**Supported Scopes**:"):
                scope_type = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("**Supported Targets**:"):
                targets = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("Traits:"):
                traits = stripped.split(":", 1)[1].strip()
            elif stripped == "Reads gamestate for all scopes.":
                continue  # skip noise line
            elif stripped:
                desc_lines.append(stripped)

        entries.append({
            "name": name,
            "description": " ".join(desc_lines),
            "scope_type": _normalize_scopes(scope_type),
            "parameters": _normalize_scopes(targets),
            "traits": traits,
        })
    return entries


def parse_modifiers_log(content: str) -> list[dict]:
    """Parse modifiers.log -> list of dicts with name and categories."""
    entries = []
    for line in content.splitlines():
        m = re.match(r"^Tag:\s*([^,]+),\s*Categories:\s*(.*)$", line)
        if m:
            name = m.group(1).strip()
            raw_cats = m.group(2)
            cats = [c.strip() for c in raw_cats.split(",") if c.strip() and c.strip() != "All"]
            entries.append({
                "name": name,
                "categories": cats,
            })
    return entries


def parse_on_actions_log(content: str) -> list[dict]:
    """Parse on_actions.log -> list of dicts with name, from_code, scope_type."""
    entries = []
    blocks = re.split(r"-{4,}", content)
    for block in blocks:
        block = block.strip()
        if not block or block.startswith("On Action"):
            continue

        lines = block.split("\n")
        name = ""
        from_code = False
        scope_type = ""

        for line in lines:
            stripped = line.strip()
            if stripped.endswith(":") and not stripped.startswith("From") and not stripped.startswith("Expected"):
                name = stripped[:-1]
            elif stripped.startswith("From Code:"):
                from_code = stripped.split(":", 1)[1].strip().lower() == "yes"
            elif stripped.startswith("Expected Scope:"):
                scope_type = stripped.split(":", 1)[1].strip().lower()

        if name:
            entries.append({
                "name": name,
                "from_code": from_code,
                "scope_type": scope_type,
            })
    return entries


def parse_event_targets_log(content: str) -> list[dict]:
    """Parse event_targets.log -> list of dicts with name, description, input/output scopes."""
    entries = []

    # Check for "Event Targets Saved from Code:" section
    saved_section = ""
    if "Event Targets Saved from Code:" in content:
        parts = content.split("Event Targets Saved from Code:")
        content = parts[0]
        saved_section = parts[1]

    blocks = re.split(r"\n### ", content)
    for block in blocks[1:]:
        lines = block.strip().split("\n")
        name = lines[0].strip()

        description = ""
        input_scopes = ""
        output_scopes = ""
        requires_data = False
        global_link = False

        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith("Input Scopes:"):
                input_scopes = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("Output Scopes:"):
                output_scopes = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("Requires Data:"):
                requires_data = stripped.split(":", 1)[1].strip().lower() == "yes"
            elif stripped.startswith("Global Link:"):
                global_link = stripped.split(":", 1)[1].strip().lower() == "yes"
            elif stripped.startswith("Wild Card:"):
                continue
            elif stripped:
                description = stripped

        entries.append({
            "name": name,
            "description": description,
            "input_scopes": _normalize_scopes(input_scopes),
            "output_scopes": _normalize_scopes(output_scopes),
            "requires_data": requires_data,
            "global_link": global_link,
        })

    # Parse bare names from saved-from-code section
    for line in saved_section.splitlines():
        name = line.strip()
        if name and re.match(r"^[a-z][a-z0-9_]*$", name):
            entries.append({
                "name": name,
                "description": "Saved from code",
                "input_scopes": "",
                "output_scopes": "",
                "requires_data": False,
                "global_link": False,
            })

    return entries


def parse_custom_localization_log(content: str) -> list[dict]:
    """Parse custom_localization.log -> list of dicts with name, scope, random_valid, entries."""
    entries = []
    blocks = re.split(r"-{4,}", content)
    for block in blocks:
        block = block.strip()
        if not block or block.startswith("Custom Localization"):
            continue

        name = ""
        scope = ""
        random_valid = False
        entry_lines = []
        in_entries = False

        for line in block.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if in_entries:
                entry_lines.append(stripped)
            elif stripped.startswith("Scope:"):
                scope = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("Random Valid:"):
                random_valid = stripped.split(":", 1)[1].strip().lower() == "yes"
            elif stripped.startswith("Entries:"):
                in_entries = True
            elif not name:
                # First non-empty, non-field line is the name (strip trailing colon)
                name = stripped.rstrip(":")

        if name:
            entries.append({
                "name": name,
                "scope": scope.lower() if scope else "",
                "random_valid": random_valid,
                "entries": "\n".join(entry_lines) if entry_lines else "",
            })
    return entries


def parse_data_types(content: str) -> list[dict]:
    """Parse data_types_*.txt -> list of dicts with name, parent_type, args, description, definition_type, return_type."""
    entries = []
    blocks = re.split(r"\n-{4,}\n", content)
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split("\n")
        first_line = lines[0].strip()
        if not first_line:
            continue

        # Parse name and args from first line: "Name( Arg0, Arg1 )" or "Type.Method( Arg0 )" or just "Name"
        args = ""
        paren_match = re.match(r"^(.+?)\(\s*(.*?)\s*\)$", first_line)
        if paren_match:
            raw_name = paren_match.group(1).strip()
            args = paren_match.group(2).strip()
        else:
            raw_name = first_line

        # Extract parent_type from dot notation
        parent_type = ""
        if "." in raw_name:
            parent_type = raw_name.rsplit(".", 1)[0]

        description = ""
        definition_type = ""
        return_type = ""

        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith("Description:"):
                description = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("Definition type:"):
                definition_type = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("Return type:"):
                return_type = stripped.split(":", 1)[1].strip()

        if raw_name and definition_type:
            entries.append({
                "name": raw_name,
                "parent_type": parent_type or None,
                "args": args or None,
                "description": description,
                "definition_type": definition_type,
                "return_type": return_type,
            })
    return entries


# ---------------------------------------------------------------------------
# File reading helpers
# ---------------------------------------------------------------------------

def _read_file(directory: Path, filename: str) -> Optional[str]:
    """Read a file from a directory, returning None if missing."""
    path = directory / filename
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace")
    return None


# ---------------------------------------------------------------------------
# DB writer / main entry point
# ---------------------------------------------------------------------------

def digest_update(
    db_path: Optional[Path] = None,
    docs_dir: Path = DEFAULT_DOCS_DIR,
    data_types_dir: Path = DEFAULT_DATA_TYPES_DIR,
    game_version: Optional[str] = None,
    verbose: bool = True,
    offline: bool = False,
) -> dict:
    """
    Main entry point: read game-dumped log files and populate DB.

    *docs_dir* is the EU5 docs/ folder containing .log files.
    *data_types_dir* is the EU5 logs/data_types/ folder containing .txt files.
    If *offline* is True only built-in seed data is loaded.
    """
    init_database(db_path)

    if offline:
        if verbose:
            print("Offline mode: loading seed data only...")
        from ..seed import seed_database
        return seed_database(db_path, force=True)

    if not docs_dir.is_dir():
        raise RuntimeError(f"Docs directory not found: {docs_dir}")

    version = game_version or _detect_game_version(docs_dir)
    if verbose:
        print(f"Reading game data (version {version})...")

    checksum_file = DEFAULT_GAME_ROOT / "binaries" / "checksum.txt"
    try:
        newest_dump = max(
            (f.stat().st_mtime for f in docs_dir.glob("*.log")), default=0)
        if newest_dump and checksum_file.is_file() and \
                newest_dump < checksum_file.stat().st_mtime:
            print("WARNING: the docs/ dumps are older than the current game "
                  "install — re-dump script docs from the in-game console "
                  "before updating, or the DB will describe the previous patch.")
    except OSError:
        pass

    conn = get_connection(db_path)
    cursor = conn.cursor()

    source_id = record_data_source(
        url=str(docs_dir),
        source_type="game-local",
        game_version=version,
        db_path=db_path,
    )

    stats = {
        "effects": 0,
        "triggers": 0,
        "scopes": 0,
        "modifiers": 0,
        "on_actions": 0,
        "custom_localizations": 0,
        "data_types": 0,
    }

    for table in ("effects", "triggers", "scopes", "modifiers", "on_actions",
                  "custom_localizations", "data_types"):
        cursor.execute(f"DELETE FROM {table}")
    conn.commit()

    # Effects
    if verbose:
        print("Parsing effects...")
    content = _read_file(docs_dir, "effects.log")
    if content:
        for e in parse_effects_log(content):
            cursor.execute("""
                INSERT INTO effects (name, category, description, scope_type, parameters, added_version, source_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                e["name"],
                categorize_item(e["name"]),
                e["description"],
                e["scope_type"],
                e["parameters"],
                version,
                source_id,
            ))
            stats["effects"] += 1
        conn.commit()

    # Triggers
    if verbose:
        print("Parsing triggers...")
    content = _read_file(docs_dir, "triggers.log")
    if content:
        for t in parse_triggers_log(content):
            cursor.execute("""
                INSERT INTO triggers (name, category, description, scope_type, parameters, added_version, source_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                t["name"],
                categorize_item(t["name"]),
                t["description"],
                t["scope_type"],
                t["parameters"],
                version,
                source_id,
            ))
            stats["triggers"] += 1
        conn.commit()

    # Modifiers
    if verbose:
        print("Parsing modifiers...")
    content = _read_file(docs_dir, "modifiers.log")
    if content:
        for m in parse_modifiers_log(content):
            log_cat = m["categories"][0].lower() if m["categories"] else ""
            category = log_cat or categorize_modifier(m["name"])
            cursor.execute("""
                INSERT INTO modifiers (name, category, added_version, source_id)
                VALUES (?, ?, ?, ?)
            """, (
                m["name"],
                category,
                version,
                source_id,
            ))
            stats["modifiers"] += 1
        conn.commit()

    # On Actions
    if verbose:
        print("Parsing on_actions...")
    content = _read_file(docs_dir, "on_actions.log")
    if content:
        for oa in parse_on_actions_log(content):
            cursor.execute("""
                INSERT INTO on_actions (name, category, scope_type, added_version, source_id)
                VALUES (?, ?, ?, ?, ?)
            """, (
                oa["name"],
                categorize_on_action(oa["name"]),
                oa["scope_type"],
                version,
                source_id,
            ))
            stats["on_actions"] += 1
        conn.commit()

    # Event Targets / Scopes
    if verbose:
        print("Parsing event targets / scopes...")
    content = _read_file(docs_dir, "event_targets.log")
    if content:
        for et in parse_event_targets_log(content):
            is_iter, iter_type = _detect_iterator(et["name"])
            cursor.execute("""
                INSERT INTO scopes
                (name, scope_type, target_type, description, is_iterator, iterator_type, added_version, source_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                et["name"],
                et["input_scopes"],
                et["output_scopes"],
                et["description"],
                1 if is_iter else 0,
                iter_type,
                version,
                source_id,
            ))
            stats["scopes"] += 1
        conn.commit()

    # Cross-populate iterators from effects/triggers into scopes table
    if verbose:
        print("Cross-populating iterators into scopes...")
    existing_scope_names = {
        r[0] for r in cursor.execute("SELECT name FROM scopes").fetchall()
    }
    for table, iter_types in [("effects", {"every_": "effect", "random_": "effect_random", "ordered_": "effect_ordered"}),
                               ("triggers", {"any_": "trigger"})]:
        rows = cursor.execute(f"SELECT name, description, scope_type, parameters FROM {table}").fetchall()
        for row in rows:
            name = row[0]
            if name in existing_scope_names:
                continue
            for prefix, itype in iter_types.items():
                if name.startswith(prefix):
                    cursor.execute("""
                        INSERT INTO scopes
                        (name, scope_type, target_type, description, is_iterator, iterator_type, added_version, source_id)
                        VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                    """, (name, row[2], row[3], row[1], itype, version, source_id))
                    existing_scope_names.add(name)
                    stats["scopes"] += 1
                    break
    conn.commit()

    # Custom Localizations
    if verbose:
        print("Parsing custom localizations...")
    content = _read_file(docs_dir, "custom_localization.log")
    if content:
        for cl in parse_custom_localization_log(content):
            cursor.execute("""
                INSERT INTO custom_localizations (name, scope, random_valid, entries, added_version, source_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                cl["name"],
                cl["scope"],
                1 if cl["random_valid"] else 0,
                cl["entries"],
                version,
                source_id,
            ))
            stats["custom_localizations"] += 1
        conn.commit()

    # Data Types (from separate directory)
    if verbose:
        print("Parsing data types...")
    _DATA_TYPE_FILES = {
        "data_types_script.txt": "script",
        "data_types_gui.txt": "gui",
        "data_types_common.txt": "common",
        "data_types_uncategorized.txt": "uncategorized",
        "data_types_internalclausewitzgui.txt": "internal_gui",
    }
    dt_dir = data_types_dir if data_types_dir.is_dir() else docs_dir
    for filename, source_cat in _DATA_TYPE_FILES.items():
        content = _read_file(dt_dir, filename)
        if content:
            for dt in parse_data_types(content):
                cursor.execute("""
                    INSERT INTO data_types
                    (name, parent_type, args, description, definition_type, return_type, source_category, added_version, source_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    dt["name"],
                    dt["parent_type"],
                    dt["args"],
                    dt["description"],
                    dt["definition_type"],
                    dt["return_type"],
                    source_cat,
                    version,
                    source_id,
                ))
                stats["data_types"] += 1
            conn.commit()

    # Enrich from initial_data.py
    if verbose:
        print("Enriching with seed data...")
    _enrich_from_seed(cursor, source_id)
    conn.commit()

    conn.close()

    # Rebuild FTS
    if verbose:
        print("Rebuilding search indexes...")
    rebuild_fts_indexes(db_path)

    # Record what this DB was built against so the CLI can warn when the
    # game patches and the dumps go stale.
    checksum = read_game_checksum()
    if checksum:
        set_meta("game_checksum_at_update", checksum, db_path)
    set_meta("game_version_at_update", version, db_path)
    set_meta("updated_at", datetime.now().isoformat(timespec="seconds"), db_path)

    return stats


def _detect_game_version(docs_dir: Path) -> str:
    """Try to detect the game version from continue_game.json, fall back to 'unknown'."""
    continue_game = docs_dir.parent / "continue_game.json"
    if continue_game.is_file():
        import json
        try:
            data = json.loads(continue_game.read_text(encoding="utf-8", errors="replace"))
            if "rawGameVersion" in data:
                return data["rawGameVersion"]
        except (json.JSONDecodeError, KeyError):
            pass
    return "unknown"


def _enrich_from_seed(cursor, source_id: int) -> None:
    """Overlay examples/syntax from initial_data onto digest-parsed rows."""
    from ..data.initial_data import (
        EFFECTS,
        FLOW_TRIGGERS,
        VARIABLE_TRIGGERS,
        GAME_STATE_TRIGGERS,
        ITERATOR_SCOPES,
        ON_ACTIONS,
        MODIFIERS,
        SYNTAX_TEMPLATES,
        SCOPE_TYPES,
    )

    # Enrich effects
    for e in EFFECTS:
        cursor.execute(
            "UPDATE effects SET syntax = COALESCE(NULLIF(syntax, ''), ?), "
            "example = COALESCE(NULLIF(example, ''), ?), "
            "parameters = COALESCE(NULLIF(parameters, ''), ?) "
            "WHERE name = ?",
            (e.get("syntax", ""), e.get("example", ""), e.get("parameters", ""), e["name"]),
        )
        # Insert if not present from digest
        cursor.execute("""
            INSERT OR IGNORE INTO effects (name, category, description, syntax, scope_type, parameters, example, source_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            e["name"], e.get("category"), e.get("description"), e.get("syntax"),
            e.get("scope_type"), e.get("parameters"), e.get("example"), source_id,
        ))

    # Enrich triggers
    for t in FLOW_TRIGGERS + VARIABLE_TRIGGERS + GAME_STATE_TRIGGERS:
        cursor.execute(
            "UPDATE triggers SET syntax = COALESCE(NULLIF(syntax, ''), ?), "
            "example = COALESCE(NULLIF(example, ''), ?), "
            "parameters = COALESCE(NULLIF(parameters, ''), ?) "
            "WHERE name = ?",
            (t.get("syntax", ""), t.get("example", ""), t.get("parameters", ""), t["name"]),
        )
        cursor.execute("""
            INSERT OR IGNORE INTO triggers (name, category, description, syntax, scope_type, parameters, example, source_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            t["name"], t.get("category"), t.get("description"), t.get("syntax"),
            t.get("scope_type"), t.get("parameters"), t.get("example"), source_id,
        ))

    # Enrich scopes / iterators
    for s in ITERATOR_SCOPES:
        cursor.execute(
            "UPDATE scopes SET syntax = COALESCE(NULLIF(syntax, ''), ?), "
            "example = COALESCE(NULLIF(example, ''), ?), "
            "parameters = COALESCE(NULLIF(parameters, ''), ?) "
            "WHERE name = ?",
            (s.get("syntax", ""), s.get("example", ""), s.get("parameters", ""), s["name"]),
        )
        cursor.execute("""
            INSERT OR IGNORE INTO scopes
            (name, scope_type, target_type, description, syntax, parameters, example, is_iterator, iterator_type, source_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            s["name"], s.get("scope_type"), s.get("target_type"), s.get("description"),
            s.get("syntax"), s.get("parameters"), s.get("example"),
            s.get("is_iterator", 0), s.get("iterator_type"), source_id,
        ))

    # Enrich modifiers
    for m in MODIFIERS:
        cursor.execute(
            "UPDATE modifiers SET description = COALESCE(NULLIF(description, ''), ?), "
            "modifier_type = COALESCE(NULLIF(modifier_type, ''), ?), "
            "scope_type = COALESCE(NULLIF(scope_type, ''), ?), "
            "syntax = COALESCE(NULLIF(syntax, ''), ?), "
            "parameters = COALESCE(NULLIF(parameters, ''), ?) "
            "WHERE name = ?",
            (
                m.get("description", ""), m.get("modifier_type", ""),
                m.get("scope_type", ""), m.get("syntax", ""),
                m.get("parameters", ""), m["name"],
            ),
        )
        cursor.execute("""
            INSERT OR IGNORE INTO modifiers
            (name, category, description, modifier_type, scope_type, is_boolean, default_value, color, percent, syntax, parameters, source_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            m["name"], m.get("category"), m.get("description"), m.get("modifier_type"),
            m.get("scope_type"), m.get("is_boolean", 0), m.get("default_value"),
            m.get("color"), m.get("percent", 0), m.get("syntax"), m.get("parameters"),
            source_id,
        ))

    # Enrich on_actions
    for oa in ON_ACTIONS:
        cursor.execute(
            "UPDATE on_actions SET description = COALESCE(NULLIF(description, ''), ?), "
            "syntax = COALESCE(NULLIF(syntax, ''), ?), "
            "parameters = COALESCE(NULLIF(parameters, ''), ?) "
            "WHERE name = ?",
            (oa.get("description", ""), oa.get("syntax", ""), oa.get("parameters", ""), oa["name"]),
        )
        cursor.execute("""
            INSERT OR IGNORE INTO on_actions (name, category, description, scope_type, syntax, parameters, source_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            oa["name"], oa.get("category"), oa.get("description"),
            oa.get("scope_type"), oa.get("syntax"), oa.get("parameters"), source_id,
        ))

    # Seed templates (these don't come from digests at all)
    for tmpl in SYNTAX_TEMPLATES:
        cursor.execute("""
            INSERT OR REPLACE INTO syntax_templates (name, category, template, description, parameters, source_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            tmpl["name"], tmpl.get("category"), tmpl.get("template"),
            tmpl.get("description"), tmpl.get("parameters"), source_id,
        ))

    # Seed scope types
    for st in SCOPE_TYPES:
        cursor.execute("""
            INSERT OR REPLACE INTO scope_types (name, description)
            VALUES (?, ?)
        """, (st["name"], st["description"]))
