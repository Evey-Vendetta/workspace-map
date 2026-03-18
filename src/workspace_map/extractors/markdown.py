"""Markdown purpose extractor."""

import os

from workspace_map.extractors import register


def _extract_symbols_markdown(_content: str) -> list:
    """Markdown has no extractable symbols."""
    return []


def purpose_markdown(path: str, content: str) -> str:
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()[:150]
    return os.path.splitext(os.path.basename(path))[0]


# Self-register
register("md", _extract_symbols_markdown, purpose_markdown)
