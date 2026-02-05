"""CLI for querying EU5 syntax database."""

import click
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown

from .database import init_database, DEFAULT_DB_PATH
from .search import (
    search_effects,
    search_triggers,
    search_scopes,
    search_modifiers,
    search_on_actions,
    fts_search,
    list_categories,
    list_scope_types,
    get_by_name,
    get_changes_for_version,
)

console = Console()


@click.group()
@click.option("--db", type=click.Path(), help="Database file path")
@click.pass_context
def main(ctx, db):
    """PDX Syntax - Query EU5 Paradox script syntax.

    Use fuzzy search to find effects, triggers, scopes, and modifiers
    for Europa Universalis 5 modding.
    """
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = Path(db) if db else DEFAULT_DB_PATH


@main.command()
@click.pass_context
def init(ctx):
    """Initialize or reset the database."""
    db_path = ctx.obj["db_path"]
    init_database(db_path)
    console.print(f"[green]Database initialized at {db_path}[/green]")


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
            _display_effect_detail(result)
        else:
            console.print(f"[yellow]No effect found with name '{query}'[/yellow]")
        return

    results = search_effects(query, scope=scope, category=category, limit=limit, db_path=db_path)

    if not results:
        console.print(f"[yellow]No effects found matching '{query}'[/yellow]")
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
            _display_trigger_detail(result)
        else:
            console.print(f"[yellow]No trigger found with name '{query}'[/yellow]")
        return

    results = search_triggers(query, scope=scope, category=category, limit=limit, db_path=db_path)

    if not results:
        console.print(f"[yellow]No triggers found matching '{query}'[/yellow]")
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
            _display_scope_detail(result)
        else:
            console.print(f"[yellow]No scope found with name '{query}'[/yellow]")
        return

    results = search_scopes(
        query, scope_type=scope_type, iterator_only=iterator, limit=limit, db_path=db_path
    )

    if not results:
        console.print(f"[yellow]No scopes found matching '{query}'[/yellow]")
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
            _display_modifier_detail(result)
        else:
            console.print(f"[yellow]No modifier found with name '{query}'[/yellow]")
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
        console.print(f"[yellow]No modifiers found matching '{query}'[/yellow]")
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
            _display_on_action_detail(result)
        else:
            console.print(f"[yellow]No on_action found with name '{query}'[/yellow]")
        return

    results = search_on_actions(query, scope_type=scope_type, limit=limit, db_path=db_path)

    if not results:
        console.print(f"[yellow]No on_actions found matching '{query}'[/yellow]")
        return

    _display_results_table(results, "On Actions", ["name", "scope_type", "description"])


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

    table = Table(title=f"Changes in {version}")
    table.add_column("Type", style="cyan")
    table.add_column("Change", style="yellow")
    table.add_column("Item", style="green")
    table.add_column("Description")

    for change in change_list:
        table.add_row(
            change["item_type"],
            change["change_type"],
            change["item_name"],
            change.get("description", ""),
        )

    console.print(table)


@main.command()
@click.option("--force", is_flag=True, help="Force update even if recently updated")
@click.option("--comprehensive", is_flag=True, help="Do comprehensive scraping (slower but more complete)")
@click.pass_context
def update(ctx, force, comprehensive):
    """Update the database from wiki sources.

    This fetches the latest data from the EU5 wiki and modding digests.
    Rate limiting is applied to prevent excessive requests.

    Use --comprehensive for thorough scraping that extracts all available
    effects, triggers, scopes, and modifiers from the wiki.
    """
    db_path = ctx.obj["db_path"]

    if comprehensive:
        from .scrapers.comprehensive import comprehensive_update

        console.print("[bold]Starting comprehensive update (this may take a few minutes)...[/bold]")
        try:
            stats = comprehensive_update(db_path, verbose=True)
            console.print("\n[green]Comprehensive update complete![/green]")
            console.print(f"  Effects: {stats.get('effects', 0)}")
            console.print(f"  Triggers: {stats.get('triggers', 0)}")
            console.print(f"  Scopes: {stats.get('scopes', 0)}")
            console.print(f"  Modifiers: {stats.get('modifiers', 0)}")
            console.print(f"  On Actions: {stats.get('on_actions', 0)}")
        except Exception as e:
            console.print(f"[red]Update failed: {e}[/red]")
            import traceback
            traceback.print_exc()
    else:
        from .scrapers.wiki import update_from_wiki

        with console.status("[bold green]Updating database from wiki sources..."):
            try:
                stats = update_from_wiki(db_path, force=force)
                console.print("[green]Update complete![/green]")
                console.print(f"  Effects: {stats.get('effects', 0)}")
                console.print(f"  Triggers: {stats.get('triggers', 0)}")
                console.print(f"  Scopes: {stats.get('scopes', 0)}")
                console.print(f"  Modifiers: {stats.get('modifiers', 0)}")
                console.print(f"  On Actions: {stats.get('on_actions', 0)}")
            except Exception as e:
                console.print(f"[red]Update failed: {e}[/red]")


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
        console.print(f"\n[bold]Description:[/bold] {template_data['description']}")

    if template_data.get("category"):
        console.print(f"[bold]Category:[/bold] {template_data['category']}")

    if template_data.get("template"):
        console.print("\n[bold]Template:[/bold]")
        console.print(Syntax(template_data["template"], "text", theme="monokai"))

    if template_data.get("parameters"):
        console.print(f"\n[bold]Parameters:[/bold] {template_data['parameters']}")


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

    table = Table(title="Syntax Templates")
    table.add_column("Name", style="cyan")
    table.add_column("Category")
    table.add_column("Description")

    for row in rows:
        table.add_row(row["name"], row["category"] or "", (row["description"] or "")[:50])

    console.print(table)


@main.command()
@click.pass_context
def rate_limit(ctx):
    """Show current rate limit status."""
    from .scrapers.wiki import get_rate_limit_status

    status = get_rate_limit_status()

    console.print("\n[bold]Rate Limit Status:[/bold]")
    for domain, info in status.items():
        console.print(f"\n  [cyan]{domain}[/cyan]")
        console.print(f"    Requests (last minute): {info['requests_last_minute']}/{info['limit_per_minute']}")
        console.print(f"    Requests (last hour): {info['requests_last_hour']}/{info['limit_per_hour']}")
        console.print(f"    Can request: {'Yes' if info['can_request'] else 'No'}")
        if info['wait_time'] > 0:
            console.print(f"    Wait time: {info['wait_time']:.1f}s")


@main.command()
@click.pass_context
def stats(ctx):
    """Show database statistics."""
    from .database import get_connection

    db_path = ctx.obj["db_path"]
    conn = get_connection(db_path)
    cursor = conn.cursor()

    tables = ["effects", "triggers", "scopes", "modifiers", "on_actions", "change_log"]

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


def _display_results_table(results: list[dict], title: str, columns: list[str]) -> None:
    """Display search results in a table."""
    table = Table(title=f"{title} ({len(results)} results)")

    for col in columns:
        style = "cyan" if col == "name" else None
        table.add_column(col.replace("_", " ").title(), style=style)

    for result in results:
        row = []
        for col in columns:
            val = result.get(col, "")
            if val is None:
                val = ""
            elif isinstance(val, bool) or col == "is_iterator" or col == "is_boolean":
                val = "Yes" if val else "No"
            elif len(str(val)) > 50:
                val = str(val)[:47] + "..."
            row.append(str(val))
        table.add_row(*row)

    console.print(table)


def _display_effect_detail(effect: dict) -> None:
    """Display detailed information about an effect."""
    console.print(Panel(f"[bold cyan]{effect['name']}[/bold cyan]", title="Effect"))

    if effect.get("description"):
        console.print(f"\n[bold]Description:[/bold] {effect['description']}")

    if effect.get("scope_type"):
        console.print(f"[bold]Scope:[/bold] {effect['scope_type']}")

    if effect.get("category"):
        console.print(f"[bold]Category:[/bold] {effect['category']}")

    if effect.get("syntax"):
        console.print("\n[bold]Syntax:[/bold]")
        console.print(Syntax(effect["syntax"], "text", theme="monokai"))

    if effect.get("parameters"):
        console.print(f"\n[bold]Parameters:[/bold] {effect['parameters']}")

    if effect.get("example"):
        console.print("\n[bold]Example:[/bold]")
        console.print(Syntax(effect["example"], "text", theme="monokai"))


def _display_trigger_detail(trigger: dict) -> None:
    """Display detailed information about a trigger."""
    console.print(Panel(f"[bold cyan]{trigger['name']}[/bold cyan]", title="Trigger"))

    if trigger.get("description"):
        console.print(f"\n[bold]Description:[/bold] {trigger['description']}")

    if trigger.get("scope_type"):
        console.print(f"[bold]Scope:[/bold] {trigger['scope_type']}")

    if trigger.get("category"):
        console.print(f"[bold]Category:[/bold] {trigger['category']}")

    if trigger.get("syntax"):
        console.print("\n[bold]Syntax:[/bold]")
        console.print(Syntax(trigger["syntax"], "text", theme="monokai"))

    if trigger.get("parameters"):
        console.print(f"\n[bold]Parameters:[/bold] {trigger['parameters']}")

    if trigger.get("example"):
        console.print("\n[bold]Example:[/bold]")
        console.print(Syntax(trigger["example"], "text", theme="monokai"))


def _display_scope_detail(scope: dict) -> None:
    """Display detailed information about a scope."""
    console.print(Panel(f"[bold cyan]{scope['name']}[/bold cyan]", title="Scope"))

    if scope.get("description"):
        console.print(f"\n[bold]Description:[/bold] {scope['description']}")

    if scope.get("scope_type"):
        console.print(f"[bold]From Scope:[/bold] {scope['scope_type']}")

    if scope.get("target_type"):
        console.print(f"[bold]Target Type:[/bold] {scope['target_type']}")

    if scope.get("is_iterator"):
        console.print(f"[bold]Iterator:[/bold] Yes")
        if scope.get("iterator_type"):
            console.print(f"[bold]Iterator Type:[/bold] {scope['iterator_type']}")

    if scope.get("syntax"):
        console.print("\n[bold]Syntax:[/bold]")
        console.print(Syntax(scope["syntax"], "text", theme="monokai"))

    if scope.get("parameters"):
        console.print(f"\n[bold]Parameters:[/bold] {scope['parameters']}")


def _display_modifier_detail(modifier: dict) -> None:
    """Display detailed information about a modifier."""
    console.print(Panel(f"[bold cyan]{modifier['name']}[/bold cyan]", title="Modifier"))

    if modifier.get("description"):
        console.print(f"\n[bold]Description:[/bold] {modifier['description']}")

    if modifier.get("category"):
        console.print(f"[bold]Category:[/bold] {modifier['category']}")

    if modifier.get("scope_type"):
        console.print(f"[bold]Scope:[/bold] {modifier['scope_type']}")

    if modifier.get("modifier_type"):
        console.print(f"[bold]Type:[/bold] {modifier['modifier_type']}")

    if modifier.get("is_boolean"):
        console.print(f"[bold]Boolean:[/bold] Yes")

    if modifier.get("default_value"):
        console.print(f"[bold]Default:[/bold] {modifier['default_value']}")

    if modifier.get("color"):
        console.print(f"[bold]Color:[/bold] {modifier['color']}")

    if modifier.get("percent"):
        console.print(f"[bold]Percent:[/bold] Yes")


def _display_on_action_detail(on_action: dict) -> None:
    """Display detailed information about an on_action."""
    console.print(Panel(f"[bold cyan]{on_action['name']}[/bold cyan]", title="On Action"))

    if on_action.get("description"):
        console.print(f"\n[bold]Description:[/bold] {on_action['description']}")

    if on_action.get("scope_type"):
        console.print(f"[bold]Scope:[/bold] {on_action['scope_type']}")

    if on_action.get("category"):
        console.print(f"[bold]Category:[/bold] {on_action['category']}")

    if on_action.get("parameters"):
        console.print(f"\n[bold]Parameters:[/bold] {on_action['parameters']}")

    if on_action.get("example"):
        console.print("\n[bold]Example:[/bold]")
        console.print(Syntax(on_action["example"], "text", theme="monokai"))


if __name__ == "__main__":
    main()
