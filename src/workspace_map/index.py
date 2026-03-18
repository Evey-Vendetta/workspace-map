"""Index build, load, save, and per-category indexers for workspace-map."""

import glob as glob_module
import json
import os
from collections import defaultdict
from datetime import datetime

from workspace_map.config import (
    Config,
    RepoConfig,
    expand_path,
    normalize_path,
    default_index_path,
)
from workspace_map.extractors import extract_symbols
from workspace_map.extractors.markdown import purpose_markdown
from workspace_map.extractors.python import purpose_python
from workspace_map.extractors.shell import purpose_shell
from workspace_map.tokenizer import extract_keywords, tokenize

INDEX_VERSION = 4
SKIP_DIRS = {".git", "build", ".dart_tool", "node_modules", "__pycache__", ".gradle"}


# ---------------------------------------------------------------------------
# File utilities
# ---------------------------------------------------------------------------

def read_file_safe(path: str, max_bytes: int = 8192) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_bytes)
    except OSError:
        return ""


def extract_frontmatter(content: str) -> dict:
    """Parse YAML-like frontmatter between --- markers."""
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    block = content[3:end].strip()
    result = {}
    for line in block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


# ---------------------------------------------------------------------------
# State / delta helpers
# ---------------------------------------------------------------------------

def file_state(path: str) -> dict:
    try:
        st = os.stat(path)
        return {"mtime": st.st_mtime, "size": st.st_size}
    except OSError:
        return {"mtime": 0, "size": 0}


def is_changed(norm_path: str, state_cache: dict, real_path: str) -> bool:
    current = file_state(real_path)
    cached = state_cache.get(norm_path)
    if cached is None:
        return True
    return current["mtime"] != cached["mtime"] or current["size"] != cached["size"]


# ---------------------------------------------------------------------------
# Per-category purpose dispatch (used by indexers that need category context)
# ---------------------------------------------------------------------------

def _extract_purpose_by_category(path: str, category: str, content: str | None = None) -> str:
    """Extract purpose with category-aware frontmatter handling."""
    if content is None:
        content = read_file_safe(path)
    ext = os.path.splitext(path)[1].lower()

    if category in ("skill", "memory", "plan", "rule", "command", "agent"):
        fm = extract_frontmatter(content)
        if "description" in fm:
            return fm["description"]

    if ext == ".dart":
        from workspace_map.extractors.dart import purpose_dart
        return purpose_dart(path, content)
    if ext == ".js":
        from workspace_map.extractors.javascript import purpose_js
        return purpose_js(path, content)
    if ext == ".py":
        return purpose_python(path, content)
    if ext in (".sh", ".bash"):
        return purpose_shell(path, content)
    if ext == ".md":
        return purpose_markdown(path, content)
    return os.path.splitext(os.path.basename(path))[0]


# ---------------------------------------------------------------------------
# Code file indexer
# ---------------------------------------------------------------------------

def index_code_files(
    repo: RepoConfig,
    state_cache: dict,
    overrides: dict,
    force: bool,
    verbose: bool,
    synonyms: dict | None = None,
) -> list:
    entries = []
    base = expand_path(repo.path)
    if not os.path.isdir(base):
        return entries

    globs = repo.glob.split(",")
    seen: set[str] = set()
    for pattern in globs:
        for real_path in glob_module.glob(os.path.join(base, pattern.strip()), recursive=True):
            real_path = os.path.realpath(real_path)
            if real_path in seen or not os.path.isfile(real_path):
                continue
            seen.add(real_path)
            norm = normalize_path(real_path)

            if norm in overrides:
                purpose = overrides[norm]
                content = read_file_safe(real_path)  # Need content for symbols
            elif force or is_changed(norm, state_cache, real_path):
                content = read_file_safe(real_path)
                purpose = _extract_purpose_by_category(real_path, "code", content)
            else:
                continue  # Will be merged from existing index

            kw = extract_keywords(purpose, os.path.basename(real_path), synonyms=synonyms)
            symbols = extract_symbols(content, repo.lang)
            entry = {
                "path": norm,
                "repo": repo.name,
                "category": "code",
                "language": repo.lang,
                "purpose": purpose,
                "keywords": kw,
                "symbols": symbols,
                "mtime": file_state(real_path)["mtime"],
                "_real": real_path,
            }
            if verbose:
                print(f"  [code] {norm} — {purpose}")
            entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Repo tree walker
# ---------------------------------------------------------------------------

def walk_repo_tree(repo_path: str) -> list:
    """Walk repo and collect file metadata (path, size, mtime) without reading content."""
    tree = []
    real_root = expand_path(repo_path)
    if not os.path.isdir(real_root):
        return tree
    for dirpath, dirs, files in os.walk(real_root, topdown=True):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            real = os.path.join(dirpath, fname)
            try:
                st = os.stat(real)
                tree.append({
                    "path": normalize_path(real),
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                })
            except OSError:
                continue
    return tree


def build_file_tree(repos: list[RepoConfig]) -> dict:
    """Build file tree for all repos."""
    result = {}
    for repo in repos:
        entries = walk_repo_tree(repo.path)
        if entries:
            result[repo.name] = entries
    return result


# ---------------------------------------------------------------------------
# CC infra indexers (operate on explicit directory paths from Config)
# ---------------------------------------------------------------------------

def index_hooks(
    hooks_dir: str,
    state_cache: dict,
    overrides: dict,
    hook_wiring: dict,
    force: bool,
    verbose: bool,
    synonyms: dict | None = None,
) -> list:
    entries = []
    real_dir = expand_path(hooks_dir)
    if not os.path.isdir(real_dir):
        return entries

    for fname in os.listdir(real_dir):
        real_path = os.path.join(real_dir, fname)
        if not os.path.isfile(real_path):
            continue
        norm = normalize_path(real_path)

        events = hook_wiring.get(fname, [])

        if norm in overrides:
            purpose = overrides[norm]
        elif force or is_changed(norm, state_cache, real_path):
            content = read_file_safe(real_path)
            ext = os.path.splitext(fname)[1].lower()
            if ext == ".py":
                purpose = purpose_python(real_path, content)
            elif ext in (".sh", ".bash"):
                purpose = purpose_shell(real_path, content)
            else:
                purpose = fname
        else:
            continue

        kw = extract_keywords(purpose, fname + " " + " ".join(events), synonyms=synonyms)
        entry = {
            "path": norm,
            "repo": None,
            "category": "hook",
            "event": ", ".join(events) if events else "unknown",
            "purpose": purpose,
            "keywords": kw,
            "mtime": file_state(real_path)["mtime"],
            "_real": real_path,
        }
        if verbose:
            print(f"  [hook] {norm} ({entry['event']}) — {purpose}")
        entries.append(entry)
    return entries


def index_memory(
    memory_dir: str,
    state_cache: dict,
    overrides: dict,
    force: bool,
    verbose: bool,
    synonyms: dict | None = None,
) -> list:
    entries = []
    real_dir = expand_path(memory_dir)
    if not os.path.isdir(real_dir):
        return entries

    for fname in os.listdir(real_dir):
        if not fname.endswith(".md"):
            continue
        real_path = os.path.join(real_dir, fname)
        norm = normalize_path(real_path)

        if norm in overrides:
            purpose = overrides[norm]
        elif force or is_changed(norm, state_cache, real_path):
            content = read_file_safe(real_path)
            fm = extract_frontmatter(content)
            if "description" in fm:
                purpose = fm["description"]
            else:
                purpose = purpose_markdown(real_path, content)
        else:
            continue

        # Infer memory type from filename prefix
        base = os.path.splitext(fname)[0]
        if base.startswith("feedback_"):
            mem_type = "feedback"
        elif base.startswith("project_"):
            mem_type = "project"
        elif base.startswith("reference_"):
            mem_type = "reference"
        elif base == "MEMORY":
            mem_type = "main"
        else:
            mem_type = "misc"

        kw = extract_keywords(purpose, fname, synonyms=synonyms)
        entry = {
            "path": norm,
            "repo": None,
            "category": "memory",
            "memory_type": mem_type,
            "purpose": purpose,
            "keywords": kw,
            "mtime": file_state(real_path)["mtime"],
            "_real": real_path,
        }
        if verbose:
            print(f"  [mem] {norm} ({mem_type}) — {purpose}")
        entries.append(entry)
    return entries


def index_skills(
    skills_dir: str,
    state_cache: dict,
    overrides: dict,
    force: bool,
    verbose: bool,
    synonyms: dict | None = None,
) -> list:
    entries = []
    real_dir = expand_path(skills_dir)
    if not os.path.isdir(real_dir):
        return entries

    for item in os.listdir(real_dir):
        skill_path = os.path.join(real_dir, item)
        if not os.path.isdir(skill_path):
            continue

        # Look for SKILL.md or any .md file
        skill_md = os.path.join(skill_path, "SKILL.md")
        if not os.path.exists(skill_md):
            candidates = [f for f in os.listdir(skill_path) if f.endswith(".md")]
            if not candidates:
                continue
            skill_md = os.path.join(skill_path, candidates[0])

        real_path = skill_md
        norm = normalize_path(skill_path)  # index directory, not the .md

        if norm in overrides:
            purpose = overrides[norm]
        elif force or is_changed(normalize_path(real_path), state_cache, real_path):
            content = read_file_safe(real_path)
            fm = extract_frontmatter(content)
            if "description" in fm:
                purpose = fm["description"]
            else:
                purpose = purpose_markdown(real_path, content)
        else:
            continue

        kw = extract_keywords(purpose, item, synonyms=synonyms)
        entry = {
            "path": norm + "/",
            "repo": None,
            "category": "skill",
            "purpose": purpose,
            "keywords": kw,
            "mtime": file_state(real_path)["mtime"],
            "_real": real_path,   # SKILL.md file, not directory — matches is_changed key
            "_state_key": normalize_path(real_path),  # explicit key for build_state
        }
        if verbose:
            print(f"  [skill] {norm}/ — {purpose}")
        entries.append(entry)
    return entries


def index_plans(
    plans_dir: str,
    state_cache: dict,
    overrides: dict,
    force: bool,
    verbose: bool,
    synonyms: dict | None = None,
) -> list:
    entries = []
    real_dir = expand_path(plans_dir)
    if not os.path.isdir(real_dir):
        return entries

    for fname in os.listdir(real_dir):
        if not fname.endswith(".md"):
            continue
        real_path = os.path.join(real_dir, fname)
        if not os.path.isfile(real_path):
            continue
        norm = normalize_path(real_path)

        if norm in overrides:
            purpose = overrides[norm]
        elif force or is_changed(norm, state_cache, real_path):
            content = read_file_safe(real_path)
            purpose = purpose_markdown(real_path, content)
        else:
            continue

        kw = extract_keywords(purpose, fname, synonyms=synonyms)
        entry = {
            "path": norm,
            "repo": None,
            "category": "plan",
            "purpose": purpose,
            "keywords": kw,
            "mtime": file_state(real_path)["mtime"],
            "_real": real_path,
        }
        if verbose:
            print(f"  [plan] {norm} — {purpose}")
        entries.append(entry)
    return entries


def index_scripts(
    scripts_dir: str,
    state_cache: dict,
    overrides: dict,
    force: bool,
    verbose: bool,
    synonyms: dict | None = None,
) -> list:
    entries = []
    real_dir = expand_path(scripts_dir)
    if not os.path.isdir(real_dir):
        return entries

    for fname in os.listdir(real_dir):
        real_path = os.path.join(real_dir, fname)
        if not os.path.isfile(real_path):
            continue
        norm = normalize_path(real_path)
        ext = os.path.splitext(fname)[1].lower()
        if ext not in (".py", ".sh", ".js", ".bash"):
            continue

        lang = {"py": "python", "sh": "shell", "bash": "shell", "js": "js"}.get(
            ext.lstrip("."), "unknown"
        )

        if norm in overrides:
            purpose = overrides[norm]
            content = read_file_safe(real_path)
        elif force or is_changed(norm, state_cache, real_path):
            content = read_file_safe(real_path)
            if ext == ".py":
                purpose = purpose_python(real_path, content)
            elif ext in (".sh", ".bash"):
                purpose = purpose_shell(real_path, content)
            elif ext == ".js":
                from workspace_map.extractors.javascript import purpose_js
                purpose = purpose_js(real_path, content)
            else:
                purpose = fname
        else:
            continue

        lang_key = ext.lstrip(".")
        symbols = extract_symbols(content, lang_key)
        kw = extract_keywords(purpose, fname, synonyms=synonyms)
        entry = {
            "path": norm,
            "repo": None,
            "category": "script",
            "language": lang,
            "purpose": purpose,
            "keywords": kw,
            "symbols": symbols,
            "mtime": file_state(real_path)["mtime"],
            "_real": real_path,
        }
        if verbose:
            print(f"  [script] {norm} — {purpose}")
        entries.append(entry)
    return entries


def index_rules(
    rules_dir: str,
    state_cache: dict,
    overrides: dict,
    force: bool,
    verbose: bool,
    synonyms: dict | None = None,
) -> list:
    entries = []
    real_dir = expand_path(rules_dir)
    if not os.path.isdir(real_dir):
        return entries

    for fname in os.listdir(real_dir):
        if not fname.endswith(".md"):
            continue
        real_path = os.path.join(real_dir, fname)
        norm = normalize_path(real_path)

        if norm in overrides:
            purpose = overrides[norm]
        elif force or is_changed(norm, state_cache, real_path):
            content = read_file_safe(real_path)
            purpose = purpose_markdown(real_path, content)
        else:
            continue

        kw = extract_keywords(purpose, fname, synonyms=synonyms)
        entry = {
            "path": norm,
            "repo": None,
            "category": "rule",
            "purpose": purpose,
            "keywords": kw,
            "mtime": file_state(real_path)["mtime"],
            "_real": real_path,
        }
        if verbose:
            print(f"  [rule] {norm} — {purpose}")
        entries.append(entry)
    return entries


def index_agents_and_commands(
    sources: list[tuple[str, str, str]],
    state_cache: dict,
    overrides: dict,
    force: bool,
    verbose: bool,
    synonyms: dict | None = None,
) -> list:
    """Index agent and command markdown files.

    `sources` is a list of (dir_path, category, scope) tuples, e.g.:
        [("~/.claude/agents/", "agent", "global"),
         ("~/myproject/.claude/agents/", "agent", "project"), ...]
    """
    entries = []
    for dir_path, category, scope in sources:
        real_dir = expand_path(dir_path)
        if not os.path.isdir(real_dir):
            continue
        for fname in os.listdir(real_dir):
            if not fname.endswith(".md"):
                continue
            real_path = os.path.join(real_dir, fname)
            norm = normalize_path(real_path)

            if norm in overrides:
                purpose = overrides[norm]
            elif force or is_changed(norm, state_cache, real_path):
                content = read_file_safe(real_path)
                fm = extract_frontmatter(content)
                if "description" in fm:
                    purpose = fm["description"]
                else:
                    purpose = purpose_markdown(real_path, content)
            else:
                continue

            kw = extract_keywords(purpose, fname, synonyms=synonyms)
            entry = {
                "path": norm,
                "repo": None,
                "category": category,
                "scope": scope,
                "purpose": purpose,
                "keywords": kw,
                "mtime": file_state(real_path)["mtime"],
                "_real": real_path,
            }
            if verbose:
                print(f"  [{category}] {norm} ({scope}) — {purpose}")
            entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Top-level index_all orchestrator
# ---------------------------------------------------------------------------

def index_all(
    config: Config,
    state_cache: dict,
    overrides: dict,
    hook_wiring: dict | None = None,
    force: bool = False,
    verbose: bool = False,
) -> list:
    """Index all sources described in config.

    Always indexes code files. Delegates CC infra indexing to
    workspace_map.claude_code.infra if available (and config allows it).
    """
    entries: list = []

    # Code files
    synonyms = config.synonyms if config.synonyms else None
    for repo in config.repos:
        entries.extend(index_code_files(repo, state_cache, overrides, force, verbose, synonyms))

    # CC features (if detected and not explicitly disabled)
    if config.claude_code_enabled != "false":
        try:
            from workspace_map.claude_code.infra import index_cc_infra
            entries.extend(
                index_cc_infra(config, state_cache, overrides, hook_wiring or {}, force, verbose)
            )
        except ImportError:
            pass

    return entries


# ---------------------------------------------------------------------------
# Index load / save
# ---------------------------------------------------------------------------

def load_index(index_path: str | None = None) -> dict:
    real = expand_path(index_path or default_index_path())
    if not os.path.exists(real):
        return {
            "_generated": None,
            "_version": INDEX_VERSION,
            "_state": {},
            "entries": [],
            "directories": [],
            "file_tree": {},
        }
    try:
        with open(real, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {
            "_generated": None,
            "_version": INDEX_VERSION,
            "_state": {},
            "entries": [],
            "directories": [],
            "file_tree": {},
        }


def save_index(index: dict, index_path: str | None = None):
    real = expand_path(index_path or default_index_path())
    tmp = real + ".tmp"
    os.makedirs(os.path.dirname(real), exist_ok=True)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
        os.replace(tmp, real)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def build_state(entries: list) -> dict:
    state = {}
    for entry in entries:
        real = entry.get("_real")
        if real and os.path.exists(real):
            # Use explicit state key if set (skills), otherwise derive from path
            norm = entry.get("_state_key") or entry["path"].rstrip("/")
            state[norm] = file_state(real)
    return state


def strip_internal_fields(entries: list) -> list:
    return [{k: v for k, v in entry.items() if not k.startswith("_")} for entry in entries]


def compute_corpus_stats(entries: list) -> dict:
    """Compute BM25 corpus statistics: N, DF per term, avgdl per field.

    Fields tokenized: filename, purpose, keywords, aliases (code only),
    symbols (code only), title/summary (session only).
    """
    if not entries:
        return {"N": 0, "df": {}, "avgdl": {}}

    N = len(entries)
    df: dict[str, int] = defaultdict(int)  # term -> number of docs containing it
    field_lengths: dict[str, list] = defaultdict(list)  # field_name -> [len_per_doc]

    FIELDS = ["filename", "purpose", "keywords", "aliases", "symbols", "title", "summary"]

    for entry in entries:
        path = entry.get("path", "")
        filename = os.path.basename(path.rstrip("/"))
        doc_terms: set[str] = set()

        field_texts = {
            "filename": filename,
            "purpose": entry.get("purpose", ""),
            "keywords": " ".join(entry.get("keywords", [])),
            "aliases": " ".join(entry.get("aliases", [])),
            "symbols": " ".join(s["name"] for s in entry.get("symbols", [])[:50]),
            "title": entry.get("title", ""),
            "summary": entry.get("summary", "") or "",
        }

        for field_name, text in field_texts.items():
            tokens = tokenize(text, filter_stops=False, dedupe=False)
            field_lengths[field_name].append(len(tokens))
            doc_terms.update(tokens)

        for term in doc_terms:
            df[term] += 1

    avgdl = {}
    for field_name in FIELDS:
        lengths = field_lengths.get(field_name, [])
        avgdl[field_name] = sum(lengths) / max(len(lengths), 1)

    return {"N": N, "df": dict(df), "avgdl": avgdl}
