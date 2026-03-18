"""Configuration loading and auto-discovery for workspace-map."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RepoConfig:
    name: str
    path: str
    lang: str
    glob: str


@dataclass
class Config:
    repos: list[RepoConfig] = field(default_factory=list)
    synonyms: dict[str, str] = field(default_factory=dict)
    directories: dict[str, str] = field(default_factory=dict)
    index_path: str = ""
    claude_code_enabled: str = "auto"   # "auto", "true", "false"
    claude_code_sessions_dir: str = "auto"
    claude_code_memory_dir: str = "auto"


# ---------------------------------------------------------------------------
# Path utilities
# ---------------------------------------------------------------------------

def normalize_path(path: str) -> str:
    """Normalize path: resolve, forward slashes, ~ for home."""
    path = os.path.realpath(path)
    path = path.replace("\\", "/")
    home = os.path.expanduser("~").replace("\\", "/")
    if path.startswith(home):
        path = "~" + path[len(home):]
    return path


def expand_path(path: str) -> str:
    """Expand ~ and normalize to OS path for filesystem operations."""
    return os.path.realpath(os.path.expanduser(path))


def short_path(norm_path: str) -> str:
    """Return the normalized path as-is (already uses ~)."""
    return norm_path


# ---------------------------------------------------------------------------
# Default index path
# ---------------------------------------------------------------------------

def default_index_path() -> str:
    """Return ~/.cache/workspace-map/index.json, creating the dir if needed."""
    cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "workspace-map")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, "index.json").replace("\\", "/")


# ---------------------------------------------------------------------------
# Claude Code detection
# ---------------------------------------------------------------------------

def detect_claude_code() -> dict | None:
    """Check if ~/.claude/ exists and return paths to CC infrastructure.

    Returns a dict with keys: sessions, memory, skills, hooks, plans, rules,
    agents, commands — each pointing to the relevant directory. Returns None
    if ~/.claude/ is not found.
    """
    cc_root = os.path.expanduser("~/.claude")
    if not os.path.isdir(cc_root):
        return None

    def _d(rel: str) -> str:
        return os.path.join(cc_root, rel).replace("\\", "/") + "/"

    result = {
        "root": cc_root.replace("\\", "/") + "/",
        "hooks": _d("hooks"),
        "scripts": _d("scripts"),
        "skills": _d("skills"),
        "plans": _d("plans"),
        "rules": _d("rules"),
        "agents": _d("agents"),
        "commands": _d("commands"),
    }

    # Memory lives under projects/ — pick the first subdirectory that has a
    # memory/ subfolder if it exists, otherwise return the projects dir.
    projects_dir = os.path.join(cc_root, "projects")
    memory_candidates = []
    if os.path.isdir(projects_dir):
        for entry in os.listdir(projects_dir):
            mem_path = os.path.join(projects_dir, entry, "memory")
            if os.path.isdir(mem_path):
                memory_candidates.append(mem_path.replace("\\", "/") + "/")
    result["memory_dirs"] = memory_candidates

    # Sessions are JSONL files directly inside project dirs
    session_dirs = []
    if os.path.isdir(projects_dir):
        for entry in os.listdir(projects_dir):
            proj_path = os.path.join(projects_dir, entry)
            if os.path.isdir(proj_path):
                has_jsonl = any(
                    f.endswith(".jsonl")
                    for f in os.listdir(proj_path)
                    if os.path.isfile(os.path.join(proj_path, f))
                )
                if has_jsonl:
                    session_dirs.append(proj_path.replace("\\", "/") + "/")
    result["session_dirs"] = session_dirs

    return result


# ---------------------------------------------------------------------------
# Auto-discovery
# ---------------------------------------------------------------------------

_LANG_EXTENSIONS = {
    ".dart": "dart",
    ".py": "py",
    ".js": "js",
    ".ts": "js",
    ".rs": "rust",
    ".go": "go",
    ".sh": "sh",
    ".bash": "sh",
    ".rb": "rb",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
}

_LANG_GLOBS = {
    "dart": "lib/**/*.dart",
    "py": "**/*.py",
    "js": "**/*.js",
    "rust": "src/**/*.rs",
    "go": "**/*.go",
    "sh": "**/*.sh",
    "rb": "**/*.rb",
    "java": "src/**/*.java",
    "kotlin": "src/**/*.kt",
    "swift": "Sources/**/*.swift",
    "cpp": "src/**/*.cpp",
    "c": "src/**/*.c",
}


def _detect_language(repo_path: str) -> tuple[str, str]:
    """Detect primary language and glob pattern for a repo directory."""
    counts: dict[str, int] = {}
    try:
        for dirpath, dirs, files in os.walk(repo_path):
            # Skip common non-source dirs
            dirs[:] = [d for d in dirs if d not in {
                ".git", "build", "node_modules", "__pycache__", ".dart_tool",
                "target", "dist", "out", ".gradle",
            }]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in _LANG_EXTENSIONS:
                    lang = _LANG_EXTENSIONS[ext]
                    counts[lang] = counts.get(lang, 0) + 1
    except OSError:
        pass

    if not counts:
        return "unknown", "**/*"

    primary = max(counts, key=lambda k: counts[k])
    glob_pattern = _LANG_GLOBS.get(primary, "**/*")
    return primary, glob_pattern


def auto_discover_repos(root: str | None = None, max_depth: int = 2) -> list[RepoConfig]:
    """Walk dirs for .git folders, detect language, return list of RepoConfig.

    Searches `root` (defaults to home dir) up to `max_depth` levels deep.
    """
    if root is None:
        root = os.path.expanduser("~")

    root = os.path.realpath(root)
    repos: list[RepoConfig] = []
    seen: set[str] = set()

    def _walk(path: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = os.listdir(path)
        except OSError:
            return

        if ".git" in entries and path not in seen:
            seen.add(path)
            name = os.path.basename(path)
            lang, glob_pattern = _detect_language(path)
            repos.append(RepoConfig(
                name=name,
                path=normalize_path(path),
                lang=lang,
                glob=glob_pattern,
            ))
            return  # Don't recurse into nested git repos

        for entry in entries:
            child = os.path.join(path, entry)
            if os.path.isdir(child) and not entry.startswith("."):
                _walk(child, depth + 1)

    _walk(root, 0)
    return repos


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

_CONFIG_SEARCH_PATHS = [
    "workspace-map.yaml",
    "workspace-map.yml",
    os.path.expanduser("~/.config/workspace-map/workspace-map.yaml"),
    os.path.expanduser("~/.config/workspace-map/config.yaml"),
]


def _parse_yaml_config(data: dict) -> Config:
    """Parse a YAML config dict into a Config object."""
    repos = []
    for r in data.get("repos", []):
        resolved = os.path.realpath(os.path.expanduser(r["path"]))
        if ".." in os.path.normpath(resolved).split(os.sep):
            raise ValueError(f"Repo path must not contain '..': {r['path']}")
        glob_pattern = r.get("glob", "**/*")
        if glob_pattern.startswith(".."):
            raise ValueError(f"Glob pattern must not start with '..': {glob_pattern}")
        repos.append(RepoConfig(
            name=r["name"],
            path=r["path"],
            lang=r.get("lang", "unknown"),
            glob=glob_pattern,
        ))

    return Config(
        repos=repos,
        synonyms=data.get("synonyms", {}),
        directories=data.get("directories", {}),
        index_path=data.get("index_path", ""),
        claude_code_enabled=str(data.get("claude_code_enabled", "auto")),
        claude_code_sessions_dir=str(data.get("claude_code_sessions_dir", "auto")),
        claude_code_memory_dir=str(data.get("claude_code_memory_dir", "auto")),
    )


def load_config(path: str | None = None) -> Config:
    """Load workspace-map config from a YAML file.

    Search order:
    1. Explicit `path` argument (if provided)
    2. workspace-map.yaml in cwd
    3. ~/.config/workspace-map/workspace-map.yaml

    Returns an empty Config if no file is found. Requires pyyaml; if not
    installed, returns an empty Config with a warning printed to stderr.
    """
    import sys

    search = [path] if path else []
    search.extend(_CONFIG_SEARCH_PATHS)

    for candidate in search:
        if candidate is None:
            continue
        real = expand_path(candidate)
        if not os.path.isfile(real):
            continue

        try:
            with open(real, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return _parse_yaml_config(data)
        except Exception as exc:
            print(f"Warning: failed to parse {real}: {exc}", file=sys.stderr)
            return Config()

    return Config()
