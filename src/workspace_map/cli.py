"""CLI entry point for the `wmap` command."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

from workspace_map.claude_code import has_claude_code
from workspace_map.config import (
    Config,
    auto_discover_repos,
    default_index_path,
    expand_path,
    load_config,
    normalize_path,
)
from workspace_map.index import (
    INDEX_VERSION,
    build_file_tree,
    build_state,
    compute_corpus_stats,
    index_all,
    load_index,
    save_index,
    strip_internal_fields,
)
from workspace_map.search import find as search_find

# ---------------------------------------------------------------------------
# ANSI colors (no external deps)
# ---------------------------------------------------------------------------

_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _color(text: str, code: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def green(text: str) -> str:
    return _color(text, "32")


def yellow(text: str) -> str:
    return _color(text, "33")


def red(text: str) -> str:
    return _color(text, "31")


def cyan(text: str) -> str:
    return _color(text, "36")


# ---------------------------------------------------------------------------
# Output formatting (mirrors monolith format_entry)
# ---------------------------------------------------------------------------

CAT_TAGS = {
    "code": "[code]",
    "hook": "[hook]",
    "memory": "[mem] ",
    "skill": "[skill]",
    "plan": "[plan]",
    "script": "[script]",
    "rule": "[rule]",
    "agent": "[agent]",
    "command": "[cmd] ",
    "session": "[sess]",
    "file_tree": "[tree]",
}


def format_entry(entry: dict) -> str:
    cat = entry.get("category", "")
    tag = CAT_TAGS.get(cat, f"[{cat}]")
    path = entry.get("path", "")
    purpose = entry.get("purpose") or entry.get("description") or ""

    if cat == "hook":
        event = entry.get("event", "")
        if event:
            return f"{tag}  {path} ({event}) — {purpose}"
        return f"{tag}  {path} — {purpose}"

    if cat == "memory":
        mem_type = entry.get("memory_type", "")
        fname = os.path.basename(path)
        if mem_type:
            return f"{tag}  {fname} ({mem_type}) — {purpose}"
        return f"{tag}  {fname} — {purpose}"

    if cat == "session":
        session_num = entry.get("session") or "S?"
        date = entry.get("date", "")
        title = entry.get("title", "")
        return f"{tag}  {session_num} ({date}) — {title}"

    if cat in ("agent", "command"):
        scope = entry.get("scope", "")
        if scope:
            return f"{tag}  {path} ({scope}) — {purpose}"

    if cat == "file_tree":
        size = entry.get("size", 0)
        if size >= 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        elif size >= 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size} B"
        return f"{tag}  {path} ({size_str})"

    return f"{tag}  {path} — {purpose}"


# ---------------------------------------------------------------------------
# Config / index helpers
# ---------------------------------------------------------------------------

def _require_config() -> Config:
    """Load config or print a helpful error and exit."""
    cfg = load_config()
    if not cfg.repos and not has_claude_code():
        print(
            red("Error: no workspace-map.yaml found and no Claude Code detected."),
            file=sys.stderr,
        )
        print(
            "  Run `wmap init` to generate a workspace-map.yaml for this directory.",
            file=sys.stderr,
        )
        sys.exit(1)
    return cfg


def _load_index_or_exit(cfg: Config | None = None) -> dict:
    """Load the index, suggesting rebuild if empty."""
    index_path = (cfg.index_path if cfg and cfg.index_path else None)
    index = load_index(index_path)
    if not index.get("entries"):
        print(yellow("Index is empty. Run: wmap rebuild"), file=sys.stderr)
        sys.exit(1)
    return index


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> None:
    """Scan cwd for git repos and generate workspace-map.yaml."""
    try:
        import yaml
    except ImportError:
        print(
            red("Error: pyyaml is required for `wmap init`. Install with: pip install pyyaml"),
            file=sys.stderr,
        )
        sys.exit(1)

    cwd = os.getcwd()
    print(f"Scanning {normalize_path(cwd)} for git repos...")
    repos = auto_discover_repos(root=cwd)

    if not repos:
        print(yellow("No git repos found. Are you in the right directory?"))
        return

    out_path = os.path.join(cwd, "workspace-map.yaml")

    repo_dicts = []
    for r in repos:
        repo_dicts.append({
            "name": r.name,
            "path": r.path,
            "lang": r.lang,
            "glob": r.glob,
        })

    data: dict = {
        "repos": repo_dicts,
        "claude_code_enabled": "auto",
    }

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(green(f"Wrote {normalize_path(out_path)}"))
    for r in repos:
        print(f"  {r.name:<20} {r.path}  ({r.lang})")
    print(f"\nNext: run `wmap rebuild` to build the index.")


def cmd_find(args: argparse.Namespace) -> None:
    cfg = _require_config()
    index = _load_index_or_exit(cfg)

    limit = getattr(args, "limit", 10) or 10
    results = search_find(
        query=args.query,
        index=index,
        config=cfg,
        type_filter=getattr(args, "type", None),
        scope_filter=getattr(args, "scope", None),
        use_bm25=not getattr(args, "no_bm25", False),
        max_results=max(limit, 30) if getattr(args, "semantic", False) else limit,
    )

    if getattr(args, "semantic", False) and results:
        from workspace_map.reranker import rerank_with_haiku
        results = rerank_with_haiku(args.query, results)
        results = results[:limit]

    if not results:
        print(f"No results for '{args.query}'")
        return

    output_json = getattr(args, "json", False)
    verbose = getattr(args, "verbose", False)

    if output_json:
        out = []
        for s, e in results:
            row = dict(e)
            if verbose:
                row["_score"] = s
            out.append(row)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return

    for s, entry in results:
        line = format_entry(entry)
        if verbose:
            print(f"({s:.1f}) {line}")
            if entry.get("aliases"):
                print(f"      aliases: {', '.join(entry['aliases'][:5])}")
            if entry.get("symbols"):
                sym_strs = [f"{sym['name']} ({sym['kind']})" for sym in entry["symbols"][:5]]
                print(f"      symbols: {', '.join(sym_strs)}")
        else:
            print(line)


def cmd_repos(args: argparse.Namespace) -> None:
    cfg = _require_config()
    index = _load_index_or_exit(cfg)

    counts: dict[str, int] = defaultdict(int)
    for e in index["entries"]:
        if e.get("category") == "code" and e.get("repo"):
            counts[e["repo"]] += 1

    print("Repos:")
    for repo in cfg.repos:
        real = expand_path(repo.path)
        exists = os.path.isdir(real)
        n = counts.get(repo.name, 0)
        status = f"{n} files" if exists else yellow("(not found)")
        print(f"  {repo.name:<20} {repo.path:<50} {status}")


def cmd_hooks(args: argparse.Namespace) -> None:
    cfg = _require_config()
    index = _load_index_or_exit(cfg)
    hooks = [e for e in index["entries"] if e.get("category") == "hook"]
    if not hooks:
        print("No hooks indexed.")
        return
    print(f"Hooks ({len(hooks)}):")
    for e in sorted(hooks, key=lambda x: x.get("event", "")):
        print(f"  {format_entry(e)}")


def cmd_memory(args: argparse.Namespace) -> None:
    cfg = _require_config()
    index = _load_index_or_exit(cfg)
    entries = [e for e in index["entries"] if e.get("category") == "memory"]
    if not entries:
        print("No memory files indexed.")
        return
    print(f"Memory files ({len(entries)}):")
    for e in sorted(entries, key=lambda x: x.get("memory_type", "")):
        print(f"  {format_entry(e)}")


def cmd_skills(args: argparse.Namespace) -> None:
    cfg = _require_config()
    index = _load_index_or_exit(cfg)
    entries = [e for e in index["entries"] if e.get("category") == "skill"]
    if not entries:
        print("No skills indexed.")
        return
    print(f"Skills ({len(entries)}):")
    for e in sorted(entries, key=lambda x: x.get("path", "")):
        print(f"  {format_entry(e)}")


def cmd_plans(args: argparse.Namespace) -> None:
    cfg = _require_config()
    index = _load_index_or_exit(cfg)
    entries = [e for e in index["entries"] if e.get("category") == "plan"]
    active = [e for e in entries if "/archive/" not in e.get("path", "")]
    if not active:
        print("No active plans indexed.")
        return
    print(f"Active plans ({len(active)}):")
    for e in sorted(active, key=lambda x: x.get("path", "")):
        print(f"  {format_entry(e)}")


def cmd_sessions(args: argparse.Namespace) -> None:
    cfg = _require_config()
    index = _load_index_or_exit(cfg)
    entries = [e for e in index["entries"] if e.get("category") == "session"]
    if not entries:
        print("No sessions indexed.")
        return

    def sort_key(e: dict):
        date = e.get("date", "")
        session = e.get("session") or "S0"
        num_str = session.lstrip("S")
        num = int(num_str) if num_str.isdigit() else 0
        return (date, num)

    entries_sorted = sorted(entries, key=sort_key, reverse=True)
    print(f"Sessions ({len(entries_sorted)}, newest first):")
    for e in entries_sorted:
        print(f"  {format_entry(e)}")


def cmd_dirs(args: argparse.Namespace) -> None:
    cfg = _require_config()
    index = _load_index_or_exit(cfg)
    directories = index.get("directories", [])
    if not directories:
        print(yellow("No directory map in index. Run `wmap rebuild` to populate it."))
        return

    repo_dirs = [d for d in directories if d.get("repo")]
    infra_dirs = [d for d in directories if not d.get("repo")]

    print("## Repos")
    for d in sorted(repo_dirs, key=lambda x: x.get("path", "")):
        print(f"  {d['path']:<52} {d.get('description', '')}")

    if infra_dirs:
        print("\n## CC Infra")
        for d in sorted(infra_dirs, key=lambda x: x.get("path", "")):
            print(f"  {d['path']:<52} {d.get('description', '')}")


def cmd_stats(args: argparse.Namespace) -> None:
    cfg = _require_config()
    index_path = cfg.index_path or default_index_path()
    index = load_index(index_path)

    generated = index.get("_generated")
    version = index.get("_version", INDEX_VERSION)
    entries = index.get("entries", [])
    dirs = index.get("directories", [])

    counts: dict[str, int] = defaultdict(int)
    for e in entries:
        counts[e.get("category", "unknown")] += 1

    code_entries = [e for e in entries if e.get("category") == "code"]
    code_repos = sorted({e["repo"] for e in code_entries if e.get("repo")})

    try:
        idx_size = os.path.getsize(expand_path(index_path))
        size_str = f"{idx_size / 1024:.1f} KB"
    except OSError:
        size_str = "N/A"

    print("Workspace Map Index")
    print(f"  Generated:  {generated or 'never'}")
    print(f"  Version:    {version}")
    print(f"  Entries:    {len(entries)} total")
    for cat in ["code", "hook", "memory", "skill", "plan", "script", "session",
                "agent", "command", "rule"]:
        count = counts.get(cat, 0)
        if count:
            print(f"    {cat:<12} {count}")
    print(f"  Directories: {len(dirs)}")
    print(f"  Repos:      {len(code_repos)} ({', '.join(code_repos) or 'none indexed'})")
    print(f"  Index size: {size_str}")

    tree = index.get("file_tree", {})
    tree_total = sum(len(v) for v in tree.values())
    print(f"  File tree:  {tree_total} files across {len(tree)} repos")

    sym_count = sum(len(e.get("symbols", [])) for e in code_entries)
    alias_entries = [e for e in code_entries if e.get("aliases")]
    alias_pct = (len(alias_entries) / len(code_entries) * 100) if code_entries else 0
    print(f"  Symbols:    {sym_count} across {len(code_entries)} code files")
    print(f"  Alias coverage: {len(alias_entries)}/{len(code_entries)} ({alias_pct:.0f}%)")


def cmd_update(args: argparse.Namespace) -> None:
    _do_build(args, force=False)


def cmd_rebuild(args: argparse.Namespace) -> None:
    _do_build(args, force=True)


def _do_build(args: argparse.Namespace, force: bool) -> None:
    cfg = _require_config()
    verbose = getattr(args, "verbose", False)

    index_path = cfg.index_path or default_index_path()
    existing = load_index(index_path)
    state_cache = existing.get("_state", {})
    old_entries_by_path = {e["path"]: e for e in existing.get("entries", [])}

    print("Building workspace index...")

    for repo in cfg.repos:
        print(f"  Scanning repo: {repo.name}")

    # index_all handles code + CC infra
    new_entries = index_all(
        config=cfg,
        state_cache=state_cache,
        overrides={},
        hook_wiring=None,
        force=force,
        verbose=verbose,
    )

    # Sessions (via CC module if available)
    session_entries: list = []
    if has_claude_code():
        try:
            from workspace_map.claude_code import find_project_dirs
            from workspace_map.claude_code.sessions import index_sessions_basic
            print("  Scanning sessions...")
            for proj in find_project_dirs():
                proj_path = proj["path"]
                session_entries.extend(
                    index_sessions_basic(
                        transcripts_dir=proj_path,
                        handoff_files=[],
                        state_cache=state_cache,
                        force=force,
                        verbose=verbose,
                    )
                )
        except Exception as exc:
            print(f"Warning: session indexing skipped: {exc}", file=sys.stderr)

    new_entries.extend(session_entries)

    # Aliases on full rebuild
    if force and getattr(args, "aliases", False):
        try:
            import asyncio
            from workspace_map.claude_code.sessions import generate_aliases_batch  # type: ignore
            code_entries = [e for e in new_entries if e.get("category") == "code"]
            if code_entries:
                print("  Generating aliases...")
                asyncio.run(generate_aliases_batch(code_entries, state_cache, force_all=True,
                                                   verbose=verbose))
        except (ImportError, AttributeError):
            pass

    # Build file tree
    print("  Building file tree...")
    file_tree = build_file_tree(cfg.repos)

    # Merge
    if force:
        merged_by_path: dict = {}
    else:
        merged_by_path = dict(old_entries_by_path)
    for e in new_entries:
        merged_by_path[e["path"]] = e

    all_entries = list(merged_by_path.values())

    # Re-derive _real for entries that had it stripped
    for e in all_entries:
        if "_real" not in e:
            e["_real"] = expand_path(e["path"].rstrip("/"))

    new_state = build_state(all_entries)

    # Preserve _alias_mtime from old state
    for key, val in new_state.items():
        old_cached = state_cache.get(key, {})
        if "_alias_mtime" in old_cached:
            val["_alias_mtime"] = old_cached["_alias_mtime"]

    print("  Computing corpus statistics...")
    corpus_stats = compute_corpus_stats(all_entries)

    index = {
        "_generated": datetime.now().isoformat(timespec="seconds"),
        "_version": INDEX_VERSION,
        "_state": new_state,
        "_corpus_stats": corpus_stats,
        "entries": strip_internal_fields(all_entries),
        "directories": existing.get("directories", []),
        "file_tree": file_tree,
    }

    save_index(index, index_path)
    total = len(index["entries"])
    print(green(f"Done. {total} entries indexed."))


def cmd_consolidate(args: argparse.Namespace) -> None:
    """Propose memory file consolidation using Haiku."""
    import re
    import subprocess

    from workspace_map.claude_code import get_claude_code_paths

    cc_paths = get_claude_code_paths()
    if not cc_paths:
        print(red("Error: Claude Code not found (~/.claude/ does not exist)."), file=sys.stderr)
        sys.exit(1)

    # Collect memory dirs from all project dirs
    from workspace_map.claude_code import find_project_dirs
    mem_dirs = [
        p["memory_dir"] for p in find_project_dirs() if p["memory_dir"]
    ]

    if not mem_dirs:
        print("No memory directories found.")
        return

    entries = []
    for mem_dir in mem_dirs:
        real_dir = expand_path(mem_dir)
        if not os.path.isdir(real_dir):
            continue
        for fname in sorted(os.listdir(real_dir)):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(real_dir, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                st = os.stat(fpath)
                mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
            except OSError:
                mtime = "unknown"

            first_line = ""
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    in_frontmatter = False
                    for line in f:
                        stripped = line.strip()
                        if stripped == "---":
                            in_frontmatter = not in_frontmatter
                            continue
                        if in_frontmatter:
                            continue
                        if stripped:
                            first_line = stripped[:100]
                            break
            except OSError:
                pass

            first_line = first_line.replace("{", "{{").replace("}", "}}").replace("|", ";")
            entries.append(f"{fname} | {mtime} | {first_line}")

    if not entries:
        print("No memory files found.")
        return

    PROMPT = (
        "You are a memory file organizer for a software project.\n"
        "Today: {today}\n\n"
        "Memory files (name | last-modified | first line):\n{entries_text}\n\n"
        "Identify:\n"
        "1. merge: groups of 2+ files covering the same topic\n"
        "2. stale: files not modified in >30 days that may be outdated\n"
        "3. duplicate: files with near-identical content\n\n"
        "Respond with JSON: {{\"merge\": [[...]], \"stale\": [...], \"duplicate\": [...], \"notes\": \"...\"}}"
    )

    entries_text = "\n".join(entries)
    today = datetime.now().strftime("%Y-%m-%d")
    prompt_text = PROMPT.format(today=today, entries_text=entries_text)

    print(f"Analyzing {len(entries)} memory files...")
    try:
        proc = subprocess.run(
            ["claude", "-p", "--model", "haiku"],
            input=prompt_text,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"claude exit {proc.returncode}: {proc.stderr[:200]}")
        raw = proc.stdout.strip()
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw).strip()
        result = json.loads(raw)
    except FileNotFoundError:
        print(red("Error: 'claude' not found in PATH."), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(red(f"Error: consolidation analysis failed: {e}"), file=sys.stderr)
        sys.exit(1)

    merges = result.get("merge", [])
    stale = result.get("stale", [])
    dupes = result.get("duplicate", [])
    notes = result.get("notes", "")

    if merges:
        print("\nMERGE (files covering the same topic):")
        for i, group in enumerate(merges, 1):
            print(f"  {i}. {', '.join(group)}")

    if stale:
        print("\nSTALE (not modified in >30 days):")
        for fname in stale:
            print(f"  - {fname}")

    if dupes:
        print("\nDUPLICATE (near-identical content):")
        for fname in dupes:
            print(f"  - {fname}")

    if notes:
        print(f"\nNotes: {notes}")

    if not merges and not stale and not dupes:
        print("\nNo consolidation actions proposed. Memory looks clean.")

    print("\nNo changes made. Review proposed actions and apply manually.")


def cmd_install_hook(args: argparse.Namespace) -> None:
    dry_run = getattr(args, "dry_run", False)
    try:
        from workspace_map.claude_code.hook import install_hook
        result = install_hook(dry_run=dry_run)
    except RuntimeError as e:
        print(red(f"Error: {e}"), file=sys.stderr)
        sys.exit(1)

    if result.get("already_installed"):
        print(yellow("Hook already installed. Nothing changed."))
        return

    if dry_run:
        print("Dry run — no changes made.")
        print(f"  Would write: {result['hook_path']}")
        print(f"  Would update: {result['settings_path']}")
        return

    if result.get("hook_written"):
        print(green(f"Hook written: {result['hook_path']}"))
    if result.get("settings_updated"):
        print(green(f"Registered in: {result['settings_path']}"))
    else:
        print(yellow("settings.json already contained the hook entry."))

    print("\nThe PreToolUse hook will now block exploratory Glob calls and "
          "suggest `wmap find` instead.")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser(cc_available: bool) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wmap",
        description="Workspace index and search CLI for multi-repo projects.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    sub.add_parser("init", help="Scan cwd for git repos and generate workspace-map.yaml")

    # find
    p_find = sub.add_parser("find", help="Search entries across the workspace")
    p_find.add_argument("query", help="Search query")
    p_find.add_argument("--type", help="Filter by language (dart, py, sh, js, md, rust)")
    p_find.add_argument(
        "--scope",
        help="Filter by category (code, hook, memory, skill, plan, script, session, agent, command, rule)",
    )
    p_find.add_argument("--json", action="store_true", help="Output as JSON")
    p_find.add_argument("--verbose", action="store_true", help="Show match scores and metadata")
    p_find.add_argument("--semantic", action="store_true",
                        help="Rerank results semantically via Haiku (requires claude in PATH)")
    p_find.add_argument("--limit", type=int, default=10, metavar="N",
                        help="Maximum results to return (default: 10)")
    p_find.add_argument("--no-bm25", action="store_true",
                        help="Disable BM25 scoring, use original keyword-bag scorer only")

    # repos
    sub.add_parser("repos", help="List indexed repos with file counts")

    # dirs
    sub.add_parser("dirs", help="Directory map")

    # stats
    sub.add_parser("stats", help="Index metadata: age, version, entry counts")

    # update
    p_update = sub.add_parser("update", help="Incremental re-index (changed files only)")
    p_update.add_argument("--verbose", action="store_true", help="Print each entry as indexed")

    # rebuild
    p_rebuild = sub.add_parser("rebuild", help="Full re-index (all files)")
    p_rebuild.add_argument("--verbose", action="store_true", help="Print each entry as indexed")
    p_rebuild.add_argument("--aliases", action="store_true",
                           help="Force regeneration of all aliases")

    # CC-only commands — only added when ~/.claude/ exists
    if cc_available:
        sub.add_parser("hooks", help="List CC hooks with event and purpose")
        sub.add_parser("memory", help="List CC memory files")
        sub.add_parser("skills", help="List CC skills")
        sub.add_parser("plans", help="List active plans (not archived)")
        sub.add_parser("sessions", help="List CC session transcripts (newest first)")
        sub.add_parser("consolidate", help="Propose memory dedup suggestions via Haiku")

        p_hook = sub.add_parser("install-hook", help="Install PreToolUse Glob hook for Claude Code")
        p_hook.add_argument("--dry-run", action="store_true",
                            help="Show what would be installed without making changes")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

COMMAND_MAP = {
    "init": cmd_init,
    "find": cmd_find,
    "repos": cmd_repos,
    "hooks": cmd_hooks,
    "memory": cmd_memory,
    "skills": cmd_skills,
    "plans": cmd_plans,
    "sessions": cmd_sessions,
    "dirs": cmd_dirs,
    "stats": cmd_stats,
    "update": cmd_update,
    "rebuild": cmd_rebuild,
    "consolidate": cmd_consolidate,
    "install-hook": cmd_install_hook,
}


def main() -> None:
    cc_available = has_claude_code()
    parser = build_parser(cc_available)
    args = parser.parse_args()

    handler = COMMAND_MAP.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
