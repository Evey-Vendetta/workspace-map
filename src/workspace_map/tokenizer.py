"""Tokenizer, stop words, and synonyms for workspace-map."""

import re
from collections import defaultdict

# ---------------------------------------------------------------------------
# Stop words
# ---------------------------------------------------------------------------

STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "is",
    "it",
    "be",
    "as",
    "at",
    "this",
    "that",
    "was",
    "are",
    "were",
    "been",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "can",
    "shall",
    "not",
    "no",
    "so",
    "if",
    "by",
    "from",
    "up",
    "out",
    "about",
    "into",
    "then",
    "than",
    "also",
    "just",
    "its",
    "it's",
    "i",
    "we",
    "you",
    "he",
    "she",
    "they",
    "my",
    "your",
    "our",
    "their",
    "what",
    "which",
    "who",
    "how",
    "when",
    "where",
    "all",
    "any",
    "each",
    "more",
    "some",
    "there",
    "these",
    "those",
    "new",
    "one",
    "two",
    "three",
    "get",
    "got",
    "let",
    "want",
    "need",
    "make",
    "made",
    "see",
    "look",
    "like",
    "going",
    "go",
    "now",
    "here",
    "s",
    "re",
    "ve",
    "ll",
    "t",
    "m",
    "d",
    "tool",
    "bash",
    "file",
    "please",
    "using",
    "would",
    "claude",
    "code",
    "run",
    "write",
    "add",
    "help",
    "create",
    "check",
    "update",
    "read",
    "note",
    "message",
    "result",
    "response",
    "output",
    "input",
    "yes",
    "sure",
    "okay",
    "ok",
    "hi",
    "hello",
    "thanks",
    "thank",
    "done",
    "good",
    "great",
    "right",
    "think",
    "know",
    "try",
    "use",
    "used",
    "work",
    "works",
    "working",
    "error",
    "fix",
    "build",
    "change",
    "changes",
    "following",
    "current",
    "first",
    "last",
    "next",
    "back",
    "into",
    "after",
    "before",
    "need",
    "take",
    "give",
    "instead",
    "way",
    "much",
    "well",
    "still",
    "even",
    "both",
    "while",
    "through",
    "between",
    "should",
    "actually",
    "already",
    "also",
    "something",
    "everything",
    "nothing",
    "anything",
    "looks",
    "seems",
}

# ---------------------------------------------------------------------------
# Synonyms
# ---------------------------------------------------------------------------

DEFAULT_SYNONYMS = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "rb": "ruby",
    "fn": "function",
    "func": "function",
    "cls": "class",
    "pkg": "package",
    "lib": "library",
    "cfg": "config",
    "conf": "config",
    "env": "environment",
    "auth": "authentication",
    "db": "database",
    "api": "interface",
    "err": "error",
    "msg": "message",
    "req": "request",
    "res": "response",
}


def merge_synonyms(user_synonyms: dict) -> dict:
    """Merge user-provided synonyms with defaults. User entries override defaults."""
    merged = dict(DEFAULT_SYNONYMS)
    merged.update(user_synonyms)
    return merged


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_\-]{2,}")

# camelCase / PascalCase splitter: "billingService" → ["billing", "Service"]
_CAMEL_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\b)|[A-Z]+|\d+")


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


def tokenize(text: str, filter_stops: bool = True, dedupe: bool = True) -> list:
    """Unified tokenizer for index-time and query-time use.

    Splits on whitespace, underscores, hyphens, then splits camelCase.
    Filters stopwords and short tokens (<3 chars). Deduplicates by default
    (for query processing); set dedupe=False when computing TF for BM25.
    """
    text = text.strip()
    # Split on whitespace, underscores, hyphens first (preserve case for camelCase)
    raw_parts = re.split(r"[\s_\-/]+", text)
    tokens = []
    seen = set()
    for part in raw_parts:
        if not part:
            continue
        # Try camelCase split on each part (before lowercasing)
        sub_tokens = _CAMEL_RE.findall(part)
        if not sub_tokens:
            sub_tokens = [part]
        for t in sub_tokens:
            t = t.lower()
            if len(t) < 3:
                continue
            if filter_stops and t in STOP_WORDS:
                continue
            if dedupe:
                if t not in seen:
                    seen.add(t)
                    tokens.append(t)
            else:
                tokens.append(t)
    return tokens


# ---------------------------------------------------------------------------
# Keyword extraction (uses synonyms)
# ---------------------------------------------------------------------------


def extract_keywords(
    text: str, extra: str = "", max_kw: int = 8, synonyms: dict | None = None
) -> list:
    """Extract top keywords from text with synonym expansion."""
    if synonyms is None:
        synonyms = DEFAULT_SYNONYMS
    tokens = tokenize(f"{text} {extra}", filter_stops=True)
    # Expand synonyms into the token list
    expanded = []
    for t in tokens:
        expanded.append(t)
        if t in synonyms:
            expanded.append(synonyms[t])
    counts = defaultdict(int)
    for t in expanded:
        counts[t] += 1
    top = sorted(counts, key=lambda k: -counts[k])[:max_kw]
    return top
