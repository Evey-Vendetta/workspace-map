"""Shell script symbol and purpose extractors."""

import os
import re

from workspace_map.extractors import register


def extract_symbols_shell(content: str) -> list:
    """Extract function definitions and key env vars from Shell scripts."""
    symbols = []
    for line in content.split("\n"):
        stripped = line.strip()
        # Function: name() { or function name {
        m = re.match(r"^(?:function\s+)?(\w+)\s*\(\)", stripped)
        if m:
            symbols.append({"kind": "function", "name": m.group(1)})
            continue
        m = re.match(r"^function\s+(\w+)", stripped)
        if m:
            symbols.append({"kind": "function", "name": m.group(1)})
            continue
        # Environment variable (UPPER_CASE export or assignment)
        m = re.match(r"^(?:export\s+)?([A-Z][A-Z0-9_]{2,})\s*=", stripped)
        if m:
            symbols.append({"kind": "const", "name": m.group(1)})
            continue
    return symbols


def purpose_shell(path: str, content: str) -> str:
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#!"):
            continue
        if line.startswith("#"):
            return line.lstrip("#").strip()[:150]
    return os.path.splitext(os.path.basename(path))[0]


# Self-register
register("sh", extract_symbols_shell, purpose_shell)
