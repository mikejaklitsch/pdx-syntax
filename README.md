# pdx-syntax

CLI tool for querying Europa Universalis 5 script syntax. EU5 launched after most LLMs were trained, so AI coding assistants have no knowledge of the game's scripting language. This tool provides a queryable SQLite knowledge base built from the game's own documentation dumps, so LLMs (and humans) can look up correct syntax instead of hallucinating it. Search uses rapidfuzz for fuzzy matching and SQLite FTS5 for full-text queries across effects, triggers, scopes, modifiers, on-actions, data types, and custom localization functions.

## Scope & Purpose

**What this tool does:**
- Quick lookups of EU5 script syntax elements by name
- Fuzzy search with filtering by scope type, category
- Display syntax patterns, parameters, usage examples
- Did-you-mean suggestions and cross-table hints on misses
- Warn when the game has patched and the database is stale

**What this tool does NOT do:**
- Syntax validation or linting of your script files
- Code generation or scaffolding
- IDE/editor integration

## Installation

```bash
pipx install git+https://github.com/mikejaklitsch/pdx-syntax
# or from a clone:
pip install -e .
```

The repo ships with a fully built database (`src/pdx_syntax/data/eu5_syntax.db`), so searches work immediately after install. Rebuild it yourself only when the game patches (see Updating below).

## Quick Start

```bash
pdx-syntax effect add_gold
pdx-syntax trigger "is at war"
pdx-syntax scope army --iterator
pdx-syntax modifier discipline
pdx-syntax on_action monthly
pdx-syntax promote GetCapital --type Country
pdx-syntax custom-loc grain --entries
pdx-syntax search "army morale" --type modifiers
pdx-syntax info          # full search guide: what lives where
```

## Output Modes

Two renderers, chosen automatically:

- **Terminal:** rich tables. Cells fold-wrap; nothing is ever truncated. If the terminal is too narrow to give every column readable width, the command falls back to flat text on its own.
- **Piped / non-TTY** (agents, scripts, `| less`): flat text blocks with full descriptions. No table layout, no column squeezing, no data loss.

Force either mode with `--plain` or `--table` (global options, e.g. `pdx-syntax --plain effect add_gold`).

## Updating After a Game Patch

The database is built from files the game itself dumps. When EU5 patches:

1. Launch the game with `-debug_mode` and open the console.
2. Run the docs dump (`script_docs`) — writes `docs/*.log` (effects, triggers, modifiers, on_actions, event_targets, custom_localization) to the Paradox user directory.
3. Run the data-types dump (`DumpDataTypes`; check console autocomplete if the name differs in your version) — writes `logs/data_types/`.
4. Run:

```bash
pdx-syntax update
```

`update` auto-detects the game version, warns if the dumps predate the current game install, and records the game's patch checksum. Afterwards every `pdx-syntax` invocation compares that stored checksum against the live install and prints a warning to stderr the moment the game patches ahead of the database.

Paths default to the author's machine; override with environment variables:

| Variable | Meaning | Default |
|----------|---------|---------|
| `PDX_USER_DIR` | Paradox user dir (contains `docs/`, `logs/`) | `~/Documents/Paradox Interactive/Europa Universalis V` (WSL path) |
| `PDX_GAME_ROOT` | Game install root (for `binaries/checksum.txt`) | Steam library install |

Or pass `--docs-dir` / `--data-types-dir` to `update` directly.

## Commands

| Command | Description |
|---------|-------------|
| `effect <query>` | Search effects |
| `trigger <query>` | Search triggers |
| `scope <query>` | Search scopes/iterators |
| `modifier <query>` | Search modifiers |
| `on_action <query>` | Search on_actions |
| `promote <query>` | Search data types (promotes, functions) |
| `custom-loc <query>` | Search custom localization functions |
| `search <query>` | Full-text search |
| `note add\|list\|rm` | Attach findings to entries |
| `template <name>` / `templates` | Syntax templates |
| `categories` / `scopes` | List filter values |
| `changes <version>` | Show version changes |
| `stats` | Database statistics |
| `update` | Rebuild DB from game dumps |
| `seed` | Load built-in fallback data only |
| `init` | Initialize an empty database |

## Search Options

All search commands support:

- `-n, --limit N` - Maximum results (default: 10)
- `--exact` - Exact name match with full detail view

Effect/Trigger: `-s/--scope`, `-c/--category`. Scope: `-t/--type`, `--iterator`. Modifier: `-c/--category`, `-s/--scope`, `--boolean`. Promote: `-t/--type`, `-c/--category`, `-d/--definition`. Custom-loc: `-s/--scope`, `-e/--entries`.

## Database Location

Default: `src/pdx_syntax/data/eu5_syntax.db` inside the installed package (shipped pre-built). Override with `--db /path/to/database.db`.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
