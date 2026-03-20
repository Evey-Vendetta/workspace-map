"""BM25F search and scoring for workspace-map."""

import math
import os
import time

from workspace_map.tokenizer import DEFAULT_SYNONYMS, tokenize

# ---------------------------------------------------------------------------
# BM25 constants
# ---------------------------------------------------------------------------

# BM25F global saturation parameter. Standard range 1.2–2.0.
# 1.2 = faster saturation (diminishing returns from repeated terms).
_BM25_K1 = 1.2

# Time-decay lambda: 0.005 → ~50% weight at 140 days, ~37% at 200 days
_DECAY_LAMBDA = 0.005

# Floor: never decay below 10% of undecayed score (prevents old-but-important
# files like CLAUDE.md from being completely buried on a stale index)
_DECAY_FLOOR = 0.1


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_entry(
    entry: dict,
    query_lower: str,
    tokens: list,
    synonyms: dict | None = None,
) -> float:
    """Original keyword-bag scorer. Used as the 30% component in blended_score."""
    if synonyms is None:
        synonyms = DEFAULT_SYNONYMS

    score = 0.0
    path = entry.get("path", "").lower()
    purpose = entry.get("purpose", "").lower()
    keywords = [k.lower() for k in entry.get("keywords", [])]
    filename = os.path.basename(path.rstrip("/")).lower()

    # Full phrase match
    if query_lower in filename:
        score += 3.0
    if query_lower in purpose:
        score += 2.0
    if any(query_lower == k for k in keywords):
        score += 1.0

    # Synonym expansion
    synonym_targets: set[str] = set()
    for t in tokens:
        if t in synonyms:
            synonym_targets.add(synonyms[t])

    for target in synonym_targets:
        if target in purpose:
            score += 1.5
        if any(target == k for k in keywords):
            score += 0.8

    # Token-level matches
    for token in tokens:
        if token in filename:
            score += 1.5
        if token in purpose:
            score += 1.0
        if any(token == k for k in keywords):
            score += 0.5

    # Partial substring matches (lower weight)
    if query_lower in path and query_lower not in filename:
        score += 0.5
    for token in tokens:
        if token in path and token not in filename:
            score += 0.25

    # Session title
    if entry.get("category") == "session":
        title = entry.get("title", "").lower()
        summary = (entry.get("summary") or "").lower()
        if query_lower in title:
            score += 2.5
        if query_lower in summary:
            score += 1.5
        for token in tokens:
            if token in title:
                score += 1.0
            if token in summary:
                score += 0.5

        for proc in entry.get("procedures", []):
            proc_lower = proc.lower()
            if query_lower in proc_lower:
                score += 1.0
            for token in tokens:
                if token in proc_lower:
                    score += 0.4

    # Alias phrase matching (separate pass — not in keyword loop)
    # Intentional: alias partial tokens score 0.3 (not 1.0) to avoid double-counting
    # with the existing token loop that also runs against purpose/keywords.
    aliases = entry.get("aliases", [])
    alias_partial = 0.0
    for alias in aliases:
        alias_low = alias.lower()
        if query_lower in alias_low:
            score += 4.0  # Full phrase match in alias (curated > filename)
            alias_partial = 0.0  # Don't add partials if we got a phrase match
            break
        else:
            for token in tokens:
                if token in alias_low:
                    alias_partial += 0.3
    score += min(alias_partial, 1.2)  # Cap at 4 alias partial hits

    # Symbol name matching (separate pass — not in keyword loop)
    # Exact symbol match is the strongest signal — if someone types a method
    # name, the file defining it should always rank first.
    symbols = entry.get("symbols", [])
    sym_partial = 0.0
    # Tokenize query for camelCase comparison (e.g., "getUserData" -> ["get", "user", "data"])
    query_sym_tokens = tokenize(query_lower)
    for sym in symbols[:50]:  # Cap symbols considered
        sym_name_lower = sym["name"].lower()
        sym_tokens = tokenize(sym["name"])
        # Exact match: query IS the symbol name (case-insensitive)
        if sym_name_lower == query_lower:
            score += 6.0  # Strongest possible signal
            sym_partial = 0.0
            break
        # Containment: query contains symbol or symbol contains query
        if sym_name_lower in query_lower or query_lower in sym_name_lower:
            score += 3.0
            sym_partial = 0.0
            break
        # Token overlap: all query tokens match symbol tokens (camelCase split)
        if len(query_sym_tokens) >= 2 and all(qt in sym_tokens for qt in query_sym_tokens):
            score += 4.0  # All tokens match — very likely the right file
            sym_partial = 0.0
            break
        for token in tokens:
            if token == sym_name_lower or (len(token) > 3 and token in sym_name_lower):
                sym_partial += 0.4
                break
    score += min(sym_partial, 1.6)  # Cap at 4 symbol partial hits

    return score


def bm25_score_entry(entry: dict, query_tokens: list, corpus_stats: dict) -> float:
    """BM25F multi-field scorer (Robertson & Zaragoza 2004).

    Computes BM25 score across multiple fields with per-field boost and
    length normalization. Uses standard BM25F formula:
        score = sum over query terms of: IDF(t) * pseudo_tf / (k1 + pseudo_tf)
    where pseudo_tf = sum over fields of: boost_f * tf_f / (1 + b_f * (dl_f/avgdl_f - 1))

    Field parameters (boost, b):
        filename:  boost=3.0, b=0.3  (short field, high boost)
        purpose:   boost=2.0, b=0.75 (main content field)
        keywords:  boost=1.5, b=0.0  (fixed-length list, no length normalization)
        aliases:   boost=4.0, b=0.3  (curated, highest boost — matches S170 tuning)
        symbols:   boost=1.5, b=0.3  (code identifiers)
        title:     boost=2.5, b=0.5  (session only)
        summary:   boost=1.5, b=0.75 (session only)

    Stopwords are NOT filtered in field tokenization (filter_stops=False).
    BM25's IDF naturally suppresses them — high DF → near-zero IDF.
    """
    if not query_tokens or not corpus_stats or corpus_stats.get("N", 0) == 0:
        return 0.0

    N = corpus_stats["N"]
    df = corpus_stats.get("df", {})
    avgdl = corpus_stats.get("avgdl", {})

    # Field definitions: (field_name, text_source, boost, b)
    path = entry.get("path", "")
    filename = os.path.basename(path.rstrip("/"))

    fields = [
        ("filename", filename, 3.0, 0.3),
        ("purpose", entry.get("purpose", ""), 2.0, 0.75),
        ("keywords", " ".join(entry.get("keywords", [])), 1.5, 0.0),
        ("aliases", " ".join(entry.get("aliases", [])), 4.0, 0.3),
        ("symbols", " ".join(s["name"] for s in entry.get("symbols", [])[:50]), 1.5, 0.3),
    ]

    # Session-specific fields
    if entry.get("category") == "session":
        fields.append(("title", entry.get("title", ""), 2.5, 0.5))
        fields.append(("summary", entry.get("summary", "") or "", 1.5, 0.75))

    # Tokenize each field (dedupe=False to preserve TF counts)
    field_tokens: dict[str, list] = {}
    for field_name, text, *_ in fields:
        field_tokens[field_name] = tokenize(text, filter_stops=False, dedupe=False)

    score = 0.0
    for term in query_tokens:
        # IDF: log((N - df + 0.5) / (df + 0.5) + 1)
        term_df = df.get(term, 0)
        idf = math.log((N - term_df + 0.5) / (term_df + 0.5) + 1.0)

        # BM25F: combine weighted TF across fields into pseudo-TF
        tf_weighted = 0.0
        for field_name, _text, boost, b in fields:
            tokens = field_tokens[field_name]
            dl = len(tokens)
            avg = avgdl.get(field_name, 1.0) or 1.0
            tf = tokens.count(term)
            if tf == 0:
                continue
            # Per-field TF normalization (BM25F length normalization)
            norm_tf = tf / (1.0 + b * (dl / avg - 1.0))
            tf_weighted += boost * norm_tf

        # BM25 saturation with global k1
        if tf_weighted > 0:
            score += idf * (tf_weighted / (_BM25_K1 + tf_weighted))

    return score


def blended_score(
    entry: dict,
    query_lower: str,
    tokens: list,
    corpus_stats: dict | None,
    synonyms: dict | None = None,
) -> float:
    """Compute blended score: 30% original + 70% BM25F, with time-decay.

    Falls back to original scorer only when corpus_stats is absent.
    Time-decay is applied as a multiplicative factor based on entry mtime.
    Decay has a floor of _DECAY_FLOOR to prevent old files from vanishing.
    Note: mtime reflects last-edit, not last-access. On a stale index,
    all files appear older than reality — rebuild to refresh.
    """
    orig = score_entry(entry, query_lower, tokens, synonyms=synonyms)

    if not corpus_stats or corpus_stats.get("N", 0) == 0:
        return orig

    bm25 = bm25_score_entry(entry, tokens, corpus_stats)
    score = orig * 0.3 + bm25 * 0.7

    # Time-decay: exponential decay based on mtime, with floor
    mtime = entry.get("mtime")
    if mtime and mtime > 0:
        age_days = (time.time() - mtime) / 86400.0
        if age_days > 0:
            decay = max(math.exp(-_DECAY_LAMBDA * age_days), _DECAY_FLOOR)
            score *= decay

    return score


# ---------------------------------------------------------------------------
# find() — library-facing search function
# ---------------------------------------------------------------------------


def find(
    query: str,
    index: dict,
    config=None,
    type_filter: str | None = None,
    scope_filter: str | None = None,
    use_bm25: bool = True,
    max_results: int = 15,
    synonyms: dict | None = None,
) -> list[tuple[float, dict]]:
    """Search the index and return ranked (score, entry) tuples.

    Args:
        query: Natural-language search query.
        index: Loaded index dict (from index.load_index()).
        config: Optional Config object; synonyms are taken from it if provided.
        type_filter: Filter by language string (e.g. "dart", "py").
        scope_filter: Filter by category string (e.g. "code", "memory").
        use_bm25: If False, use original keyword-bag scorer only.
        max_results: Maximum number of results to return.
        synonyms: Override synonym table (falls back to config.synonyms then DEFAULT_SYNONYMS).

    Returns:
        List of (score, entry) tuples, sorted descending by score.
    """
    entries = index.get("entries", [])
    if not entries:
        return []

    # Resolve synonyms
    if synonyms is None and config is not None:
        synonyms = config.synonyms or None
    if synonyms is None:
        synonyms = DEFAULT_SYNONYMS

    query_lower = query.lower().strip()
    tokens = tokenize(query_lower, filter_stops=True)

    corpus_stats = index.get("_corpus_stats") if use_bm25 else None

    scored: list[tuple[float, dict]] = []
    for entry in entries:
        # Apply filters
        if type_filter:
            lang = entry.get("language", "")
            if not lang:
                ext = os.path.splitext(entry.get("path", "").rstrip("/"))[1].lstrip(".")
                lang = ext or ""
            if lang.lower() != type_filter.lower():
                continue
        if scope_filter:
            cat = entry.get("category", "")
            if cat.lower() != scope_filter.lower():
                continue

        s = blended_score(entry, query_lower, tokens, corpus_stats, synonyms=synonyms)
        if s > 0:
            scored.append((s, entry))

    # Search file tree (lower weight, skip already-scored paths)
    if not scope_filter:
        seen_paths = {e["path"] for _, e in scored}
        file_tree = index.get("file_tree", {})
        for repo_name, tree_entries in file_tree.items():
            for te in tree_entries:
                if te.get("path", "") in seen_paths:
                    continue
                te_path = te.get("path", "").lower()
                te_fname = os.path.basename(te_path).lower()
                ts = 0.0
                if query_lower in te_fname:
                    ts += 0.6
                for token in tokens:
                    if token in te_fname:
                        ts += 0.3
                if ts > 0:
                    scored.append(
                        (
                            ts,
                            {
                                "path": te["path"],
                                "category": "file_tree",
                                "purpose": "",
                                "repo": repo_name,
                                "size": te.get("size", 0),
                            },
                        )
                    )

    scored.sort(key=lambda x: -x[0])
    return scored[:max_results]
