"""Claude Code integration — auto-detected, disabled when .claude/ not found."""

import os


def has_claude_code() -> bool:
    """Check if Claude Code is installed (looks for ~/.claude/ directory)."""
    return os.path.isdir(os.path.join(os.path.expanduser("~"), ".claude"))


def get_claude_code_paths() -> dict | None:
    """Return paths to CC infrastructure dirs, or None if not found."""
    if not has_claude_code():
        return None
    home = os.path.expanduser("~")
    claude_dir = os.path.join(home, ".claude")
    return {
        "hooks": os.path.join(claude_dir, "hooks"),
        "scripts": os.path.join(claude_dir, "scripts"),
        "skills": os.path.join(claude_dir, "skills"),
        "plans": os.path.join(claude_dir, "plans"),
        "rules": os.path.join(claude_dir, "rules"),
        "agents": os.path.join(claude_dir, "agents"),
        "commands": os.path.join(claude_dir, "commands"),
        "analytics": os.path.join(claude_dir, "analytics"),
        # Memory and sessions are project-specific — discovered separately
    }


def find_project_dirs() -> list[dict]:
    """Find all Claude Code project directories under ~/.claude/projects/."""
    projects_dir = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    if not os.path.isdir(projects_dir):
        return []
    results = []
    for entry in os.listdir(projects_dir):
        proj_path = os.path.join(projects_dir, entry)
        if os.path.isdir(proj_path):
            memory_dir = os.path.join(proj_path, "memory")
            results.append(
                {
                    "name": entry,
                    "path": proj_path,
                    "has_memory": os.path.isdir(memory_dir),
                    "memory_dir": memory_dir if os.path.isdir(memory_dir) else None,
                }
            )
    return results
