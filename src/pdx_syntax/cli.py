"""CLI for querying EU5 syntax database."""

import sys

import click
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markup import escape as _esc

from .database import init_database, get_meta, DEFAULT_DB_PATH
from .search import (
    search_effects,
    search_triggers,
    search_scopes,
    search_modifiers,
    search_on_actions,
    search_data_types,
    search_custom_localizations,
    fts_search,
    list_categories,
    list_scope_types,
    get_by_name,
    suggest_similar,
    find_in_other_tables,
    get_changes_for_version,
    add_note,
    get_notes,
    get_all_notes,
    delete_note,
)

console = Console()
_err_console = Console(stderr=True)

# Plain output: full data as flat text, no table layout. Auto-enabled when
# stdout is not a terminal (pipes, agents, redirects) so column squeezing
# can never mangle results; --plain/--table force it either way.
_PLAIN = not sys.stdout.isatty()


@click.group(context_settings={"token_normalize_func": lambda x: x.replace("_", "-")})
@click.option("--db", type=click.Path(), help="Database file path")
@click.option("--plain/--table", "plain", default=None,
              help="Force flat text / rich table output (default: tables on a "
                   "terminal, flat text when piped)")
@click.pass_context
def main(ctx, db, plain):
    """PDX Syntax - Query EU5 Paradox script syntax.

    Use fuzzy search to find effects, triggers, scopes, and modifiers
    for Europa Universalis 5 modding.
    """
    global _PLAIN
    if plain is not None:
        _PLAIN = plain
    ctx.ensure_object(dict)
    db_path = Path(db) if db else DEFAULT_DB_PATH
    ctx.obj["db_path"] = db_path
    init_database(db_path)
    _warn_if_stale(db_path)


def _warn_if_stale(db_path):
    """Warn (stderr) when the game has patched since the DB was built."""
    from .scrapers.digest import read_game_checksum
    stored = get_meta("game_checksum_at_update", db_path)
    if not stored:
        return
    live = read_game_checksum()
    if live and live != stored:
        _err_console.print(
            "[yellow]WARNING: the game has patched since this syntax DB was "
            "built (checksum mismatch). Re-dump script docs from the in-game "
            "console, then run 'pdx-syntax update'.[/yellow]")


@main.command()
@click.pass_context
def init(ctx):
    """Initialize or reset the database."""
    db_path = ctx.obj["db_path"]
    init_database(db_path)
    console.print(f"[green]Database initialized at {db_path}[/green]")


GUIDE_TEXT = """
[bold cyan]pdx-syntax - Search Guide[/bold cyan]

The database has 7 searchable tables.  Entries can appear in more than one.

[bold]EFFECTS[/bold]  [dim]pdx-syntax effect <query>[/dim]
  Commands that change game state: add_gold, create_character, set_variable, etc.
  [dim]Includes iterator effects (every_*, random_*, ordered_*).[/dim]
  Filters: -s/--scope <type>  -c/--category <cat>

[bold]TRIGGERS[/bold]  [dim]pdx-syntax trigger <query>[/dim]
  Conditions that check game state: has_gold, is_at_war, num_of_cities, etc.
  [dim]Includes iterator triggers (any_*).[/dim]
  Filters: -s/--scope <type>  -c/--category <cat>

[bold]SCOPES[/bold]  [dim]pdx-syntax scope <query>[/dim]
  Event targets that change scope context plus ALL iterators cross-populated
  from effects and triggers.  Best single table for finding iterators.
  Filters: -t/--type <scope_type>  --iterator

[bold]MODIFIERS[/bold]  [dim]pdx-syntax modifier <query>[/dim]
  Numeric and boolean stat modifiers: discipline, tax_modifier, etc.
  Filters: -c/--category <cat>  -s/--scope <type>  --boolean

[bold]ON ACTIONS[/bold]  [dim]pdx-syntax on-action <query>[/dim]
  Hooks fired by the engine: on_war_declared, on_monthly, on_death, etc.
  Filters: -s/--scope <type>

[bold]DATA TYPES[/bold]  [dim]pdx-syntax promote <query>[/dim]
  Promotes, functions, and types for script/GUI/loc: GetCapital, MakeScope.
  Filters: -t/--type <parent_type>  -c/--category  -d/--definition <def_type>

[bold]CUSTOM LOCALIZATIONS[/bold]  [dim]pdx-syntax custom-loc <query>[/dim]
  Custom loc functions with entry keys for dynamic text.
  Filters: -s/--scope  -e/--entries (search within entry keys)

[bold]Search strategy when you can't find something:[/bold]
  1. Try a shorter or broader query — "gold" finds add_gold, has_gold, etc.
  2. Wrong table?  Iterators (every_/any_/random_/ordered_) live in scopes,
     effects, AND triggers.  An "add_" or "set_" is an effect.  A "has_" or
     "is_" or "num_" is a trigger.  A stat name is a modifier.
  3. Use --exact for precise name lookups, omit it for fuzzy matching.
  4. Try pdx-syntax search "<words>" -t <type> for full-text search.
  5. Check pdx-syntax stats to confirm the database is populated.
  6. Run pdx-syntax categories -t <type> to see valid category filters.
"""


def _print_guide():
    console.print(GUIDE_TEXT)


# table name -> CLI command that searches it
TABLE_COMMANDS = {
    "effects": "effect",
    "triggers": "trigger",
    "scopes": "scope",
    "modifiers": "modifier",
    "on_actions": "on-action",
    "data_types": "promote",
    "custom_localizations": "custom-loc",
}


def _handle_miss(query, table, db_path, label):
    """On a failed lookup, print did-you-mean suggestions and cross-table
    hits instead of the full search guide."""
    console.print(f"[yellow]No {label} found matching '{query}'[/yellow]")

    other = find_in_other_tables(query, table, db_path=db_path)
    if other:
        hints = ", ".join(
            f"{t} (pdx-syntax {TABLE_COMMANDS[t]} {query} --exact)"
            for t in other
        )
        console.print(f"[green]Exact name exists in:[/green] {hints}")

    suggestions = suggest_similar(query, table, db_path=db_path)
    if suggestions:
        console.print("[bold]Did you mean:[/bold]")
        for name, score in suggestions:
            console.print(f"  - {name} [dim]({score})[/dim]")

    console.print("[dim]More search strategies: pdx-syntax info[/dim]")


@main.command()
@click.pass_context
def info(ctx):
    """Show detailed search guide — what lives where and how to find it."""
    _print_guide()


@main.command()
@click.argument("query")
@click.option("-s", "--scope", help="Filter by scope type")
@click.option("-c", "--category", help="Filter by category")
@click.option("-n", "--limit", default=10, help="Maximum results")
@click.option("--exact", is_flag=True, help="Exact name match only")
@click.pass_context
def effect(ctx, query, scope, category, limit, exact):
    """Search for effects (commands that change game state).

    Examples:
        pdx-syntax effect add_gold
        pdx-syntax effect "create character" --scope country
        pdx-syntax effect army --category iterator
    """
    db_path = ctx.obj["db_path"]

    if exact:
        result = get_by_name(query, "effects", db_path)
        if result:
            _display_effect_detail(result, db_path)
        else:
            _handle_miss(query, "effects", db_path, "effect")
        return

    results = search_effects(query, scope=scope, category=category, limit=limit, db_path=db_path)

    if not results:
        _handle_miss(query, "effects", db_path, "effect")
        return

    _display_results_table(results, "Effects", ["name", "scope_type", "category", "description"])


@main.command()
@click.argument("query")
@click.option("-s", "--scope", help="Filter by scope type")
@click.option("-c", "--category", help="Filter by category")
@click.option("-n", "--limit", default=10, help="Maximum results")
@click.option("--exact", is_flag=True, help="Exact name match only")
@click.pass_context
def trigger(ctx, query, scope, category, limit, exact):
    """Search for triggers (conditions that check game state).

    Examples:
        pdx-syntax trigger has_gold
        pdx-syntax trigger "is at war" --scope country
        pdx-syntax trigger any_ --category iterator
    """
    db_path = ctx.obj["db_path"]

    if exact:
        result = get_by_name(query, "triggers", db_path)
        if result:
            _display_trigger_detail(result, db_path)
        else:
            _handle_miss(query, "triggers", db_path, "trigger")
        return

    results = search_triggers(query, scope=scope, category=category, limit=limit, db_path=db_path)

    if not results:
        _handle_miss(query, "triggers", db_path, "trigger")
        return

    _display_results_table(results, "Triggers", ["name", "scope_type", "category", "description"])


@main.command()
@click.argument("query")
@click.option("-t", "--type", "scope_type", help="Filter by scope type")
@click.option("--iterator", is_flag=True, help="Show only iterator scopes")
@click.option("-n", "--limit", default=10, help="Maximum results")
@click.option("--exact", is_flag=True, help="Exact name match only")
@click.pass_context
def scope(ctx, query, scope_type, iterator, limit, exact):
    """Search for scopes (context changers and iterators).

    Examples:
        pdx-syntax scope every_country
        pdx-syntax scope character --type country
        pdx-syntax scope army --iterator
    """
    db_path = ctx.obj["db_path"]

    if exact:
        result = get_by_name(query, "scopes", db_path)
        if result:
            _display_scope_detail(result, db_path)
        else:
            _handle_miss(query, "scopes", db_path, "scope")
        return

    results = search_scopes(
        query, scope_type=scope_type, iterator_only=iterator, limit=limit, db_path=db_path
    )

    if not results:
        _handle_miss(query, "scopes", db_path, "scope")
        return

    _display_results_table(
        results, "Scopes", ["name", "scope_type", "target_type", "is_iterator", "description"]
    )


@main.command()
@click.argument("query")
@click.option("-c", "--category", help="Filter by category")
@click.option("-s", "--scope", "scope_type", help="Filter by scope type")
@click.option("--boolean", is_flag=True, help="Show only boolean modifiers")
@click.option("-n", "--limit", default=10, help="Maximum results")
@click.option("--exact", is_flag=True, help="Exact name match only")
@click.pass_context
def modifier(ctx, query, category, scope_type, boolean, limit, exact):
    """Search for modifiers (stat modifiers).

    Examples:
        pdx-syntax modifier discipline
        pdx-syntax modifier tax --category economic
        pdx-syntax modifier allow --boolean
    """
    db_path = ctx.obj["db_path"]

    if exact:
        result = get_by_name(query, "modifiers", db_path)
        if result:
            _display_modifier_detail(result, db_path)
        else:
            _handle_miss(query, "modifiers", db_path, "modifier")
        return

    results = search_modifiers(
        query,
        category=category,
        scope_type=scope_type,
        boolean_only=boolean,
        limit=limit,
        db_path=db_path,
    )

    if not results:
        _handle_miss(query, "modifiers", db_path, "modifier")
        return

    _display_results_table(
        results, "Modifiers", ["name", "category", "scope_type", "is_boolean", "description"]
    )


@main.command()
@click.argument("query")
@click.option("-s", "--scope", "scope_type", help="Filter by scope type")
@click.option("-n", "--limit", default=10, help="Maximum results")
@click.option("--exact", is_flag=True, help="Exact name match only")
@click.pass_context
def on_action(ctx, query, scope_type, limit, exact):
    """Search for on_actions (event hooks).

    Examples:
        pdx-syntax on_action death
        pdx-syntax on_action war --scope country
        pdx-syntax on_action monthly
    """
    db_path = ctx.obj["db_path"]

    if exact:
        result = get_by_name(query, "on_actions", db_path)
        if result:
            _display_on_action_detail(result, db_path)
        else:
            _handle_miss(query, "on_actions", db_path, "on_action")
        return

    results = search_on_actions(query, scope_type=scope_type, limit=limit, db_path=db_path)

    if not results:
        _handle_miss(query, "on_actions", db_path, "on_action")
        return

    _display_results_table(results, "On Actions", ["name", "scope_type", "description"])


@main.command()
@click.argument("query")
@click.option("-t", "--type", "parent_type", help="Filter by parent type (e.g., Country)")
@click.option("-c", "--category", "source_category", help="Filter by source category (script, gui, common, uncategorized, internal_gui)")
@click.option("-d", "--definition", "definition_type", help="Filter by definition type (e.g., Promote, Function, Type)")
@click.option("-n", "--limit", default=10, help="Maximum results")
@click.option("--exact", is_flag=True, help="Exact name match only")
@click.pass_context
def promote(ctx, query, parent_type, source_category, definition_type, limit, exact):
    """Search data types (promotes, functions, types).

    Examples:
        pdx-syntax promote GetCapital
        pdx-syntax promote GetCapital --type Country
        pdx-syntax promote Variable --category script
        pdx-syntax promote MakeScope --definition Function
    """
    db_path = ctx.obj["db_path"]

    if exact:
        result = get_by_name(query, "data_types", db_path)
        if result:
            _display_data_type_detail(result, db_path)
        else:
            _handle_miss(query, "data_types", db_path, "data type")
        return

    results = search_data_types(
        query,
        parent_type=parent_type,
        source_category=source_category,
        definition_type=definition_type,
        limit=limit,
        db_path=db_path,
    )

    if not results:
        _handle_miss(query, "data_types", db_path, "data type")
        return

    _display_results_table(
        results, "Data Types", ["name", "definition_type", "return_type", "source_category", "description"]
    )


@main.command()
@click.argument("query")
@click.option("-s", "--scope", help="Filter by scope")
@click.option("-e", "--entries", is_flag=True, help="Search within entry keys instead of names")
@click.option("-n", "--limit", default=10, help="Maximum results")
@click.option("--exact", is_flag=True, help="Exact name match only")
@click.pass_context
def custom_loc(ctx, query, scope, entries, limit, exact):
    """Search custom localization functions.

    Examples:
        pdx-syntax custom-loc rebel              # fuzzy match on name
        pdx-syntax custom-loc grain --entries     # find locs containing 'grain' entry
        pdx-syntax custom-loc country --scope country
    """
    db_path = ctx.obj["db_path"]

    if exact:
        result = get_by_name(query, "custom_localizations", db_path)
        if result:
            _display_custom_loc_detail(result, db_path)
        else:
            _handle_miss(query, "custom_localizations", db_path, "custom localization")
        return

    results = search_custom_localizations(query, scope=scope, search_entries=entries, limit=limit, db_path=db_path)

    if not results:
        _handle_miss(query, "custom_localizations", db_path, "custom localization")
        return

    _display_results_table(results, "Custom Localizations", ["name", "scope", "random_valid", "entries"])


@main.command()
@click.argument("query")
@click.option(
    "-t",
    "--type",
    "item_type",
    type=click.Choice(["effects", "triggers", "scopes", "modifiers"]),
    default="effects",
    help="Type to search",
)
@click.option("-n", "--limit", default=10, help="Maximum results")
@click.pass_context
def search(ctx, query, item_type, limit):
    """Full-text search across the database.

    Examples:
        pdx-syntax search "army morale" --type modifiers
        pdx-syntax search "iterate country" --type scopes
    """
    db_path = ctx.obj["db_path"]
    results = fts_search(query, item_type, limit=limit, db_path=db_path)

    if not results:
        console.print(f"[yellow]No results found for '{query}' in {item_type}[/yellow]")
        _print_guide()
        return

    # Determine columns based on type
    columns = {
        "effects": ["name", "scope_type", "category", "description"],
        "triggers": ["name", "scope_type", "category", "description"],
        "scopes": ["name", "scope_type", "target_type", "description"],
        "modifiers": ["name", "category", "scope_type", "description"],
    }

    _display_results_table(results, item_type.title(), columns[item_type])


@main.command()
@click.option(
    "-t",
    "--type",
    "item_type",
    type=click.Choice(["effects", "triggers", "scopes", "modifiers", "on_actions"]),
    help="Type to list categories for",
)
@click.pass_context
def categories(ctx, item_type):
    """List available categories for a type.

    Examples:
        pdx-syntax categories --type effects
        pdx-syntax categories --type modifiers
    """
    db_path = ctx.obj["db_path"]

    if item_type:
        cats = list_categories(item_type, db_path)
        if cats:
            console.print(f"\n[bold]Categories for {item_type}:[/bold]")
            for cat in cats:
                console.print(f"  - {cat}")
        else:
            console.print(f"[yellow]No categories found for {item_type}[/yellow]")
    else:
        for t in ["effects", "triggers", "modifiers", "on_actions"]:
            cats = list_categories(t, db_path)
            if cats:
                console.print(f"\n[bold]Categories for {t}:[/bold]")
                for cat in cats[:10]:
                    console.print(f"  - {cat}")
                if len(cats) > 10:
                    console.print(f"  ... and {len(cats) - 10} more")


@main.command()
@click.pass_context
def scopes(ctx):
    """List all scope types."""
    db_path = ctx.obj["db_path"]
    scope_list = list_scope_types(db_path)

    if scope_list:
        console.print("\n[bold]Available Scope Types:[/bold]")
        for s in scope_list:
            console.print(f"  - {s}")
    else:
        console.print("[yellow]No scope types found. Run 'pdx-syntax update' to populate.[/yellow]")


@main.command()
@click.argument("version")
@click.pass_context
def changes(ctx, version):
    """Show changes for a specific game version.

    Examples:
        pdx-syntax changes 1.1.0
        pdx-syntax changes 1.0.10
    """
    db_path = ctx.obj["db_path"]
    change_list = get_changes_for_version(version, db_path)

    if not change_list:
        console.print(f"[yellow]No changes recorded for version {version}[/yellow]")
        return

    rows = [
        {
            "name": c["item_name"],
            "item_type": c["item_type"],
            "change_type": c["change_type"],
            "description": c.get("description", ""),
        }
        for c in change_list
    ]
    _display_results_table(rows, f"Changes in {version}",
                           ["name", "item_type", "change_type", "description"])


@main.command()
@click.option("--docs-dir", type=click.Path(exists=True), help="Path to EU5 docs/ directory")
@click.option("--data-types-dir", type=click.Path(exists=True), help="Path to EU5 logs/data_types/ directory")
@click.option("--version", help="Game version label (auto-detected if omitted)")
@click.option("--offline", is_flag=True, help="Use only built-in seed data (no file reading)")
@click.pass_context
def update(ctx, docs_dir, data_types_dir, version, offline):
    """Update the database from game-dumped log files.

    Reads the .log and data_types files that EU5 dumps to its user
    directory.  By default looks in the standard Paradox location;
    use --docs-dir / --data-types-dir to override.

    Use --offline to load only the built-in seed data.
    """
    from pathlib import Path as _Path
    from .scrapers.digest import digest_update, DEFAULT_DOCS_DIR, DEFAULT_DATA_TYPES_DIR

    db_path = ctx.obj["db_path"]
    dd = _Path(docs_dir) if docs_dir else DEFAULT_DOCS_DIR
    dtd = _Path(data_types_dir) if data_types_dir else DEFAULT_DATA_TYPES_DIR

    console.print("[bold]Updating database from game files...[/bold]")
    try:
        stats = digest_update(
            db_path,
            docs_dir=dd,
            data_types_dir=dtd,
            game_version=version,
            verbose=True,
            offline=offline,
        )
        console.print("\n[green]Update complete![/green]")
        console.print(f"  Effects: {stats.get('effects', 0)}")
        console.print(f"  Triggers: {stats.get('triggers', 0)}")
        console.print(f"  Scopes: {stats.get('scopes', 0)}")
        console.print(f"  Modifiers: {stats.get('modifiers', 0)}")
        console.print(f"  On Actions: {stats.get('on_actions', 0)}")
        console.print(f"  Custom Localizations: {stats.get('custom_localizations', 0)}")
        console.print(f"  Data Types: {stats.get('data_types', 0)}")
    except Exception as e:
        console.print(f"[red]Update failed: {e}[/red]")
        import traceback
        traceback.print_exc()


@main.command()
@click.option("--force", is_flag=True, help="Force reseed even if already seeded")
@click.pass_context
def seed(ctx, force):
    """Seed the database with initial data.

    This loads the built-in EU5 syntax data without fetching from the web.
    Use this for offline setup or to reset to known good data.
    """
    from .seed import seed_database

    db_path = ctx.obj["db_path"]

    with console.status("[bold green]Seeding database with initial data..."):
        try:
            stats = seed_database(db_path, force=force)
            console.print("[green]Seed complete![/green]")
            console.print(f"  Scope Types: {stats.get('scope_types', 0)}")
            console.print(f"  Triggers: {stats.get('triggers', 0)}")
            console.print(f"  Scopes: {stats.get('scopes', 0)}")
            console.print(f"  Effects: {stats.get('effects', 0)}")
            console.print(f"  Modifiers: {stats.get('modifiers', 0)}")
            console.print(f"  On Actions: {stats.get('on_actions', 0)}")
            console.print(f"  Templates: {stats.get('templates', 0)}")
            console.print(f"  Version Changes: {stats.get('changes', 0)}")
        except Exception as e:
            console.print(f"[red]Seed failed: {e}[/red]")


@main.command()
@click.argument("name")
@click.pass_context
def template(ctx, name):
    """Show a syntax template by name.

    Examples:
        pdx-syntax template event_structure
        pdx-syntax template scripted_effect
    """
    from .database import get_connection

    db_path = ctx.obj["db_path"]
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM syntax_templates WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        # Try fuzzy match
        conn = get_connection(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM syntax_templates")
        all_names = [r[0] for r in cursor.fetchall()]
        conn.close()

        if all_names:
            from rapidfuzz import process
            matches = process.extract(name, all_names, limit=3)
            console.print(f"[yellow]Template '{name}' not found. Did you mean:[/yellow]")
            for match, score, _ in matches:
                console.print(f"  - {match}")
        else:
            console.print("[yellow]No templates found. Run 'pdx-syntax seed' first.[/yellow]")
        return

    template_data = dict(row)
    console.print(Panel(f"[bold cyan]{template_data['name']}[/bold cyan]", title="Template"))

    if template_data.get("description"):
        console.print(f"\n[bold]Description:[/bold] {_esc(str(template_data['description']))}")

    if template_data.get("category"):
        console.print(f"[bold]Category:[/bold] {_esc(str(template_data['category']))}")

    if template_data.get("template"):
        console.print("\n[bold]Template:[/bold]")
        console.print(Syntax(template_data["template"], "text", theme="monokai"))

    if template_data.get("parameters"):
        console.print(f"\n[bold]Parameters:[/bold] {_esc(str(template_data['parameters']))}")


@main.command()
@click.pass_context
def templates(ctx):
    """List all available syntax templates."""
    from .database import get_connection

    db_path = ctx.obj["db_path"]
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name, category, description FROM syntax_templates ORDER BY category, name")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        console.print("[yellow]No templates found. Run 'pdx-syntax seed' first.[/yellow]")
        return

    _display_results_table(
        [dict(r) for r in rows], "Syntax Templates", ["name", "category", "description"]
    )


@main.command()
@click.pass_context
def stats(ctx):
    """Show database statistics."""
    from .database import get_connection

    db_path = ctx.obj["db_path"]
    conn = get_connection(db_path)
    cursor = conn.cursor()

    tables = ["effects", "triggers", "scopes", "modifiers", "on_actions",
              "custom_localizations", "data_types", "change_log"]

    console.print("\n[bold]Database Statistics:[/bold]")
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            console.print(f"  {table}: {count}")
        except Exception:
            console.print(f"  {table}: [yellow]not found[/yellow]")

    # Show last update time
    cursor.execute(
        "SELECT MAX(fetched_at) FROM data_sources"
    )
    row = cursor.fetchone()
    if row and row[0]:
        console.print(f"\n  Last updated: {row[0]}")

    conn.close()


VALID_NOTE_TYPES = ["effect", "trigger", "scope", "modifier", "on_action", "custom_loc", "data_type"]


@main.command()
@click.argument("action", type=click.Choice(["add", "list", "rm"]))
@click.argument("args", nargs=-1)
@click.pass_context
def note(ctx, action, args):
    """Add, list, or remove notes on entries.

    \b
    Add a note:
        pdx-syntax note add effect add_gold "Accepts negative values"
    List notes for an entry:
        pdx-syntax note list effect add_gold
    List all notes:
        pdx-syntax note list
    Remove a note by ID:
        pdx-syntax note rm 3
    """
    db_path = ctx.obj["db_path"]

    if action == "add":
        if len(args) < 3:
            console.print("[red]Usage: pdx-syntax note add <type> <name> <content>[/red]")
            console.print(f"  Types: {', '.join(VALID_NOTE_TYPES)}")
            return
        item_type, item_name, content = args[0], args[1], " ".join(args[2:])
        if item_type not in VALID_NOTE_TYPES:
            console.print(f"[red]Invalid type '{item_type}'. Must be one of: {', '.join(VALID_NOTE_TYPES)}[/red]")
            return
        note_id = add_note(item_type, item_name, content, db_path=db_path)
        console.print(f"[green]Note #{note_id} added to {item_type} '{item_name}'[/green]")

    elif action == "list":
        if len(args) >= 2:
            item_type, item_name = args[0], args[1]
            notes = get_notes(item_type, item_name, db_path=db_path)
            if not notes:
                console.print(f"[yellow]No notes for {item_type} '{item_name}'[/yellow]")
                return
            _display_notes(notes, f"{item_type}: {item_name}")
        else:
            notes = get_all_notes(db_path=db_path)
            if not notes:
                console.print("[yellow]No notes found[/yellow]")
                return
            _display_notes(notes, "All Notes")

    elif action == "rm":
        if not args:
            console.print("[red]Usage: pdx-syntax note rm <note_id>[/red]")
            return
        try:
            note_id = int(args[0])
        except ValueError:
            console.print("[red]Note ID must be a number[/red]")
            return
        if delete_note(note_id, db_path=db_path):
            console.print(f"[green]Note #{note_id} deleted[/green]")
        else:
            console.print(f"[yellow]Note #{note_id} not found[/yellow]")


def _display_notes(notes: list[dict], title: str) -> None:
    """Display notes."""
    if _PLAIN:
        print(title)
        for n in notes:
            print(f"\n#{n['id']} [{n['item_type']} {n['item_name']}] ({n['author']})")
            for line in str(n["content"]).splitlines():
                print(f"    {line.rstrip()}")
        print()
        return

    table = Table(title=title)
    table.add_column("ID", style="dim")
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Note", overflow="fold", ratio=3)
    table.add_column("Author", style="dim")

    for n in notes:
        table.add_row(
            str(n["id"]),
            n["item_type"],
            n["item_name"],
            n["content"],
            n["author"],
        )

    console.print(table)


def _get_entry_notes(item_type: str, name: str, db_path) -> list[dict]:
    """Get notes for an entry, for use in detail displays."""
    return get_notes(item_type, name, db_path=db_path)


# Columns rendered as an indented body under the entry instead of inline
_BODY_COLUMNS = ("description", "entries")


def _fmt_val(val, col: str) -> str:
    if val is None:
        return ""
    if isinstance(val, bool) or col in ("is_iterator", "is_boolean", "random_valid"):
        return "Yes" if val else "No"
    return str(val)


def _display_results_table(results: list[dict], title: str, columns: list[str]) -> None:
    """Display search results.

    Plain mode (default when piped): one flat block per result, full text,
    nothing squeezed or wrapped away. Table mode (terminals): rich table with
    fold overflow so cells wrap but are never truncated.
    """
    # Even in table mode, fall back to plain when the terminal cannot give
    # every column readable width (long names + narrow terminal would
    # otherwise wrap cells down to a few characters per line).
    use_plain = _PLAIN
    if not use_plain and results:
        name_width = max(len(str(r.get("name", ""))) for r in results)
        tag_cols = [c for c in columns if c != "name" and c not in _BODY_COLUMNS]
        needed = name_width + 12 * len(tag_cols) + 30 + 3 * len(columns) + 4
        use_plain = console.width < needed

    if use_plain:
        print(f"{title} ({len(results)} results)")
        body_cols = [c for c in _BODY_COLUMNS if c in columns]
        for result in results:
            tags = " | ".join(
                f"{col}: {_fmt_val(result.get(col), col)}"
                for col in columns
                if col != "name" and col not in body_cols
                and _fmt_val(result.get(col), col) != ""
            )
            name = _fmt_val(result.get("name"), "name")
            print(f"\n{name}" + (f"  [{tags}]" if tags else ""))
            for col in body_cols:
                text = _fmt_val(result.get(col), col)
                for line in text.splitlines():
                    if line.strip():
                        print(f"    {line.rstrip()}")
        print()
        return

    table = Table(title=f"{title} ({len(results)} results)")
    for col in columns:
        style = "cyan" if col == "name" else None
        # Only the name column resists wrapping; every column folds instead
        # of truncating, and body columns get the spare width.
        table.add_column(
            col.replace("_", " ").title(),
            style=style,
            no_wrap=(col == "name"),
            overflow="fold",
            ratio=(3 if col in _BODY_COLUMNS else None),
        )

    for result in results:
        table.add_row(*[_fmt_val(result.get(col, ""), col) for col in columns])

    console.print(table)
    console.print("[dim]Tip: use `pdx-syntax note add <type> <name> \"<note>\"` to record findings.[/dim]")


def _show_notes_section(item_type: str, name: str, db_path) -> None:
    """Show notes for an entry if any exist."""
    notes = get_notes(item_type, name, db_path=db_path)
    if notes:
        console.print(f"\n[bold yellow]Notes ({len(notes)}):[/bold yellow]")
        for n in notes:
            console.print(f"  [dim]#{n['id']}[/dim] {n['content']}  [dim]({n['author']})[/dim]")


def _display_effect_detail(effect: dict, db_path=None) -> None:
    """Display detailed information about an effect."""
    console.print(Panel(f"[bold cyan]{effect['name']}[/bold cyan]", title="Effect"))

    if effect.get("description"):
        console.print(f"\n[bold]Description:[/bold] {_esc(str(effect['description']))}")

    if effect.get("scope_type"):
        console.print(f"[bold]Scope:[/bold] {_esc(str(effect['scope_type']))}")

    if effect.get("category"):
        console.print(f"[bold]Category:[/bold] {_esc(str(effect['category']))}")

    if effect.get("syntax"):
        console.print("\n[bold]Syntax:[/bold]")
        console.print(Syntax(effect["syntax"], "text", theme="monokai"))

    if effect.get("parameters"):
        console.print(f"\n[bold]Parameters:[/bold] {_esc(str(effect['parameters']))}")

    if effect.get("example"):
        console.print("\n[bold]Example:[/bold]")
        console.print(Syntax(effect["example"], "text", theme="monokai"))

    if db_path:
        _show_notes_section("effect", effect["name"], db_path)


def _display_trigger_detail(trigger: dict, db_path=None) -> None:
    """Display detailed information about a trigger."""
    console.print(Panel(f"[bold cyan]{trigger['name']}[/bold cyan]", title="Trigger"))

    if trigger.get("description"):
        console.print(f"\n[bold]Description:[/bold] {_esc(str(trigger['description']))}")

    if trigger.get("scope_type"):
        console.print(f"[bold]Scope:[/bold] {_esc(str(trigger['scope_type']))}")

    if trigger.get("category"):
        console.print(f"[bold]Category:[/bold] {_esc(str(trigger['category']))}")

    if trigger.get("syntax"):
        console.print("\n[bold]Syntax:[/bold]")
        console.print(Syntax(trigger["syntax"], "text", theme="monokai"))

    if trigger.get("parameters"):
        console.print(f"\n[bold]Parameters:[/bold] {_esc(str(trigger['parameters']))}")

    if trigger.get("example"):
        console.print("\n[bold]Example:[/bold]")
        console.print(Syntax(trigger["example"], "text", theme="monokai"))

    if db_path:
        _show_notes_section("trigger", trigger["name"], db_path)


def _display_scope_detail(scope: dict, db_path=None) -> None:
    """Display detailed information about a scope."""
    console.print(Panel(f"[bold cyan]{scope['name']}[/bold cyan]", title="Scope"))

    if scope.get("description"):
        console.print(f"\n[bold]Description:[/bold] {_esc(str(scope['description']))}")

    if scope.get("scope_type"):
        console.print(f"[bold]From Scope:[/bold] {_esc(str(scope['scope_type']))}")

    if scope.get("target_type"):
        console.print(f"[bold]Target Type:[/bold] {_esc(str(scope['target_type']))}")

    if scope.get("is_iterator"):
        console.print(f"[bold]Iterator:[/bold] Yes")
        if scope.get("iterator_type"):
            console.print(f"[bold]Iterator Type:[/bold] {_esc(str(scope['iterator_type']))}")

    if scope.get("syntax"):
        console.print("\n[bold]Syntax:[/bold]")
        console.print(Syntax(scope["syntax"], "text", theme="monokai"))

    if scope.get("parameters"):
        console.print(f"\n[bold]Parameters:[/bold] {_esc(str(scope['parameters']))}")

    if scope.get("example"):
        console.print("\n[bold]Example:[/bold]")
        console.print(Syntax(scope["example"], "text", theme="monokai"))

    if db_path:
        _show_notes_section("scope", scope["name"], db_path)


def _display_modifier_detail(modifier: dict, db_path=None) -> None:
    """Display detailed information about a modifier."""
    console.print(Panel(f"[bold cyan]{modifier['name']}[/bold cyan]", title="Modifier"))

    if modifier.get("description"):
        console.print(f"\n[bold]Description:[/bold] {_esc(str(modifier['description']))}")

    if modifier.get("category"):
        console.print(f"[bold]Category:[/bold] {_esc(str(modifier['category']))}")

    if modifier.get("scope_type"):
        console.print(f"[bold]Scope:[/bold] {_esc(str(modifier['scope_type']))}")

    if modifier.get("modifier_type"):
        console.print(f"[bold]Type:[/bold] {_esc(str(modifier['modifier_type']))}")

    if modifier.get("is_boolean"):
        console.print(f"[bold]Boolean:[/bold] Yes")

    if modifier.get("default_value"):
        console.print(f"[bold]Default:[/bold] {_esc(str(modifier['default_value']))}")

    if modifier.get("color"):
        console.print(f"[bold]Color:[/bold] {_esc(str(modifier['color']))}")

    if modifier.get("percent"):
        console.print(f"[bold]Percent:[/bold] Yes")

    if modifier.get("syntax"):
        console.print("\n[bold]Syntax:[/bold]")
        console.print(Syntax(modifier["syntax"], "text", theme="monokai"))

    if modifier.get("parameters"):
        console.print(f"\n[bold]Parameters:[/bold] {_esc(str(modifier['parameters']))}")

    if db_path:
        _show_notes_section("modifier", modifier["name"], db_path)


def _display_on_action_detail(on_action: dict, db_path=None) -> None:
    """Display detailed information about an on_action."""
    console.print(Panel(f"[bold cyan]{on_action['name']}[/bold cyan]", title="On Action"))

    if on_action.get("description"):
        console.print(f"\n[bold]Description:[/bold] {_esc(str(on_action['description']))}")

    if on_action.get("scope_type"):
        console.print(f"[bold]Scope:[/bold] {_esc(str(on_action['scope_type']))}")

    if on_action.get("category"):
        console.print(f"[bold]Category:[/bold] {_esc(str(on_action['category']))}")

    if on_action.get("syntax"):
        console.print("\n[bold]Syntax:[/bold]")
        console.print(Syntax(on_action["syntax"], "text", theme="monokai"))

    if on_action.get("parameters"):
        console.print(f"\n[bold]Parameters:[/bold] {_esc(str(on_action['parameters']))}")

    if on_action.get("example"):
        console.print("\n[bold]Example:[/bold]")
        console.print(Syntax(on_action["example"], "text", theme="monokai"))

    if db_path:
        _show_notes_section("on_action", on_action["name"], db_path)


def _display_data_type_detail(dt: dict, db_path=None) -> None:
    """Display detailed information about a data type."""
    console.print(Panel(f"[bold cyan]{dt['name']}[/bold cyan]", title="Data Type"))

    if dt.get("description"):
        console.print(f"\n[bold]Description:[/bold] {_esc(str(dt['description']))}")

    if dt.get("parent_type"):
        console.print(f"[bold]Parent Type:[/bold] {_esc(str(dt['parent_type']))}")

    if dt.get("args"):
        console.print(f"[bold]Arguments:[/bold] {_esc(str(dt['args']))}")

    if dt.get("definition_type"):
        console.print(f"[bold]Definition:[/bold] {_esc(str(dt['definition_type']))}")

    if dt.get("return_type"):
        console.print(f"[bold]Return Type:[/bold] {_esc(str(dt['return_type']))}")

    if dt.get("source_category"):
        console.print(f"[bold]Category:[/bold] {_esc(str(dt['source_category']))}")

    if db_path:
        _show_notes_section("data_type", dt["name"], db_path)


def _display_custom_loc_detail(cl: dict, db_path=None) -> None:
    """Display detailed information about a custom localization."""
    console.print(Panel(f"[bold cyan]{cl['name']}[/bold cyan]", title="Custom Localization"))

    if cl.get("scope"):
        console.print(f"\n[bold]Scope:[/bold] {_esc(str(cl['scope']))}")

    console.print(f"[bold]Random Valid:[/bold] {'Yes' if cl.get('random_valid') else 'No'}")

    if cl.get("entries"):
        console.print(f"\n[bold]Entries:[/bold]")
        for entry in cl["entries"].split("\n")[:20]:
            console.print(f"  {entry}")
        lines = cl["entries"].split("\n")
        if len(lines) > 20:
            console.print(f"  ... and {len(lines) - 20} more")

    if db_path:
        _show_notes_section("custom_loc", cl["name"], db_path)


if __name__ == "__main__":
    main()
