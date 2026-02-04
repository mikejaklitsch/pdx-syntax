# pdx-syntax

CLI tool for querying Europa Universalis 5 Paradox script syntax. Provides fast fuzzy search for effects, triggers, scopes, modifiers, and on_actions.

## Installation

```bash
pip install -e .
```

## Quick Start

```bash
# Initialize and seed the database
pdx-syntax init
pdx-syntax seed

# Search for effects
pdx-syntax effect add_gold
pdx-syntax effect "create character" --scope country

# Search for triggers
pdx-syntax trigger has_variable
pdx-syntax trigger "is at war"

# Search for scopes/iterators
pdx-syntax scope every_country
pdx-syntax scope army --iterator

# Search for modifiers
pdx-syntax modifier discipline
pdx-syntax modifier tax --category economic

# Search for on_actions
pdx-syntax on_action death
pdx-syntax on_action monthly

# View syntax templates
pdx-syntax templates
pdx-syntax template event_structure

# View version changes
pdx-syntax changes 1.1.0
```

## Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize the database |
| `seed` | Seed with built-in EU5 syntax data |
| `update` | Fetch latest data from EU5 wiki |
| `effect <query>` | Search effects |
| `trigger <query>` | Search triggers |
| `scope <query>` | Search scopes/iterators |
| `modifier <query>` | Search modifiers |
| `on_action <query>` | Search on_actions |
| `search <query>` | Full-text search |
| `template <name>` | Show syntax template |
| `templates` | List all templates |
| `categories` | List categories |
| `scopes` | List scope types |
| `changes <version>` | Show version changes |
| `stats` | Show database statistics |
| `rate_limit` | Show rate limit status |

## Search Options

All search commands support:

- `-n, --limit N` - Maximum results (default: 10)
- `--exact` - Exact name match only

Effect/Trigger specific:
- `-s, --scope TYPE` - Filter by scope type
- `-c, --category CAT` - Filter by category

Scope specific:
- `-t, --type TYPE` - Filter by scope type
- `--iterator` - Show only iterators

Modifier specific:
- `-c, --category CAT` - Filter by category
- `-s, --scope TYPE` - Filter by scope type
- `--boolean` - Show only boolean modifiers

## Data Sources

Data is sourced from:

- [EU5 Wiki](https://eu5.paradoxwikis.com/) - Effects, triggers, scopes, modifiers
- [Modding Digests](https://github.com/Europa-Universalis-5-Modding-Co-op/modding-digests) - Version changes

## Rate Limiting

The tool includes built-in rate limiting to prevent excessive requests:

- 10 requests per minute per domain
- 100 requests per hour per domain

Use `pdx-syntax rate_limit` to check current status.

## Database Location

Default: `~/.local/share/pdx-syntax/eu5_syntax.db`

Override with `--db /path/to/database.db`

## Version Tracking

The database tracks changes across EU5 versions. Use `pdx-syntax changes <version>` to see what changed in a specific version.

Tracked versions: 1.0.0, 1.0.2, 1.0.3, 1.0.4, 1.0.5, 1.0.7, 1.0.8, 1.0.9, 1.0.10, 1.1.0

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src tests
ruff check src tests
```

## License

MIT
