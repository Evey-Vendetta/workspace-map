# workspace-map

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![CI](https://img.shields.io/github/actions/workflow/status/Evey-Vendetta/workspace-map/ci.yml?label=CI)](https://github.com/Evey-Vendetta/workspace-map/actions)

**Multi-repo code indexer with BM25 search.**

Index all your repos into one searchable index. Find code by natural language,
not just exact strings. Optional Claude Code integration auto-detected.

## Features

- **Multi-repo indexing** — Dart, Python, JavaScript/TypeScript, Shell, Markdown; language auto-detected per repo
- **BM25 ranking** — proper information retrieval scoring, not grep; documents ranked by relevance
- **Symbol extraction** — classes, functions, methods, enums, constants extracted per language and included in search scoring
- **Incremental updates** — mtime + size cache skips unchanged files; `wmap update` re-indexes only what changed
- **Natural language search** — camelCase splitting (`billingService` → `billing service`), synonym expansion, stop word filtering
- **Claude Code integration** — auto-detects `~/.claude/`; indexes hooks, skills, plans, memory files, rules, agents, commands, and session transcripts
- **LLM reranking** — optional semantic reranking via Anthropic API (requires `pip install workspace-map[ai]`)

## Quick Start

```bash
pip install workspace-map

# Initialize config in the current directory
wmap init

# Build the index from scratch
wmap rebuild

# Search
wmap find "authentication service"
wmap find "database migration handler"
wmap find "hook that fires before tool use"
```

`wmap init` writes a `workspace-map.yaml` in the current directory populated
with git repos auto-discovered up to 2 directories deep. Edit it to add names,
descriptions, and synonyms, then run `wmap rebuild`.

## CLI Reference

| Command | Description |
|---------|-------------|
| `wmap find "<query>"` | Search the index; returns ranked results with file paths |
| `wmap find "<query>" --top N` | Limit results to top N (default: 10) |
| `wmap find "<query>" --category code` | Filter by category: `code`, `hook`, `skill`, `memory`, `plan`, `script`, `rule`, `session` |
| `wmap find "<query>" --repo myrepo` | Filter to a single repo |
| `wmap init` | Write a starter `workspace-map.yaml` with auto-discovered repos |
| `wmap rebuild` | Full re-index of all repos and CC infra |
| `wmap rebuild --force` | Re-index all files, ignoring mtime cache |
| `wmap rebuild --verbose` | Print each file as it is indexed |
| `wmap update` | Incremental update — re-index only changed files |
| `wmap repos` | List all repos in the current config |
| `wmap hooks` | List all indexed Claude Code hooks |
| `wmap memory` | List all indexed memory files |
| `wmap skills` | List all indexed skills |
| `wmap plans` | List all indexed plan files |
| `wmap scripts` | List all indexed scripts |
| `wmap sessions` | List all indexed session transcripts |
| `wmap dirs` | List all directory-level entries in the index |
| `wmap stats` | Show index statistics: entry counts per category, index size, last build time |
| `wmap consolidate` | Merge duplicate entries and prune stale paths from the index |
| `wmap install-hook` | Install the PreToolUse Glob hook for Claude Code |

All commands accept `--config <path>` to use a config file other than
the default. Run `wmap <command> --help` for full flag reference.

## Configuration

workspace-map looks for `workspace-map.yaml` in the current directory, then
`~/.config/workspace-map/workspace-map.yaml`.

```yaml
repos:
  - path: ~/projects/myapp
    name: myapp
    description: "Flutter mobile app — screens, widgets, services, state"

  - path: ~/projects/myapp-backend
    name: backend
    description: "Cloud Functions — HTTP endpoints, database triggers"

# Additional non-git directories to index
extra_dirs:
  - path: ~/.claude/skills
    name: cc-skills
    description: "Claude Code skill scripts"

# Synonym expansion — terms that map to each other in search
synonyms:
  - [auth, authentication, login, signin]
  - [purchase, in_app_purchase, subscription, billing]

# Patterns to exclude (relative to repo root)
exclude:
  - "**/.dart_tool/**"
  - "**/build/**"
  - "**/*.g.dart"

# Override index location (default: ~/.cache/workspace-map/index.json)
# index_path: ~/my-index.json
```

### Config keys

| Key | Default | Description |
|-----|---------|-------------|
| `repos[].path` | required | Path to git repo (supports `~`) |
| `repos[].name` | required | Short identifier used in search output |
| `repos[].description` | `""` | Added to search scoring for the repo root |
| `repos[].lang` | auto-detected | Force language: `dart`, `py`, `js`, `sh`, etc. |
| `repos[].glob` | auto | Override file glob, e.g. `lib/**/*.dart` |
| `extra_dirs` | `[]` | Additional directories indexed as a flat file list |
| `synonyms` | `[]` | Lists of terms that expand to each other at query time |
| `exclude` | `[]` | Glob patterns to skip (matched against relative paths) |
| `index_path` | `~/.cache/workspace-map/index.json` | Where to write the index |
| `claude_code_enabled` | `"auto"` | `"auto"`, `"true"`, or `"false"` |

## Claude Code Integration

When `~/.claude/` is found, workspace-map automatically indexes Claude Code
infrastructure files alongside your source code:

| Category | Source | What gets indexed |
|----------|--------|-------------------|
| `hook` | `~/.claude/hooks/` | Hook scripts with their wiring events parsed from `settings.json` |
| `skill` | `~/.claude/skills/` | Skill directories; description from `SKILL.md` frontmatter |
| `plan` | `~/.claude/plans/` | Plan markdown files |
| `memory` | `~/.claude/projects/*/memory/` | Per-project memory files; typed as `feedback`, `reference`, `project`, or `main` |
| `rule` | `~/.claude/rules/` | Rule markdown files |
| `script` | `~/.claude/scripts/` | Utility scripts with symbol extraction |
| `agent` | `~/.claude/agents/` | Agent definition files |
| `command` | `~/.claude/commands/` | Slash command definitions |
| `session` | `~/.claude/projects/*/` | Session transcripts (`.jsonl`) with title and date extracted |

Set `claude_code_enabled: "false"` in config to disable CC indexing entirely.

### PreToolUse hook

`wmap install-hook` installs a PreToolUse hook that blocks exploratory Glob
calls and reminds to use `wmap find` instead. It writes the hook to
`~/.claude/hooks/workspace-map-reminder.py` and registers it in
`~/.claude/settings.json` under the `Glob` matcher.

```bash
wmap install-hook          # install and register
wmap install-hook --dry-run  # preview what would be installed
```

The hook distinguishes exact extension globs (`**/*.dart`, `src/**/*.tsx`)
from exploratory patterns and only blocks the latter.

## Adding Language Support

Built-in extractors live in `src/workspace_map/extractors/`. Each module
handles one language.

1. Create `src/workspace_map/extractors/<lang>.py` with two functions:

   ```python
   def extract_symbols_<lang>(content: str) -> list[dict]:
       """Return dicts with 'kind' and 'name' keys (optionally 'parent')."""
       ...

   def purpose_<lang>(path: str, content: str) -> str:
       """Return a short description of the file's purpose."""
       ...
   ```

   `kind` values follow the existing convention: `"class"`, `"function"`,
   `"method"`, `"enum"`, `"mixin"`, `"extension"`, `"const"`.

2. Self-register at module bottom:

   ```python
   from workspace_map.extractors import register
   register("<lang>", extract_symbols_<lang>, purpose_<lang>)
   ```

3. Add the auto-import to `src/workspace_map/extractors/__init__.py`:

   ```python
   from workspace_map.extractors import <lang>  # noqa: E402, F401
   ```

4. Add file extension mapping in `src/workspace_map/config.py`
   (`_LANG_EXTENSIONS` and `_LANG_GLOBS`).

5. Add tests in `tests/test_extractor_<lang>.py` and update `README.md`.

See `src/workspace_map/extractors/dart.py` for a complete reference
implementation with class/method/constant extraction and doc-comment
purpose inference.

## License

MIT — see [LICENSE](LICENSE).
