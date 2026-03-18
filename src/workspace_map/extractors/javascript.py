"""JavaScript symbol and purpose extractors."""

import os
import re

from workspace_map.extractors import register


def extract_symbols_js(content: str) -> list:
    """Extract exported functions, classes, and top-level const from JavaScript."""
    symbols = []
    for line in content.split("\n"):
        stripped = line.strip()
        # Class
        m = re.match(r"^(?:export\s+)?class\s+(\w+)", stripped)
        if m:
            symbols.append({"kind": "class", "name": m.group(1)})
            continue
        # Exported/top-level function
        m = re.match(r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)", stripped)
        if m:
            symbols.append({"kind": "function", "name": m.group(1)})
            continue
        # Arrow function const
        m = re.match(r"^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(", stripped)
        if m:
            symbols.append({"kind": "function", "name": m.group(1)})
            continue
        # Regular const
        m = re.match(r"^(?:export\s+)?const\s+(\w+)\s*=", stripped)
        if m:
            symbols.append({"kind": "const", "name": m.group(1)})
            continue
        # module.exports member
        m = re.match(r"^\s*(\w+)\s*:\s*(?:async\s+)?function", stripped)
        if m:
            symbols.append({"kind": "function", "name": m.group(1)})
            continue
    return symbols


def purpose_js(path: str, content: str) -> str:
    comment_re = re.compile(r"/\*\*(.*?)\*/|//\s*(.+)", re.DOTALL)
    cm = comment_re.search(content)
    comment = ""
    if cm:
        raw = (cm.group(1) or cm.group(2) or "").strip()
        comment = re.sub(r"\s+", " ", raw.replace("*", "")).strip()

    name_re = re.compile(
        r"(?:class\s+(\w+)|function\s+(\w+)|module\.exports\s*=\s*(?:class\s+)?(\w+))"
    )
    nm = name_re.search(content)
    name = ""
    if nm:
        name = nm.group(1) or nm.group(2) or nm.group(3) or ""

    base = os.path.splitext(os.path.basename(path))[0]
    if name and comment:
        return f"{name} — {comment[:120]}"
    if name:
        return name
    if comment:
        return comment[:120]
    return base


# Self-register
register("js", extract_symbols_js, purpose_js)
