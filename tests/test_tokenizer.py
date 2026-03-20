"""Tests for workspace_map.tokenizer."""

from workspace_map.tokenizer import (
    DEFAULT_SYNONYMS,
    extract_keywords,
    merge_synonyms,
    tokenize,
)

# ---------------------------------------------------------------------------
# tokenize — camelCase splitting
# ---------------------------------------------------------------------------


class TestCamelCaseSplitting:
    def test_pascal_case_splits_on_uppercase(self):
        result = tokenize("RoastService", filter_stops=False)
        assert "roast" in result
        assert "service" in result

    def test_camel_case_splits_lowercase_start(self):
        result = tokenize("economyService", filter_stops=False)
        assert "economy" in result
        assert "service" in result

    def test_multi_word_pascal_case(self):
        result = tokenize("EconomyServiceFactory", filter_stops=False)
        assert "economy" in result
        assert "service" in result
        assert "factory" in result

    def test_all_caps_abbreviation_treated_as_single_token(self):
        # "IAP" stays as "iap" (or similar — at least it's lowercased)
        result = tokenize("IAPPurchase", filter_stops=False)
        lowered = [t.lower() for t in result]
        assert any("purchase" in t for t in lowered)

    def test_single_word_unchanged(self):
        result = tokenize("roast", filter_stops=False)
        assert result == ["roast"]


# ---------------------------------------------------------------------------
# tokenize — snake_case splitting
# ---------------------------------------------------------------------------


class TestSnakeCaseSplitting:
    def test_snake_case_splits_on_underscore(self):
        result = tokenize("roast_service", filter_stops=False)
        assert "roast" in result
        assert "service" in result

    def test_multi_segment_snake_case(self):
        result = tokenize("economy_service_factory", filter_stops=False)
        assert "economy" in result
        assert "service" in result
        assert "factory" in result

    def test_path_like_string_with_slashes(self):
        result = tokenize("lib/services/roast_service", filter_stops=False)
        assert "lib" in result
        assert "services" in result
        assert "roast" in result
        assert "service" in result


# ---------------------------------------------------------------------------
# tokenize — stop word filtering
# ---------------------------------------------------------------------------


class TestStopWordFiltering:
    def test_stop_words_removed_by_default(self):
        # "the" and "and" are stop words
        result = tokenize("the roast and the cat")
        assert "the" not in result
        assert "and" not in result
        assert "roast" in result
        assert "cat" in result

    def test_stop_words_kept_when_filter_disabled(self):
        result = tokenize("the roast", filter_stops=False)
        assert "the" in result

    def test_short_tokens_filtered(self):
        # Tokens < 3 chars are always removed
        result = tokenize("go do it", filter_stops=False)
        assert "go" not in result
        assert "do" not in result
        assert "it" not in result

    def test_exactly_three_chars_kept(self):
        result = tokenize("cat", filter_stops=False)
        assert "cat" in result

    def test_two_chars_removed(self):
        result = tokenize("at", filter_stops=False)
        assert "at" not in result


# ---------------------------------------------------------------------------
# tokenize — deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    def test_dedupe_on_by_default(self):
        result = tokenize("roast roast roast")
        assert result.count("roast") == 1

    def test_dedupe_off_preserves_duplicates(self):
        result = tokenize("roast roast roast", dedupe=False)
        assert result.count("roast") == 3

    def test_dedupe_across_case_variants(self):
        # "Roast" and "roast" both normalize to "roast"
        result = tokenize("Roast roast")
        assert result.count("roast") == 1


# ---------------------------------------------------------------------------
# tokenize — empty / None handling
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_string_returns_empty_list(self):
        assert tokenize("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert tokenize("   ") == []

    def test_all_stop_words_returns_empty(self):
        assert tokenize("the and or but") == []

    def test_all_short_tokens_returns_empty(self):
        assert tokenize("a b c", filter_stops=False) == []

    def test_hyphenated_words_split(self):
        result = tokenize("flash-lite", filter_stops=False)
        assert "flash" in result
        assert "lite" in result


# ---------------------------------------------------------------------------
# extract_keywords — synonym expansion
# ---------------------------------------------------------------------------


class TestSynonymExpansion:
    def test_default_synonym_expanded(self):
        # "auth" maps to "authentication" in DEFAULT_SYNONYMS
        result = extract_keywords("auth handler", synonyms=DEFAULT_SYNONYMS)
        assert "authentication" in result

    def test_cfg_synonym_expands_to_config(self):
        result = extract_keywords("cfg loader", synonyms=DEFAULT_SYNONYMS)
        assert "config" in result

    def test_custom_synonym_overrides_default(self):
        custom = {"kibble": "credits"}
        result = extract_keywords("kibble", synonyms=custom)
        assert "credits" in result
        # "economy" from default is NOT present because custom didn't include it
        assert "economy" not in result

    def test_no_synonyms_no_expansion(self):
        result = extract_keywords("kibble", synonyms={})
        assert "economy" not in result
        assert "kibble" in result

    def test_extra_arg_included_in_tokens(self):
        result = extract_keywords("roast", extra="service dart")
        assert "roast" in result
        # "dart" is not a stop word — should appear
        assert "dart" in result

    def test_max_kw_limits_results(self):
        long_text = "roast economy balance camera screen service factory widget provider"
        result = extract_keywords(long_text, max_kw=3)
        assert len(result) <= 3

    def test_empty_text_returns_empty(self):
        assert extract_keywords("") == []


# ---------------------------------------------------------------------------
# merge_synonyms
# ---------------------------------------------------------------------------


class TestMergeSynonyms:
    def test_user_entries_override_defaults(self):
        merged = merge_synonyms({"kibble": "coin"})
        assert merged["kibble"] == "coin"

    def test_default_entries_preserved_when_not_overridden(self):
        merged = merge_synonyms({"mynew": "thing"})
        assert "auth" in merged  # default entry
        assert merged["auth"] == "authentication"

    def test_new_user_entries_added(self):
        merged = merge_synonyms({"myterm": "myexpansion"})
        assert merged["myterm"] == "myexpansion"

    def test_empty_user_synonyms_returns_defaults(self):
        merged = merge_synonyms({})
        assert merged == DEFAULT_SYNONYMS
