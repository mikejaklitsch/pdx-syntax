"""Comprehensive scraper for EU5 wiki script documentation.

This module provides thorough scraping of the EU5 wiki to collect
all effects, triggers, scopes, and modifiers.
"""

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from ..database import get_connection, init_database, record_data_source, rebuild_fts_indexes
from .rate_limiter import get_rate_limiter

BASE_URL = "https://eu5.paradoxwikis.com"

# Raw module URLs for script docs
MODULE_URLS = {
    "effects": f"{BASE_URL}/index.php?title=Module:Script_docs/Effects&action=raw",
    "triggers": f"{BASE_URL}/index.php?title=Module:Script_docs/Triggers&action=raw",
}

# Wiki pages with tables
WIKI_PAGES = {
    "effects": f"{BASE_URL}/Effect",
    "triggers": f"{BASE_URL}/Trigger",
    "scopes": f"{BASE_URL}/Scope",
    "modifiers": f"{BASE_URL}/Modifier_types",
    "on_actions": f"{BASE_URL}/On_actions",
}


def fetch_with_retry(url: str, max_retries: int = 3, timeout: float = 60.0) -> Optional[str]:
    """Fetch a URL with retry logic and rate limiting."""
    rate_limiter = get_rate_limiter()
    domain = "eu5.paradoxwikis.com"

    for attempt in range(max_retries):
        # Wait for rate limit
        wait_time = rate_limiter.wait_if_needed(domain)
        if wait_time > 0:
            print(f"  Rate limited, waited {wait_time:.1f}s")

        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                rate_limiter.record_request(domain)
                return response.text
        except httpx.TimeoutException:
            print(f"  Timeout on attempt {attempt + 1}/{max_retries}")
            time.sleep(2 ** attempt)  # Exponential backoff
        except httpx.HTTPError as e:
            print(f"  HTTP error on attempt {attempt + 1}/{max_retries}: {e}")
            if attempt == max_retries - 1:
                return None
            time.sleep(2 ** attempt)

    return None


def parse_lua_module(content: str) -> list[dict]:
    """Parse a Lua module file to extract script documentation entries."""
    entries = []

    # Pattern to match Lua table entries like: ["effect_name"] = { ... }
    # This is a simplified parser - the actual format is more complex
    pattern = r'\["([^"]+)"\]\s*=\s*\{([^}]+)\}'

    for match in re.finditer(pattern, content, re.DOTALL):
        name = match.group(1)
        body = match.group(2)

        entry = {"name": name}

        # Extract description
        desc_match = re.search(r'desc\s*=\s*"([^"]*)"', body)
        if desc_match:
            entry["description"] = desc_match.group(1)

        # Extract scopes
        scopes_match = re.search(r'scopes\s*=\s*\{([^}]*)\}', body)
        if scopes_match:
            entry["scope_type"] = scopes_match.group(1).strip()

        # Extract targets
        targets_match = re.search(r'targets\s*=\s*\{([^}]*)\}', body)
        if targets_match:
            entry["target_type"] = targets_match.group(1).strip()

        entries.append(entry)

    return entries


def parse_wiki_tables(html: str, item_type: str) -> list[dict]:
    """Parse wiki HTML to extract items from tables."""
    soup = BeautifulSoup(html, "lxml")
    items = []

    # Find all tables
    for table in soup.find_all("table", class_="wikitable"):
        # Get headers
        headers = []
        header_row = table.find("tr")
        if header_row:
            for th in header_row.find_all(["th", "td"]):
                header_text = th.get_text(strip=True).lower()
                # Normalize header names
                header_text = header_text.replace(" ", "_")
                headers.append(header_text)

        # Process data rows
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 1:
                item = {}
                for i, cell in enumerate(cells):
                    if i < len(headers):
                        text = cell.get_text(strip=True)
                        # Get code blocks if present
                        code = cell.find("code")
                        if code:
                            text = code.get_text(strip=True)
                        item[headers[i]] = text

                # Normalize field names
                if "name" not in item and "effect" in item:
                    item["name"] = item["effect"]
                if "name" not in item and "trigger" in item:
                    item["name"] = item["trigger"]
                if "name" not in item and "scope" in item:
                    item["name"] = item["scope"]
                if "name" not in item and "modifier" in item:
                    item["name"] = item["modifier"]

                if item.get("name"):
                    items.append(item)

    # Also look for definition lists (dt/dd pairs)
    for dt in soup.find_all("dt"):
        name = dt.get_text(strip=True)
        if name and not name.startswith(("↑", "^")):
            dd = dt.find_next_sibling("dd")
            description = dd.get_text(strip=True) if dd else ""
            items.append({"name": name, "description": description})

    return items


def extract_all_names_from_html(html: str) -> set[str]:
    """Extract all potential effect/trigger/scope names from HTML."""
    soup = BeautifulSoup(html, "lxml")
    names = set()

    # Look in code blocks
    for code in soup.find_all("code"):
        text = code.get_text(strip=True)
        # Match patterns like effect_name, any_*, every_*, etc.
        if re.match(r'^[a-z][a-z0-9_]*$', text) and len(text) > 2:
            names.add(text)

    # Look in table cells
    for td in soup.find_all("td"):
        text = td.get_text(strip=True)
        if re.match(r'^[a-z][a-z0-9_]*$', text) and len(text) > 2:
            names.add(text)

    # Look in definition terms
    for dt in soup.find_all("dt"):
        text = dt.get_text(strip=True)
        if re.match(r'^[a-z][a-z0-9_]*$', text) and len(text) > 2:
            names.add(text)

    return names


def comprehensive_update(db_path: Optional[Path] = None, verbose: bool = True) -> dict:
    """
    Perform a comprehensive update of the database from all wiki sources.

    This fetches data from multiple pages and consolidates it.
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
    }

    # Fetch and parse effects
    if verbose:
        print("Fetching effects...")

    effect_names = set()

    # From wiki page
    html = fetch_with_retry(WIKI_PAGES["effects"])
    if html:
        source_id = record_data_source(WIKI_PAGES["effects"], "wiki", db_path=db_path)
        items = parse_wiki_tables(html, "effects")
        names = extract_all_names_from_html(html)
        effect_names.update(names)

        for item in items:
            effect_names.add(item.get("name", ""))
            if item.get("name"):
                cursor.execute("""
                    INSERT OR REPLACE INTO effects
                    (name, category, description, syntax, scope_type, parameters, source_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.get("name"),
                    categorize_item(item.get("name", "")),
                    item.get("description", item.get("desc", "")),
                    item.get("syntax", item.get("usage", "")),
                    item.get("scope_type", item.get("scopes", item.get("supported_scopes", ""))),
                    item.get("parameters", item.get("targets", "")),
                    source_id,
                ))
        conn.commit()

    # From raw module
    lua_content = fetch_with_retry(MODULE_URLS["effects"])
    if lua_content:
        source_id = record_data_source(MODULE_URLS["effects"], "module", db_path=db_path)
        entries = parse_lua_module(lua_content)

        for entry in entries:
            effect_names.add(entry.get("name", ""))
            if entry.get("name"):
                cursor.execute("""
                    INSERT OR IGNORE INTO effects
                    (name, category, description, scope_type, source_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    entry.get("name"),
                    categorize_item(entry.get("name", "")),
                    entry.get("description", ""),
                    entry.get("scope_type", ""),
                    source_id,
                ))
        conn.commit()

    # Insert any remaining names found
    for name in effect_names:
        if name:
            cursor.execute("""
                INSERT OR IGNORE INTO effects (name, category, source_id)
                VALUES (?, ?, ?)
            """, (name, categorize_item(name), source_id if 'source_id' in dir() else None))

    cursor.execute("SELECT COUNT(*) FROM effects")
    stats["effects"] = cursor.fetchone()[0]
    conn.commit()

    # Fetch and parse triggers
    if verbose:
        print("Fetching triggers...")

    trigger_names = set()

    html = fetch_with_retry(WIKI_PAGES["triggers"])
    if html:
        source_id = record_data_source(WIKI_PAGES["triggers"], "wiki", db_path=db_path)
        items = parse_wiki_tables(html, "triggers")
        names = extract_all_names_from_html(html)
        trigger_names.update(names)

        for item in items:
            trigger_names.add(item.get("name", ""))
            if item.get("name"):
                cursor.execute("""
                    INSERT OR REPLACE INTO triggers
                    (name, category, description, syntax, scope_type, parameters, source_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.get("name"),
                    categorize_item(item.get("name", "")),
                    item.get("description", item.get("desc", "")),
                    item.get("syntax", item.get("usage", "")),
                    item.get("scope_type", item.get("scopes", item.get("supported_scopes", ""))),
                    item.get("parameters", ""),
                    source_id,
                ))
        conn.commit()

    # From raw module
    lua_content = fetch_with_retry(MODULE_URLS["triggers"])
    if lua_content:
        source_id = record_data_source(MODULE_URLS["triggers"], "module", db_path=db_path)
        entries = parse_lua_module(lua_content)

        for entry in entries:
            trigger_names.add(entry.get("name", ""))
            if entry.get("name"):
                cursor.execute("""
                    INSERT OR IGNORE INTO triggers
                    (name, category, description, scope_type, source_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    entry.get("name"),
                    categorize_item(entry.get("name", "")),
                    entry.get("description", ""),
                    entry.get("scope_type", ""),
                    source_id,
                ))
        conn.commit()

    for name in trigger_names:
        if name:
            cursor.execute("""
                INSERT OR IGNORE INTO triggers (name, category)
                VALUES (?, ?)
            """, (name, categorize_item(name)))

    cursor.execute("SELECT COUNT(*) FROM triggers")
    stats["triggers"] = cursor.fetchone()[0]
    conn.commit()

    # Fetch and parse scopes
    if verbose:
        print("Fetching scopes...")

    html = fetch_with_retry(WIKI_PAGES["scopes"])
    if html:
        source_id = record_data_source(WIKI_PAGES["scopes"], "wiki", db_path=db_path)
        items = parse_wiki_tables(html, "scopes")
        names = extract_all_names_from_html(html)

        for name in names:
            is_iterator = name.startswith(("any_", "every_", "random_", "ordered_"))
            iterator_type = None
            if name.startswith("any_"):
                iterator_type = "trigger"
            elif name.startswith("every_"):
                iterator_type = "effect"
            elif name.startswith("random_"):
                iterator_type = "effect_random"
            elif name.startswith("ordered_"):
                iterator_type = "effect_ordered"

            cursor.execute("""
                INSERT OR IGNORE INTO scopes
                (name, is_iterator, iterator_type, source_id)
                VALUES (?, ?, ?, ?)
            """, (name, 1 if is_iterator else 0, iterator_type, source_id))

        for item in items:
            name = item.get("name", "")
            if name:
                is_iterator = name.startswith(("any_", "every_", "random_", "ordered_"))
                cursor.execute("""
                    INSERT OR REPLACE INTO scopes
                    (name, scope_type, target_type, description, is_iterator, source_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    name,
                    item.get("input_scopes", item.get("scope_type", "")),
                    item.get("output_scope", item.get("target_type", "")),
                    item.get("description", ""),
                    1 if is_iterator else 0,
                    source_id,
                ))
        conn.commit()

    cursor.execute("SELECT COUNT(*) FROM scopes")
    stats["scopes"] = cursor.fetchone()[0]

    # Fetch and parse modifiers
    if verbose:
        print("Fetching modifiers...")

    html = fetch_with_retry(WIKI_PAGES["modifiers"])
    if html:
        source_id = record_data_source(WIKI_PAGES["modifiers"], "wiki", db_path=db_path)
        items = parse_wiki_tables(html, "modifiers")
        names = extract_all_names_from_html(html)

        for name in names:
            cursor.execute("""
                INSERT OR IGNORE INTO modifiers (name, category)
                VALUES (?, ?)
            """, (name, categorize_modifier(name)))

        for item in items:
            if item.get("name"):
                is_boolean = "bool" in item.get("type", "").lower() or item.get("boolean", "") == "yes"
                cursor.execute("""
                    INSERT OR REPLACE INTO modifiers
                    (name, category, description, modifier_type, scope_type, is_boolean, source_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.get("name"),
                    categorize_modifier(item.get("name", "")),
                    item.get("description", ""),
                    item.get("type", item.get("modifier_type", "")),
                    item.get("scope", ""),
                    1 if is_boolean else 0,
                    source_id,
                ))
        conn.commit()

    cursor.execute("SELECT COUNT(*) FROM modifiers")
    stats["modifiers"] = cursor.fetchone()[0]

    # Fetch and parse on_actions
    if verbose:
        print("Fetching on_actions...")

    html = fetch_with_retry(WIKI_PAGES["on_actions"])
    if html:
        source_id = record_data_source(WIKI_PAGES["on_actions"], "wiki", db_path=db_path)
        items = parse_wiki_tables(html, "on_actions")
        names = extract_all_names_from_html(html)

        for name in names:
            if name.startswith("on_") or "_pulse" in name:
                cursor.execute("""
                    INSERT OR IGNORE INTO on_actions (name, category)
                    VALUES (?, ?)
                """, (name, categorize_on_action(name)))

        for item in items:
            if item.get("name"):
                cursor.execute("""
                    INSERT OR REPLACE INTO on_actions
                    (name, category, description, scope_type, parameters, source_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    item.get("name"),
                    categorize_on_action(item.get("name", "")),
                    item.get("description", ""),
                    item.get("scope_type", item.get("root_scope", "")),
                    item.get("parameters", item.get("scopes", "")),
                    source_id,
                ))
        conn.commit()

    cursor.execute("SELECT COUNT(*) FROM on_actions")
    stats["on_actions"] = cursor.fetchone()[0]

    conn.close()

    # Rebuild FTS indexes
    if verbose:
        print("Rebuilding search indexes...")
    rebuild_fts_indexes(db_path)

    return stats


def categorize_item(name: str) -> str:
    """Categorize an effect or trigger by its name pattern."""
    if name.startswith("any_"):
        return "iterator_trigger"
    elif name.startswith("every_"):
        return "iterator_effect"
    elif name.startswith("random_"):
        return "iterator_random"
    elif name.startswith("ordered_"):
        return "iterator_ordered"
    elif name.startswith("add_"):
        return "add"
    elif name.startswith("remove_"):
        return "remove"
    elif name.startswith("set_"):
        return "set"
    elif name.startswith("change_"):
        return "change"
    elif name.startswith("create_"):
        return "create"
    elif name.startswith("destroy_"):
        return "destroy"
    elif name.startswith("has_"):
        return "check"
    elif name.startswith("is_"):
        return "check"
    elif name.startswith("can_"):
        return "check"
    elif name in ("and", "or", "not", "nand", "nor", "if", "else", "else_if", "while", "switch"):
        return "flow"
    else:
        return "other"


def categorize_modifier(name: str) -> str:
    """Categorize a modifier by its name pattern."""
    if "army" in name or "military" in name or "discipline" in name or "morale" in name:
        return "military"
    elif "navy" in name or "naval" in name or "ship" in name or "sailor" in name:
        return "naval"
    elif "tax" in name or "trade" in name or "production" in name or "income" in name:
        return "economy"
    elif "diplomatic" in name or "relation" in name or "opinion" in name:
        return "diplomacy"
    elif "stability" in name or "legitimacy" in name or "government" in name:
        return "government"
    elif "technology" in name or "idea" in name or "research" in name:
        return "technology"
    elif "population" in name or "pop_" in name or "growth" in name:
        return "population"
    elif "local_" in name:
        return "province"
    elif "global_" in name:
        return "global"
    elif "allow" in name or "can_" in name or "block" in name:
        return "permission"
    elif "estate" in name:
        return "estate"
    else:
        return "other"


def categorize_on_action(name: str) -> str:
    """Categorize an on_action by its name pattern."""
    if "pulse" in name:
        return "pulse"
    elif "war" in name or "battle" in name or "siege" in name:
        return "war"
    elif "character" in name or "ruler" in name or "heir" in name or "death" in name:
        return "character"
    elif "province" in name or "capital" in name or "location" in name:
        return "province"
    elif "diplomacy" in name or "alliance" in name or "annex" in name:
        return "diplomacy"
    elif "election" in name or "government" in name:
        return "government"
    else:
        return "other"
