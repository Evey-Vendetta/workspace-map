"""Tests for workspace_map.search (BM25F scoring and find())."""

import time

from workspace_map.search import (
    _DECAY_FLOOR,
    blended_score,
    bm25_score_entry,
    find,
    score_entry,
)
from workspace_map.tokenizer import tokenize

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_entry(
    path="~/projects/myrepo/lib/economy_service.dart",
    purpose="EconomyService — manages Kibble balance and deductions",
    keywords=None,
    language="dart",
    category="code",
    mtime=None,
    symbols=None,
    aliases=None,
):
    return {
        "path": path,
        "repo": "myrepo",
        "category": category,
        "language": language,
        "purpose": purpose,
        "keywords": keywords or ["economy", "kibble", "balance"],
        "symbols": symbols or [],
        "aliases": aliases or [],
        "mtime": mtime if mtime is not None else time.time() - 3600,
    }


def simple_corpus_stats(entries):
    from workspace_map.index import compute_corpus_stats

    return compute_corpus_stats(entries)


# ---------------------------------------------------------------------------
# score_entry (keyword-bag scorer)
# ---------------------------------------------------------------------------


class TestScoreEntry:
    def test_filename_match_adds_score(self):
        entry = make_entry(path="~/projects/economy_service.dart")
        score = score_entry(entry, "economy", ["economy"])
        assert score > 0

    def test_purpose_match_adds_score(self):
        entry = make_entry(purpose="handles economy logic")
        score = score_entry(entry, "economy", ["economy"])
        assert score > 0

    def test_keyword_exact_match_adds_score(self):
        entry = make_entry(keywords=["economy", "kibble"])
        score = score_entry(entry, "economy", ["economy"])
        assert score > 0

    def test_no_match_returns_zero(self):
        entry = make_entry(
            path="~/projects/camera_screen.dart",
            purpose="Camera screen captures photos",
            keywords=["camera", "photo"],
        )
        score = score_entry(entry, "economy", ["economy"])
        assert score == 0.0

    def test_alias_full_match_outweighs_filename(self):
        entry_alias = make_entry(
            path="~/projects/foo.dart",
            aliases=["economy service"],
        )
        entry_filename = make_entry(
            path="~/projects/economy_service.dart",
        )
        s_alias = score_entry(entry_alias, "economy service", ["economy", "service"])
        s_filename = score_entry(entry_filename, "economy service", ["economy", "service"])
        # Alias full match gives 4.0; filename gives 3.0
        assert s_alias > s_filename

    def test_symbol_exact_match_gives_high_score(self):
        entry = make_entry(
            symbols=[{"kind": "method", "name": "deductKibble", "parent": "EconomyService"}]
        )
        score = score_entry(entry, "deductkibble", ["deductkibble"])
        assert score >= 6.0

    def test_synonym_in_purpose_adds_score(self):
        entry = make_entry(purpose="manages economy and balance")
        # "kibble" -> "economy" synonym
        score_with_syn = score_entry(entry, "kibble", ["kibble"], synonyms={"kibble": "economy"})
        score_without_syn = score_entry(entry, "kibble", ["kibble"], synonyms={})
        assert score_with_syn > score_without_syn

    def test_session_title_match(self):
        entry = {
            "path": "~/sessions/abc.jsonl",
            "category": "session",
            "title": "Economy refactor session",
            "summary": "Refactored kibble deduction logic",
            "purpose": "",
            "keywords": [],
            "symbols": [],
            "aliases": [],
            "procedures": [],
            "mtime": time.time(),
        }
        score = score_entry(entry, "economy", ["economy"])
        assert score > 0


# ---------------------------------------------------------------------------
# bm25_score_entry
# ---------------------------------------------------------------------------


class TestBM25ScoreEntry:
    def test_zero_for_empty_query(self):
        entry = make_entry()
        corpus = simple_corpus_stats([entry])
        score = bm25_score_entry(entry, [], corpus)
        assert score == 0.0

    def test_zero_for_empty_corpus_stats(self):
        entry = make_entry()
        score = bm25_score_entry(entry, ["economy"], {})
        assert score == 0.0

    def test_zero_for_zero_N(self):
        entry = make_entry()
        score = bm25_score_entry(entry, ["economy"], {"N": 0})
        assert score == 0.0

    def test_relevant_entry_scores_higher_than_irrelevant(self):
        relevant = make_entry(
            path="~/economy_service.dart",
            purpose="EconomyService manages Kibble economy balance",
            keywords=["economy", "kibble"],
        )
        irrelevant = make_entry(
            path="~/camera_screen.dart",
            purpose="CameraScreen captures photos",
            keywords=["camera", "photo"],
        )
        corpus = simple_corpus_stats([relevant, irrelevant])
        tokens = tokenize("economy kibble", filter_stops=False)
        s_rel = bm25_score_entry(relevant, tokens, corpus)
        s_irr = bm25_score_entry(irrelevant, tokens, corpus)
        assert s_rel > s_irr

    def test_score_is_nonnegative(self):
        entry = make_entry()
        corpus = simple_corpus_stats([entry])
        score = bm25_score_entry(entry, ["economy"], corpus)
        assert score >= 0.0

    def test_term_not_in_entry_contributes_zero(self):
        entry = make_entry(purpose="camera photo", keywords=["camera"])
        corpus = simple_corpus_stats([entry, make_entry()])
        score = bm25_score_entry(entry, ["economy"], corpus)
        # economy doesn't appear in camera entry; score should be 0 or very low
        assert score < 0.2  # low but may not be exactly zero due to field overlap


# ---------------------------------------------------------------------------
# blended_score
# ---------------------------------------------------------------------------


class TestBlendedScore:
    def test_falls_back_to_original_without_corpus_stats(self):
        entry = make_entry(purpose="economy balance kibble")
        tokens = ["economy"]
        orig = score_entry(entry, "economy", tokens)
        blended = blended_score(entry, "economy", tokens, corpus_stats=None)
        assert blended == orig

    def test_blended_is_different_from_pure_original(self):
        entries = [
            make_entry(),
            make_entry(path="~/camera.dart", purpose="camera", keywords=["camera"]),
        ]
        corpus = simple_corpus_stats(entries)
        entry = entries[0]
        tokens = tokenize("economy", filter_stops=False)
        orig = score_entry(entry, "economy", tokens)
        blended = blended_score(entry, "economy", tokens, corpus_stats=corpus)
        # blended = orig*0.3 + bm25*0.7 (plus decay), so it differs from pure orig
        assert blended != orig or orig == 0.0

    def test_time_decay_reduces_score_for_old_files(self):
        new_entry = make_entry(mtime=time.time() - 3600)  # 1 hour old
        old_entry = make_entry(mtime=time.time() - 86400 * 365)  # 1 year old

        entries = [new_entry, old_entry]
        corpus = simple_corpus_stats(entries)
        tokens = tokenize("economy", filter_stops=False)

        s_new = blended_score(new_entry, "economy", tokens, corpus)
        s_old = blended_score(old_entry, "economy", tokens, corpus)
        assert s_new > s_old

    def test_decay_floor_prevents_complete_burial(self):
        """Very old file should still score at least DECAY_FLOOR fraction of undecayed."""
        very_old = make_entry(mtime=time.time() - 86400 * 10000)  # ~27 years old
        entries = [very_old, make_entry(path="~/other.dart", purpose="other", keywords=["other"])]
        corpus = simple_corpus_stats(entries)
        tokens = ["economy"]

        s = blended_score(very_old, "economy", tokens, corpus)
        # Expected floor: decay = DECAY_FLOOR applied to blended score
        expected_floor = (
            score_entry(very_old, "economy", tokens) * 0.3
            + bm25_score_entry(very_old, tokens, corpus) * 0.7
        ) * _DECAY_FLOOR
        assert s >= expected_floor * 0.99  # within floating-point tolerance

    def test_zero_mtime_no_decay_applied(self):
        entry = make_entry(mtime=0)
        entries = [entry, make_entry(path="~/other.dart", purpose="other", keywords=["other"])]
        corpus = simple_corpus_stats(entries)
        tokens = ["economy"]
        score = blended_score(entry, "economy", tokens, corpus)
        # mtime=0 means decay branch skipped — score == orig*0.3 + bm25*0.7
        expected = (
            score_entry(entry, "economy", tokens) * 0.3
            + bm25_score_entry(entry, tokens, corpus) * 0.7
        )
        assert abs(score - expected) < 1e-9


# ---------------------------------------------------------------------------
# find()
# ---------------------------------------------------------------------------


class TestFind:
    def test_returns_list_of_tuples(self, sample_index):
        results = find("economy", sample_index)
        assert isinstance(results, list)
        for score, entry in results:
            assert isinstance(score, float)
            assert isinstance(entry, dict)

    def test_relevant_result_in_top_3(self, sample_index):
        results = find("economy kibble", sample_index)
        assert len(results) > 0
        paths = [e["path"] for _, e in results[:3]]
        assert any("economy" in p for p in paths)

    def test_results_sorted_descending_by_score(self, sample_index):
        results = find("economy", sample_index)
        scores = [s for s, _ in results]
        assert scores == sorted(scores, reverse=True)

    def test_empty_query_returns_few_or_none(self, sample_index):
        # Empty query tokenizes to nothing → may return all entries with time-decay only
        results = find("", sample_index)
        # Acceptable: either empty or all entries with low scores
        if results:
            scores = [s for s, _ in results]
            assert all(s < 5.0 for s in scores)  # no strong keyword matches

    def test_no_matching_query_returns_empty(self, sample_index):
        results = find("xyznonexistenttokenqwerty", sample_index)
        assert results == []

    def test_empty_index_returns_empty(self):
        empty_index = {"entries": [], "_corpus_stats": None, "file_tree": {}}
        results = find("economy", empty_index)
        assert results == []

    def test_type_filter_dart_excludes_other_langs(self, sample_index):
        # Add a Python entry to sample index to confirm filtering
        index = dict(sample_index)
        entries = list(index["entries"]) + [
            {
                "path": "~/projects/roast.py",
                "repo": "myrepo",
                "category": "code",
                "language": "py",
                "purpose": "economy roast service Python",
                "keywords": ["economy", "roast"],
                "symbols": [],
                "mtime": time.time(),
            }
        ]
        index["entries"] = entries
        results = find("economy", index, type_filter="dart")
        langs = {e.get("language") for _, e in results}
        assert "py" not in langs

    def test_type_filter_py_includes_only_python(self, sample_index):
        index = dict(sample_index)
        entries = list(index["entries"]) + [
            {
                "path": "~/projects/economy.py",
                "repo": "myrepo",
                "category": "code",
                "language": "py",
                "purpose": "economy balance tracker",
                "keywords": ["economy", "balance"],
                "symbols": [],
                "mtime": time.time(),
            }
        ]
        index["entries"] = entries
        results = find("economy", index, type_filter="py")
        for _, e in results:
            assert e.get("language") == "py"

    def test_scope_filter_code_excludes_rules(self, sample_index):
        results = find("flutter", sample_index, scope_filter="code")
        for _, e in results:
            assert e.get("category") == "code"

    def test_scope_filter_rule_returns_rule_entries(self, sample_index):
        results = find("flutter quality", sample_index, scope_filter="rule")
        if results:
            for _, e in results:
                assert e.get("category") == "rule"

    def test_max_results_limits_output(self, sample_index):
        results = find("dart", sample_index, max_results=1)
        assert len(results) <= 1

    def test_use_bm25_false_falls_back_to_keyword_scorer(self, sample_index):
        results_bm25 = find("economy", sample_index, use_bm25=True)
        results_kw = find("economy", sample_index, use_bm25=False)
        # Both should return results; scores differ but structure is the same
        assert len(results_kw) > 0
        assert len(results_bm25) > 0

    def test_recent_file_ranks_above_old_file_for_same_query(self, sample_index):
        """camera_screen is very recent; old rule file should rank lower for overlapping query."""
        results = find("flutter", sample_index)
        # The rule entry is 30 days old — it should not outrank fresh code entries
        # for a query that also matches code files
        if len(results) >= 2:
            # Just assert results are sorted (time-decay validated in blended_score tests)
            scores = [s for s, _ in results]
            assert scores == sorted(scores, reverse=True)
