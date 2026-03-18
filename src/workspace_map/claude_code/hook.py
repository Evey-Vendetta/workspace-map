"""Install the workspace-map PreToolUse hook for Claude Code."""

import json
import os
import shutil
import sys

# The hook script content — generalized from workspace-map-reminder.py.
# Uses sys.executable at install time so the shebang matches the current Python.
HOOK_CONTENT = '''\
#!/usr/bin/env python3
"""PreToolUse hook for Glob — reminds to use workspace-map find instead of exploratory Glob.

Fires on every Glob call. If the pattern looks like natural-language exploration
(not an exact extension glob like **/*.dart), emits a reminder and blocks the call.

Install:
    wmap install-hook

Or manually copy to ~/.claude/hooks/ and register in ~/.claude/settings.json:
    {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Glob", "hooks": [{"type": "command", "command": "python ~/.claude/hooks/workspace-map-reminder.py"}]}
            ]
        }
    }
"""
import json
import re
import sys


def is_exact_pattern(pattern: str) -> bool:
    """Return True if pattern is a precise glob (extension, exact path), not exploratory."""
    # Exact extension globs: **/*.dart, src/**/*.tsx, *.py
    if re.match(r\'^[\\w./\\\\*-]+\\*.\\w+$\', pattern):
        return True
    # Exact file path: lib/services/foo.dart
    if re.match(r\'^[\\w./\\\\-]+\\.\\w+$\', pattern):
        return True
    return False


def main():
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input", {})
    pattern = tool_input.get("pattern", "")

    if is_exact_pattern(pattern):
        # Exact pattern — Glob is the right tool
        sys.exit(0)

    # Exploratory pattern — remind about workspace-map
    msg = (
        "STOP: Use workspace-map find before Glob for exploratory searches.\\n"
        "Command: wmap find \\"<query>\\"\\n"
        "Glob is for exact extension/path patterns only (e.g., **/*.dart)."
    )
    print(msg, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
'''

HOOK_FILENAME = "workspace-map-reminder.py"
SETTINGS_FILENAME = "settings.json"


def _get_hooks_dir() -> str:
    return os.path.join(os.path.expanduser("~"), ".claude", "hooks")


def _get_settings_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".claude", SETTINGS_FILENAME)


def _register_in_settings(settings_path: str) -> bool:
    """Add the PreToolUse Glob hook entry to settings.json.

    Returns True if settings were modified, False if already present.
    """
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except (json.JSONDecodeError, OSError):
            settings = {}
    else:
        settings = {}

    hooks = settings.setdefault("hooks", {})
    pre_tool_use = hooks.setdefault("PreToolUse", [])

    hook_cmd = f"{sys.executable} ~/.claude/hooks/{HOOK_FILENAME}"

    # Check if already registered
    for entry in pre_tool_use:
        for h in entry.get("hooks", []):
            if HOOK_FILENAME in h.get("command", ""):
                return False  # Already registered

    # Append the new entry
    pre_tool_use.append({
        "matcher": "Glob",
        "hooks": [{"type": "command", "command": hook_cmd}],
    })

    tmp_path = settings_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, settings_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return True


def install_hook(dry_run: bool = False) -> dict:
    """Install the PreToolUse hook to ~/.claude/hooks/ and register it in settings.json.

    Args:
        dry_run: If True, report what would be done without making changes.

    Returns:
        Dict with keys:
            hook_path (str): Path where the hook was (or would be) written.
            settings_path (str): Path to settings.json.
            hook_written (bool): True if hook file was written.
            settings_updated (bool): True if settings.json was updated.
            already_installed (bool): True if hook was already in place.
    """
    hooks_dir = _get_hooks_dir()
    hook_path = os.path.join(hooks_dir, HOOK_FILENAME)
    settings_path = _get_settings_path()

    result = {
        "hook_path": hook_path,
        "settings_path": settings_path,
        "hook_written": False,
        "settings_updated": False,
        "already_installed": False,
    }

    # Check if Claude Code is available
    claude_dir = os.path.join(os.path.expanduser("~"), ".claude")
    if not os.path.isdir(claude_dir):
        raise RuntimeError(
            "Claude Code not found (~/.claude/ does not exist). "
            "Install Claude Code before running this command."
        )

    # Check if hook already exists
    hook_exists = os.path.exists(hook_path)

    if dry_run:
        result["hook_written"] = not hook_exists
        result["already_installed"] = hook_exists
        return result

    # Write hook file
    os.makedirs(hooks_dir, exist_ok=True)
    with open(hook_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(HOOK_CONTENT)
    result["hook_written"] = True

    # Make executable on Unix-like systems
    if sys.platform != "win32":
        try:
            import stat
            st = os.stat(hook_path)
            os.chmod(hook_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass

    # Register in settings.json
    result["settings_updated"] = _register_in_settings(settings_path)
    result["already_installed"] = hook_exists and not result["settings_updated"]

    return result
