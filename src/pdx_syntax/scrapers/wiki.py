"""Scraper for EU5 Wiki data."""

import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from ..database import (
    get_connection,
    init_database,
    record_data_source,
    rebuild_fts_indexes,
)
from .rate_limiter import get_rate_limiter


# Wiki URLs to scrape
WIKI_URLS = {
    "effects": "https://eu5.paradoxwikis.com/Effect",
    "triggers": "https://eu5.paradoxwikis.com/Trigger",
    "scopes": "https://eu5.paradoxwikis.com/Scope",
    "modifiers": "https://eu5.paradoxwikis.com/Modifier_types",
    "modifier_modding": "https://eu5.paradoxwikis.com/Modifier_modding",
    "on_actions": "https://eu5.paradoxwikis.com/On_actions",
    "events": "https://eu5.paradoxwikis.com/Event_modding",
    "actions": "https://eu5.paradoxwikis.com/Action_modding",
    "macros": "https://eu5.paradoxwikis.com/Macro",
    "modding": "https://eu5.paradoxwikis.com/Modding",
}

# Modding digests repo
DIGESTS_BASE = "https://raw.githubusercontent.com/Europa-Universalis-5-Modding-Co-op/modding-digests/main"
DIGEST_VERSIONS = ["1.0.0", "1.0.2", "1.0.3", "1.0.4", "1.0.5", "1.0.7", "1.0.8", "1.0.9", "1.0.10", "1.1.0"]


def fetch_url(url: str, timeout: float = 30.0) -> Optional[str]:
    """
    Fetch a URL with rate limiting.

    Returns the response text or None if request fails.
    """
    rate_limiter = get_rate_limiter()
    domain = urlparse(url).netloc

    # Wait if needed
    waited = rate_limiter.wait_if_needed(domain)
    if waited > 0:
        print(f"  Rate limited: waited {waited:.1f}s for {domain}")

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            rate_limiter.record_request(domain)
            return response.text
    except httpx.HTTPError as e:
        print(f"  Error fetching {url}: {e}")
        return None


def parse_wiki_table(soup: BeautifulSoup, table_class: Optional[str] = None) -> list[dict]:
    """Parse a wiki table into a list of dictionaries."""
    results = []

    tables = soup.find_all("table", class_=table_class) if table_class else soup.find_all("table")

    for table in tables:
        headers = []
        header_row = table.find("tr")
        if header_row:
            for th in header_row.find_all(["th", "td"]):
                headers.append(th.get_text(strip=True).lower().replace(" ", "_"))

        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) >= len(headers):
                row_data = {}
                for i, header in enumerate(headers):
                    if i < len(cells):
                        row_data[header] = cells[i].get_text(strip=True)
                if row_data:
                    results.append(row_data)

    return results


def parse_effect_page(html: str) -> list[dict]:
    """Parse the effects wiki page."""
    soup = BeautifulSoup(html, "lxml")
    effects = []

    # Find all effect definitions in tables
    tables = parse_wiki_table(soup)

    for row in tables:
        effect = {
            "name": row.get("name", row.get("effect", "")),
            "description": row.get("description", row.get("desc", "")),
            "scope_type": row.get("scope", row.get("supported_scopes", "none")),
            "syntax": row.get("syntax", row.get("usage", "")),
            "parameters": row.get("parameters", row.get("supported_targets", "")),
        }
        if effect["name"]:
            effects.append(effect)

    # Also extract from definition lists and code blocks
    for dt in soup.find_all("dt"):
        name = dt.get_text(strip=True)
        dd = dt.find_next_sibling("dd")
        if dd and name:
            effects.append({
                "name": name,
                "description": dd.get_text(strip=True),
                "scope_type": "none",
            })

    return effects


def parse_trigger_page(html: str) -> list[dict]:
    """Parse the triggers wiki page."""
    soup = BeautifulSoup(html, "lxml")
    triggers = []

    tables = parse_wiki_table(soup)

    for row in tables:
        trigger = {
            "name": row.get("name", row.get("trigger", "")),
            "description": row.get("description", row.get("desc", "")),
            "scope_type": row.get("scope", row.get("supported_scopes", "none")),
            "syntax": row.get("syntax", row.get("usage", "")),
            "parameters": row.get("parameters", ""),
        }
        if trigger["name"]:
            triggers.append(trigger)

    return triggers


def parse_scope_page(html: str) -> list[dict]:
    """Parse the scopes wiki page."""
    soup = BeautifulSoup(html, "lxml")
    scopes = []

    tables = parse_wiki_table(soup)

    for row in tables:
        name = row.get("name", row.get("scope", ""))
        is_iterator = name.startswith(("any_", "every_", "random_", "ordered_"))
        iterator_type = None
        if is_iterator:
            if name.startswith("any_"):
                iterator_type = "trigger"
            elif name.startswith("every_"):
                iterator_type = "effect"
            elif name.startswith("random_"):
                iterator_type = "effect_random"
            elif name.startswith("ordered_"):
                iterator_type = "effect_ordered"

        scope = {
            "name": name,
            "description": row.get("description", row.get("desc", "")),
            "scope_type": row.get("input_scopes", row.get("scope", "none")),
            "target_type": row.get("output_scope", row.get("targets", "")),
            "is_iterator": 1 if is_iterator else 0,
            "iterator_type": iterator_type,
            "syntax": row.get("syntax", ""),
            "parameters": row.get("parameters", ""),
        }
        if scope["name"]:
            scopes.append(scope)

    return scopes


def parse_modifier_page(html: str) -> list[dict]:
    """Parse the modifiers wiki page."""
    soup = BeautifulSoup(html, "lxml")
    modifiers = []

    tables = parse_wiki_table(soup)

    for row in tables:
        name = row.get("name", row.get("modifier", ""))
        is_boolean = "yes" in row.get("boolean", "").lower() or "bool" in row.get("type", "").lower()

        modifier = {
            "name": name,
            "description": row.get("description", row.get("desc", "")),
            "category": row.get("category", row.get("type", "")),
            "scope_type": row.get("scope", ""),
            "modifier_type": row.get("type", row.get("modifier_type", "")),
            "is_boolean": 1 if is_boolean else 0,
            "default_value": row.get("default", row.get("default_value", "")),
            "color": row.get("color", ""),
            "percent": 1 if "yes" in row.get("percent", "").lower() else 0,
        }
        if modifier["name"]:
            modifiers.append(modifier)

    return modifiers


def parse_on_actions_page(html: str) -> list[dict]:
    """Parse the on_actions wiki page."""
    soup = BeautifulSoup(html, "lxml")
    on_actions = []

    tables = parse_wiki_table(soup)

    for row in tables:
        on_action = {
            "name": row.get("name", row.get("on_action", "")),
            "description": row.get("description", row.get("desc", "")),
            "scope_type": row.get("scope", row.get("root_scope", "")),
            "parameters": row.get("parameters", row.get("scopes", "")),
        }
        if on_action["name"]:
            on_actions.append(on_action)

    # Also look for headers and lists describing on_actions
    for h3 in soup.find_all(["h2", "h3", "h4"]):
        name = h3.get_text(strip=True)
        if name.startswith("on_") or "_pulse" in name:
            # Get description from following paragraph
            desc = ""
            next_elem = h3.find_next_sibling()
            if next_elem and next_elem.name == "p":
                desc = next_elem.get_text(strip=True)

            on_actions.append({
                "name": name,
                "description": desc,
                "scope_type": "",
                "parameters": "",
            })

    return on_actions


def parse_digest(content: str, version: str) -> list[dict]:
    """Parse a modding digest for changes."""
    changes = []

    # Look for breaking changes section
    lines = content.split("\n")
    current_section = ""

    for line in lines:
        line = line.strip()

        if line.startswith("##"):
            current_section = line.lstrip("#").strip().lower()
            continue

        if not line or line.startswith("---"):
            continue

        # Parse change entries
        if ":" in line and current_section:
            parts = line.split(":", 1)
            if len(parts) == 2:
                item_name = parts[0].strip().strip("-*")
                description = parts[1].strip().strip('"')

                change_type = "modified"
                if "removed" in description.lower() or "deleted" in description.lower():
                    change_type = "removed"
                elif "added" in description.lower() or "new" in description.lower():
                    change_type = "added"
                elif "changed" in description.lower() or "replaced" in description.lower():
                    change_type = "modified"

                changes.append({
                    "game_version": version,
                    "change_type": change_type,
                    "item_type": current_section,
                    "item_name": item_name,
                    "description": description,
                    "recorded_at": datetime.now().isoformat(),
                })

    return changes


def update_from_wiki(db_path: Optional[Path] = None, force: bool = False) -> dict:
    """
    Update the database from wiki sources.

    Returns statistics about the update.
    """
    init_database(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()

    stats = {
        "effects": 0,
        "triggers": 0,
        "scopes": 0,
        "modifiers": 0,
        "on_actions": 0,
        "changes": 0,
    }

    # Check if we've updated recently (within 1 hour)
    if not force:
        cursor.execute(
            "SELECT MAX(fetched_at) FROM data_sources WHERE source_type = 'wiki'"
        )
        row = cursor.fetchone()
        if row and row[0]:
            last_fetch = datetime.fromisoformat(row[0])
            if datetime.now() - last_fetch < timedelta(hours=1):
                print("Database updated within the last hour. Use --force to update anyway.")
                conn.close()
                return stats

    # Fetch and parse effects
    print("Fetching effects...")
    html = fetch_url(WIKI_URLS["effects"])
    if html:
        source_id = record_data_source(WIKI_URLS["effects"], "wiki", db_path=db_path)
        effects = parse_effect_page(html)
        for effect in effects:
            cursor.execute("""
                INSERT OR REPLACE INTO effects (name, category, description, syntax, scope_type, parameters, source_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                effect.get("name"),
                effect.get("category"),
                effect.get("description"),
                effect.get("syntax"),
                effect.get("scope_type"),
                effect.get("parameters"),
                source_id,
            ))
        stats["effects"] = len(effects)
        conn.commit()

    # Fetch and parse triggers
    print("Fetching triggers...")
    html = fetch_url(WIKI_URLS["triggers"])
    if html:
        source_id = record_data_source(WIKI_URLS["triggers"], "wiki", db_path=db_path)
        triggers = parse_trigger_page(html)
        for trigger in triggers:
            cursor.execute("""
                INSERT OR REPLACE INTO triggers (name, category, description, syntax, scope_type, parameters, source_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                trigger.get("name"),
                trigger.get("category"),
                trigger.get("description"),
                trigger.get("syntax"),
                trigger.get("scope_type"),
                trigger.get("parameters"),
                source_id,
            ))
        stats["triggers"] = len(triggers)
        conn.commit()

    # Fetch and parse scopes
    print("Fetching scopes...")
    html = fetch_url(WIKI_URLS["scopes"])
    if html:
        source_id = record_data_source(WIKI_URLS["scopes"], "wiki", db_path=db_path)
        scopes = parse_scope_page(html)
        for scope in scopes:
            cursor.execute("""
                INSERT OR REPLACE INTO scopes
                (name, scope_type, target_type, description, syntax, parameters, is_iterator, iterator_type, source_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                scope.get("name"),
                scope.get("scope_type"),
                scope.get("target_type"),
                scope.get("description"),
                scope.get("syntax"),
                scope.get("parameters"),
                scope.get("is_iterator"),
                scope.get("iterator_type"),
                source_id,
            ))
        stats["scopes"] = len(scopes)
        conn.commit()

    # Fetch and parse modifiers
    print("Fetching modifiers...")
    html = fetch_url(WIKI_URLS["modifiers"])
    if html:
        source_id = record_data_source(WIKI_URLS["modifiers"], "wiki", db_path=db_path)
        modifiers = parse_modifier_page(html)
        for modifier in modifiers:
            cursor.execute("""
                INSERT OR REPLACE INTO modifiers
                (name, category, description, modifier_type, scope_type, is_boolean, default_value, color, percent, source_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                modifier.get("name"),
                modifier.get("category"),
                modifier.get("description"),
                modifier.get("modifier_type"),
                modifier.get("scope_type"),
                modifier.get("is_boolean"),
                modifier.get("default_value"),
                modifier.get("color"),
                modifier.get("percent"),
                source_id,
            ))
        stats["modifiers"] = len(modifiers)
        conn.commit()

    # Fetch and parse on_actions
    print("Fetching on_actions...")
    html = fetch_url(WIKI_URLS["on_actions"])
    if html:
        source_id = record_data_source(WIKI_URLS["on_actions"], "wiki", db_path=db_path)
        on_actions = parse_on_actions_page(html)
        for on_action in on_actions:
            cursor.execute("""
                INSERT OR REPLACE INTO on_actions (name, category, description, scope_type, parameters, source_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                on_action.get("name"),
                on_action.get("category"),
                on_action.get("description"),
                on_action.get("scope_type"),
                on_action.get("parameters"),
                source_id,
            ))
        stats["on_actions"] = len(on_actions)
        conn.commit()

    # Fetch modding digests for version changes
    print("Fetching modding digests...")
    for version in DIGEST_VERSIONS:
        url = f"{DIGESTS_BASE}/{version}/discord.md"
        content = fetch_url(url)
        if content:
            source_id = record_data_source(url, "digest", game_version=version, db_path=db_path)
            changes = parse_digest(content, version)
            for change in changes:
                cursor.execute("""
                    INSERT INTO change_log
                    (game_version, change_type, item_type, item_name, description, recorded_at, source_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    change["game_version"],
                    change["change_type"],
                    change["item_type"],
                    change["item_name"],
                    change["description"],
                    change["recorded_at"],
                    source_id,
                ))
            stats["changes"] += len(changes)
            conn.commit()

    conn.close()

    # Rebuild FTS indexes
    print("Rebuilding search indexes...")
    rebuild_fts_indexes(db_path)

    return stats


def get_rate_limit_status() -> dict:
    """Get current rate limit status."""
    rate_limiter = get_rate_limiter()
    return {
        "paradoxwikis.com": rate_limiter.get_stats("eu5.paradoxwikis.com"),
        "github.com": rate_limiter.get_stats("raw.githubusercontent.com"),
    }
