"""Session transcript indexing for Claude Code."""

import json
import os
import re

from workspace_map.config import normalize_path
from workspace_map.index import file_state, read_file_safe
from workspace_map.tokenizer import extract_keywords

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

SYSTEM_REMINDER_RE = re.compile(
    r"<system-reminder>.*?</system-reminder>", re.DOTALL | re.IGNORECASE
)
XML_TAG_RE = re.compile(r"<[^>]+>.*?</[^>]+>|<[^>]+/>", re.DOTALL)
HANDOFF_SESSION_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}) — Session (\d+): (.+)$", re.MULTILINE)

# Prefixes that indicate system-injected content, not real user messages
SYSTEM_CONTENT_PREFIXES = (
    "<local-command-caveat>",
    "<ide_opened_file>",
    "<ide_action>",
    "<system-reminder>",
    "<available-deferred-tools>",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_changed(norm_path: str, state_cache: dict, real_path: str) -> bool:
    current = file_state(real_path)
    cached = state_cache.get(norm_path)
    if cached is None:
        return True
    return current["mtime"] != cached["mtime"] or current["size"] != cached["size"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def generate_aliases_batch(
    entries: list,
    state_cache: dict,
    force_all: bool = False,
    verbose: bool = False,
) -> None:
    """Alias generation via Haiku — not yet implemented.

    This stub exists so `wmap rebuild --aliases` fails gracefully rather than
    raising an ImportError. A full implementation would call the claude CLI
    once per batch to generate searchable aliases for each code entry.
    """
    print("Warning: --aliases is not yet implemented. Skipping alias generation.")


def parse_handoff_sessions(handoff_files: list[str]) -> dict:
    """Parse HANDOFF files and return {date_str: [(session_num, title), ...]}.

    Args:
        handoff_files: List of paths to HANDOFF.md / archive.md files to parse.
    """
    sessions = {}
    for hf in handoff_files:
        real = os.path.realpath(os.path.expanduser(hf))
        if not os.path.exists(real):
            continue
        content = read_file_safe(real, max_bytes=200000)
        for m in HANDOFF_SESSION_RE.finditer(content):
            date_str, num, title = m.group(1), m.group(2), m.group(3)
            sessions.setdefault(date_str, []).append((f"S{num}", title.strip()))
    return sessions


def strip_session_content(content: str) -> str:
    """Strip system-reminder tags and tool results from JSONL content."""
    content = SYSTEM_REMINDER_RE.sub("", content)
    return content


def extract_session_text(real_path: str) -> str:
    """Extract user+assistant text from a JSONL transcript file for summarization."""
    content = read_file_safe(real_path, max_bytes=200000)
    lines = content.splitlines()
    texts = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg_type = obj.get("type", "")
        if msg_type not in ("user", "assistant"):
            continue
        # Skip tool_result content blocks entirely
        msg_obj = obj.get("message", {})
        raw_content = msg_obj.get("content", "") if isinstance(msg_obj, dict) else ""
        text = ""
        if isinstance(raw_content, str):
            text = strip_session_content(raw_content)
        elif isinstance(raw_content, list):
            parts = []
            for part in raw_content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", ""))
            text = strip_session_content(" ".join(parts))
        if text.strip():
            texts.append(f"[{msg_type}]: {text.strip()[:1000]}")
    return "\n".join(texts)


def index_sessions_basic(
    transcripts_dir: str,
    handoff_files: list[str],
    state_cache: dict,
    force: bool,
    verbose: bool,
) -> list:
    """Basic session indexer: date, title from first user message, keywords.

    Args:
        transcripts_dir: Path to the directory containing .jsonl transcript files.
        handoff_files: Paths to HANDOFF.md / archive.md files for session numbering.
        state_cache: Mtime/size cache from the existing index for delta detection.
        force: If True, re-index even unchanged files.
        verbose: If True, print each entry as it is indexed.
    """
    from datetime import datetime

    handoff_map = parse_handoff_sessions(handoff_files)
    entries = []

    transcripts_real = os.path.realpath(os.path.expanduser(transcripts_dir))
    if not os.path.isdir(transcripts_real):
        return entries

    jsonl_files = [
        f
        for f in os.listdir(transcripts_real)
        if f.endswith(".jsonl") and os.path.isfile(os.path.join(transcripts_real, f))
    ]

    for fname in jsonl_files:
        real_path = os.path.join(transcripts_real, fname)
        norm = normalize_path(real_path)

        if not force and not _is_changed(norm, state_cache, real_path):
            continue

        # 256KB — large sessions can have late first user msg
        content = read_file_safe(real_path, max_bytes=262144)
        lines = content.splitlines()

        first_user_msg = ""
        date_str = ""
        user_texts = []
        msg_count = 0

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = obj.get("type", "")
            ts = obj.get("timestamp", "")
            if ts and not date_str:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    date_str = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass

            if msg_type == "user":
                msg_count += 1
                msg_obj = obj.get("message", {})
                raw_content = msg_obj.get("content", "") if isinstance(msg_obj, dict) else ""
                text = ""
                if isinstance(raw_content, str):
                    text = strip_session_content(raw_content)
                elif isinstance(raw_content, list):
                    parts = []
                    for part in raw_content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            parts.append(part.get("text", ""))
                    text = strip_session_content(" ".join(parts))

                text = text.strip()
                # Skip system-injected content
                if text and any(text.startswith(p) for p in SYSTEM_CONTENT_PREFIXES):
                    continue
                # Strip remaining XML tags for cleaner titles
                text = XML_TAG_RE.sub("", text).strip()
                if text and len(text) > 20:
                    if not first_user_msg:
                        first_user_msg = text[:80]
                    user_texts.append(text[:500])

            elif msg_type == "assistant":
                msg_count += 1

        if not date_str and not first_user_msg:
            continue
        # Skip sessions with no substantive user content (subagent stubs)
        if not user_texts:
            continue

        title = first_user_msg[:80] if first_user_msg else fname
        keywords = extract_keywords(" ".join(user_texts[:10]))
        file_size = 0
        try:
            file_size = os.path.getsize(real_path)
        except OSError:
            pass

        entry = {
            "path": norm,
            "repo": None,
            "category": "session",
            "session": None,
            "title": title,
            "date": date_str,
            "summary": None,
            "orphaned_ideas": [],
            "decisions": [],
            "files_modified": [],
            "tools_used": [],
            "procedures": [],
            "keywords": keywords,
            "mtime": file_state(real_path)["mtime"],
            "_real": real_path,
            "_msg_count": msg_count,
        }
        entry["_file_size"] = file_size
        entries.append(entry)

    # Second pass: assign HANDOFF session numbers to largest session per date
    # Group entries by date
    by_date = {}
    for e in entries:
        by_date.setdefault(e["date"], []).append(e)
    for date_str, date_entries in by_date.items():
        if date_str not in handoff_map:
            continue
        handoff_list = handoff_map[date_str]
        # Sort sessions by file size (largest first) — main sessions are biggest
        date_entries.sort(key=lambda e: e.get("_file_size", 0), reverse=True)
        # Assign HANDOFF entries to the N largest sessions
        for i, (snum, stitle) in enumerate(handoff_list):
            if i < len(date_entries):
                date_entries[i]["session"] = snum
                date_entries[i]["title"] = stitle

    if verbose:
        for e in entries:
            label = e["session"] or "S?"
            print(f"  [sess] {label} ({e['date']}) — {e['title']}")

    return entries
