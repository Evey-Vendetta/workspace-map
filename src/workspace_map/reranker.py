"""Semantic reranker for workspace-map search results.

Uses Haiku via the `claude` CLI to re-score candidates based on semantic
relevance. Requires the `claude` binary to be in PATH.

The `anthropic` SDK is an optional dependency — HAS_ANTHROPIC is True when it
is installed (reserved for future direct-API reranking path).
"""

import json
import re
import subprocess
import sys

try:
    import anthropic  # noqa: F401

    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# ---------------------------------------------------------------------------
# Rerank prompt
# ---------------------------------------------------------------------------

HAIKU_RERANK_PROMPT = """Given this search query and list of workspace entries, re-score each
entry from 0.0 to 10.0 based on semantic relevance. Consider synonyms, domain concepts,
and intent — not just keywords.

Query: {query}

Entries (index: path | purpose | keywords):
{entries_text}

Output a JSON array of objects with keys "index" (int, 0-based) and "score" (float 0-10).
Respond with only the JSON array, no other text."""


# ---------------------------------------------------------------------------
# Reranker
# ---------------------------------------------------------------------------


def rerank_with_haiku(query: str, candidates: list) -> list:
    """Re-rank search results using Haiku for semantic relevance.

    `candidates` is a list of (score, entry) tuples. The top 30 are sent to
    Haiku for re-scoring. Scores are blended: 30% original + 70% Haiku.

    Returns the re-sorted list. Falls back to the original ordering on any
    error (subprocess failure, JSON parse error, etc.).
    """
    if not candidates:
        return candidates

    # Format top 30 candidates
    top = candidates[:30]
    lines = []
    for i, (score, entry) in enumerate(top):
        path = entry.get("path", "")
        purpose = (entry.get("purpose") or entry.get("description") or "")[:80]
        kw = " ".join(entry.get("keywords", [])[:3])
        aliases_str = ", ".join(entry.get("aliases", [])[:5])
        sym_names = ", ".join(s["name"] for s in entry.get("symbols", [])[:10])
        extra = ""
        if aliases_str:
            extra += f" | aliases: {aliases_str}"
        if sym_names:
            extra += f" | symbols: {sym_names}"
        lines.append(f"{i}: {path} | {purpose} | {kw}{extra}")
    entries_text = "\n".join(lines)

    prompt_text = HAIKU_RERANK_PROMPT.format(query=query, entries_text=entries_text)

    try:
        proc = subprocess.run(
            ["claude", "-p", "--model", "haiku"],
            input=prompt_text,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if proc.returncode != 0:
            print(
                f"  Warning: semantic reranking failed: claude exit {proc.returncode}",
                file=sys.stderr,
            )
            return candidates
        raw = proc.stdout.strip()
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw).strip()
        reranked = json.loads(raw)

        # Combine scores: 30% search score (already BM25-blended) + 70% Haiku
        for item in reranked:
            idx = item.get("index", -1)
            haiku_score = item.get("score", 0.0)
            if 0 <= idx < len(top):
                orig_score = top[idx][0]
                top[idx] = (orig_score * 0.3 + haiku_score * 0.7, top[idx][1])

        # Re-sort and return (include remaining candidates beyond top 30)
        top.sort(key=lambda x: -x[0])
        return top + candidates[30:]
    except FileNotFoundError:
        print(
            "  Warning: semantic reranking failed: 'claude' not found in PATH",
            file=sys.stderr,
        )
        return candidates
    except Exception as e:
        print(f"  Warning: semantic reranking failed: {e}", file=sys.stderr)
        return candidates
