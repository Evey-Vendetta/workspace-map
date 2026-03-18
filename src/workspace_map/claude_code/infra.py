"""Claude Code infrastructure indexer — orchestrates CC-specific indexing.

Delegates to workspace_map.index for the actual per-category indexing logic.
This module handles CC-specific path discovery and hook wiring parsing.
"""

import json
import os
import re
from collections import defaultdict

from workspace_map.claude_code import get_claude_code_paths


# ---------------------------------------------------------------------------
# Hook wiring parser
# ---------------------------------------------------------------------------


def parse_hook_wiring(cc_paths: dict) -> dict:
    """Return {hook_filename: [event, ...]} by parsing ~/.claude/settings.json.

    Args:
        cc_paths: CC infrastructure paths dict from get_claude_code_paths().
    """
    wiring: dict[str, set] = defaultdict(set)

    home = os.path.expanduser("~")
    settings_files = [
        os.path.join(home, ".claude", "settings.json"),
    ]

    for sf in settings_files:
        sf_exp = os.path.realpath(os.path.expanduser(sf))
        if not os.path.exists(sf_exp):
            continue
        try:
            with open(sf_exp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        hooks_block = data.get("hooks", {})
        for event, entries in hooks_block.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                for hook in entry.get("hooks", []):
                    cmd = hook.get("command", "")
                    # Extract script filename from command string.
                    # Handle quoted paths: find the last .py/.sh/.js component.
                    parts = re.split(r'[\s"\']+', cmd)
                    for part in parts:
                        part = part.replace("\\", "/")
                        if any(part.endswith(ext) for ext in (".py", ".sh", ".js")):
                            fname = os.path.basename(part)
                            wiring[fname].add(event)
                    # Also handle bash.exe -c "...path..." patterns
                    embedded = re.findall(r"([^\s/\"'\\]+\.(?:py|sh|js))", cmd)
                    for e in embedded:
                        wiring[e].add(event)

    return {k: sorted(v) for k, v in wiring.items()}


# ---------------------------------------------------------------------------
# CC infra entry point
# ---------------------------------------------------------------------------


def index_cc_infra(
    config,
    state_cache: dict,
    overrides: dict,
    hook_wiring: dict | None = None,
    force: bool = False,
    verbose: bool = False,
) -> list:
    """Index all Claude Code infrastructure files.

    Discovers CC paths via get_claude_code_paths(), then delegates to the
    per-category indexers in workspace_map.index with the appropriate paths.

    Args:
        config: Config object (used for memory dir discovery and synonyms).
        state_cache: Mtime/size cache from the existing index for delta detection.
        overrides: Manual purpose overrides keyed by normalized path.
        hook_wiring: Pre-parsed {hook_filename: [event, ...]} dict.
                     If None, parsed from ~/.claude/settings.json.
        force: Re-index even unchanged files.
        verbose: Print each entry as indexed.

    Returns:
        List of index entries for all CC infra files.
    """
    from workspace_map.index import (
        index_hooks,
        index_memory,
        index_skills,
        index_plans,
        index_scripts,
        index_rules,
        index_agents_and_commands,
    )
    from workspace_map.claude_code import find_project_dirs

    entries: list = []
    cc_paths = get_claude_code_paths()
    if not cc_paths:
        return entries

    synonyms = config.synonyms if (config and config.synonyms) else None

    if hook_wiring is None:
        hook_wiring = parse_hook_wiring(cc_paths)

    # Hooks
    hooks_dir = cc_paths.get("hooks", "")
    if hooks_dir:
        entries.extend(index_hooks(
            hooks_dir, state_cache, overrides, hook_wiring, force, verbose, synonyms,
        ))

    # Memory — auto-discover from all project memory dirs
    mem_dirs: list[str] = []
    if (config and hasattr(config, "claude_code_memory_dir")
            and config.claude_code_memory_dir not in ("auto", "")):
        mem_dirs = [config.claude_code_memory_dir]
    else:
        for proj in find_project_dirs():
            if proj["memory_dir"]:
                mem_dirs.append(proj["memory_dir"])

    for mem_dir in mem_dirs:
        entries.extend(index_memory(
            mem_dir, state_cache, overrides, force, verbose, synonyms,
        ))

    # Skills
    skills_dir = cc_paths.get("skills", "")
    if skills_dir:
        entries.extend(index_skills(
            skills_dir, state_cache, overrides, force, verbose, synonyms,
        ))

    # Plans
    plans_dir = cc_paths.get("plans", "")
    if plans_dir:
        entries.extend(index_plans(
            plans_dir, state_cache, overrides, force, verbose, synonyms,
        ))

    # Scripts
    scripts_dir = cc_paths.get("scripts", "")
    if scripts_dir:
        entries.extend(index_scripts(
            scripts_dir, state_cache, overrides, force, verbose, synonyms,
        ))

    # Rules
    rules_dir = cc_paths.get("rules", "")
    if rules_dir:
        entries.extend(index_rules(
            rules_dir, state_cache, overrides, force, verbose, synonyms,
        ))

    # Agents and commands (global only from cc_paths; project dirs via config)
    agent_sources: list[tuple[str, str, str]] = []
    agents_dir = cc_paths.get("agents", "")
    commands_dir = cc_paths.get("commands", "")
    if agents_dir:
        agent_sources.append((agents_dir, "agent", "global"))
    if commands_dir:
        agent_sources.append((commands_dir, "command", "global"))

    # Project-specific agent/command dirs from config
    for extra_dir in (getattr(config, "extra_agent_dirs", None) or []):
        agent_sources.append((extra_dir, "agent", "project"))
    for extra_dir in (getattr(config, "extra_command_dirs", None) or []):
        agent_sources.append((extra_dir, "command", "project"))

    if agent_sources:
        entries.extend(index_agents_and_commands(
            agent_sources, state_cache, overrides, force, verbose, synonyms,
        ))

    return entries
