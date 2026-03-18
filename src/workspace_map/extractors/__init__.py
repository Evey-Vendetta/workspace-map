"""Extractor registry for workspace-map.

Language-specific symbol and purpose extractors register themselves here.
All built-in extractors are imported at module load so they self-register.
"""

EXTRACTORS: dict = {}  # lang -> {"symbols": fn, "purpose": fn}


def register(lang: str, symbols_fn, purpose_fn) -> None:
    """Register symbol and purpose extractors for a language key."""
    EXTRACTORS[lang] = {"symbols": symbols_fn, "purpose": purpose_fn}


def extract_symbols(content: str, language: str) -> list:
    """Dispatch to language-specific symbol extractor. Returns [] for unknown langs."""
    if language in EXTRACTORS:
        return EXTRACTORS[language]["symbols"](content)
    return []


def extract_purpose(path: str, content: str, language: str) -> str:
    """Dispatch to language-specific purpose extractor. Returns basename for unknown langs."""
    if language in EXTRACTORS:
        return EXTRACTORS[language]["purpose"](path, content)
    import os
    return os.path.splitext(os.path.basename(path))[0]


# Auto-import all built-in extractors so they self-register
from workspace_map.extractors import dart  # noqa: E402, F401
from workspace_map.extractors import python  # noqa: E402, F401
from workspace_map.extractors import javascript  # noqa: E402, F401
from workspace_map.extractors import shell  # noqa: E402, F401
from workspace_map.extractors import markdown  # noqa: E402, F401
