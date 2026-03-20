"""Tests for workspace_map.index (build, delta detection, incremental update, categories)."""

import os

from workspace_map.config import RepoConfig
from workspace_map.index import (
    INDEX_VERSION,
    build_state,
    compute_corpus_stats,
    extract_frontmatter,
    file_state,
    index_code_files,
    index_memory,
    index_plans,
    index_rules,
    is_changed,
    load_index,
    save_index,
    strip_internal_fields,
)

# ---------------------------------------------------------------------------
# extract_frontmatter
# ---------------------------------------------------------------------------


class TestExtractFrontmatter:
    def test_parses_description_field(self):
        content = "---\ndescription: My skill\nauthor: test\n---\nrest of content"
        fm = extract_frontmatter(content)
        assert fm["description"] == "My skill"

    def test_no_frontmatter_returns_empty_dict(self):
        fm = extract_frontmatter("# Just a heading\nsome text")
        assert fm == {}

    def test_unclosed_frontmatter_returns_empty_dict(self):
        fm = extract_frontmatter("---\ndescription: oops\n")
        assert fm == {}

    def test_strips_quotes_from_values(self):
        fm = extract_frontmatter('---\ndescription: "quoted value"\n---\n')
        assert fm["description"] == "quoted value"

    def test_multiple_fields_parsed(self):
        content = "---\ndescription: My thing\nversion: 1\nauthor: me\n---\n"
        fm = extract_frontmatter(content)
        assert fm["description"] == "My thing"
        assert fm["version"] == "1"


# ---------------------------------------------------------------------------
# file_state / is_changed
# ---------------------------------------------------------------------------


class TestFileState:
    def test_returns_mtime_and_size(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")
        state = file_state(str(f))
        assert "mtime" in state
        assert "size" in state
        assert state["size"] == 5

    def test_missing_file_returns_zeros(self):
        state = file_state("/nonexistent/path/file.txt")
        assert state == {"mtime": 0, "size": 0}


class TestIsChanged:
    def test_new_file_is_changed(self, tmp_path):
        f = tmp_path / "new.txt"
        f.write_text("content", encoding="utf-8")
        # Not in cache → is_changed returns True
        assert is_changed("~/new.txt", {}, str(f)) is True

    def test_unchanged_file_not_changed(self, tmp_path):
        f = tmp_path / "same.txt"
        f.write_text("content", encoding="utf-8")
        st = file_state(str(f))
        cache = {"~/same.txt": st}
        assert is_changed("~/same.txt", cache, str(f)) is False

    def test_modified_mtime_is_changed(self, tmp_path):
        f = tmp_path / "changed.txt"
        f.write_text("old content", encoding="utf-8")
        # Cache with wrong mtime
        cache = {"~/changed.txt": {"mtime": 0.0, "size": 11}}
        assert is_changed("~/changed.txt", cache, str(f)) is True

    def test_modified_size_is_changed(self, tmp_path):
        f = tmp_path / "resized.txt"
        f.write_text("hello", encoding="utf-8")
        st = file_state(str(f))
        # Cache with correct mtime but wrong size
        cache = {"~/resized.txt": {"mtime": st["mtime"], "size": 999}}
        assert is_changed("~/resized.txt", cache, str(f)) is True


# ---------------------------------------------------------------------------
# index_code_files
# ---------------------------------------------------------------------------


class TestIndexCodeFiles:
    def test_indexes_python_file(self, tmp_path):
        repo_dir = tmp_path / "myrepo"
        repo_dir.mkdir()
        src = repo_dir / "script.py"
        src.write_text('"""My script."""\nfoo = 1\n', encoding="utf-8")

        repo = RepoConfig(name="myrepo", path=str(repo_dir), lang="py", glob="**/*.py")
        entries = index_code_files(repo, {}, {}, force=True, verbose=False)
        assert len(entries) == 1
        assert entries[0]["category"] == "code"
        assert entries[0]["language"] == "py"

    def test_entry_has_required_fields(self, tmp_path):
        repo_dir = tmp_path / "myrepo"
        repo_dir.mkdir()
        src = repo_dir / "module.py"
        src.write_text('"""Module purpose."""\n', encoding="utf-8")

        repo = RepoConfig(name="myrepo", path=str(repo_dir), lang="py", glob="**/*.py")
        entries = index_code_files(repo, {}, {}, force=True, verbose=False)
        entry = entries[0]
        for field in (
            "path",
            "repo",
            "category",
            "language",
            "purpose",
            "keywords",
            "symbols",
            "mtime",
        ):  # noqa: E501
            assert field in entry

    def test_purpose_extracted_from_docstring(self, tmp_path):
        repo_dir = tmp_path / "myrepo"
        repo_dir.mkdir()
        (repo_dir / "svc.py").write_text('"""Economy service logic."""\n', encoding="utf-8")

        repo = RepoConfig(name="myrepo", path=str(repo_dir), lang="py", glob="**/*.py")
        entries = index_code_files(repo, {}, {}, force=True, verbose=False)
        assert "Economy" in entries[0]["purpose"] or "economy" in entries[0]["purpose"].lower()

    def test_unchanged_file_skipped_with_state_cache(self, tmp_path):
        repo_dir = tmp_path / "myrepo"
        repo_dir.mkdir()
        src = repo_dir / "old.py"
        src.write_text('"""Old module."""\n', encoding="utf-8")

        repo = RepoConfig(name="myrepo", path=str(repo_dir), lang="py", glob="**/*.py")
        # First pass — index
        entries1 = index_code_files(repo, {}, {}, force=True, verbose=False)
        state = build_state(entries1)

        # Strip _real so we have a clean normalized state cache
        # (entries1[0]["path"] is the normalized key used in state cache)
        # Second pass with state cache — file hasn't changed, should return empty
        entries2 = index_code_files(repo, state, {}, force=False, verbose=False)
        assert len(entries2) == 0

    def test_nonexistent_repo_path_returns_empty(self):
        repo = RepoConfig(name="ghost", path="/nonexistent/path", lang="py", glob="**/*.py")
        entries = index_code_files(repo, {}, {}, force=True, verbose=False)
        assert entries == []

    def test_dart_file_indexed_with_symbols(self, tmp_path):
        repo_dir = tmp_path / "dartrepo"
        repo_dir.mkdir()
        (repo_dir / "service.dart").write_text(
            "class EconomyService {\n  void getBalance() {}\n}\n",
            encoding="utf-8",
        )
        repo = RepoConfig(name="dartrepo", path=str(repo_dir), lang="dart", glob="**/*.dart")
        entries = index_code_files(repo, {}, {}, force=True, verbose=False)
        assert len(entries) == 1
        syms = entries[0]["symbols"]
        assert any(s["name"] == "EconomyService" for s in syms)

    def test_category_assigned_as_code(self, tmp_path):
        repo_dir = tmp_path / "r"
        repo_dir.mkdir()
        (repo_dir / "x.py").write_text("x = 1\n", encoding="utf-8")
        repo = RepoConfig(name="r", path=str(repo_dir), lang="py", glob="**/*.py")
        entries = index_code_files(repo, {}, {}, force=True, verbose=False)
        assert entries[0]["category"] == "code"


# ---------------------------------------------------------------------------
# index_memory
# ---------------------------------------------------------------------------


class TestIndexMemory:
    def test_indexes_md_file_in_memory_dir(self, tmp_path):
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        (mem_dir / "MEMORY.md").write_text("# Project Memory\nsome content", encoding="utf-8")
        entries = index_memory(str(mem_dir), {}, {}, force=True, verbose=False)
        assert len(entries) == 1

    def test_non_md_files_skipped(self, tmp_path):
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        (mem_dir / "notes.txt").write_text("plain text", encoding="utf-8")
        entries = index_memory(str(mem_dir), {}, {}, force=True, verbose=False)
        assert len(entries) == 0

    def test_memory_type_inferred_from_filename(self, tmp_path):
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        for fname, expected_type in [
            ("feedback_costs.md", "feedback"),
            ("project_clawed.md", "project"),
            ("reference_quota.md", "reference"),
            ("MEMORY.md", "main"),
            ("misc_notes.md", "misc"),
        ]:
            (mem_dir / fname).write_text(f"# {fname}\n", encoding="utf-8")

        entries = index_memory(str(mem_dir), {}, {}, force=True, verbose=False)
        type_map = {os.path.basename(e["path"]): e["memory_type"] for e in entries}
        assert type_map.get("feedback_costs.md") == "feedback"
        assert type_map.get("project_clawed.md") == "project"
        assert type_map.get("reference_quota.md") == "reference"
        assert type_map.get("MEMORY.md") == "main"
        assert type_map.get("misc_notes.md") == "misc"

    def test_frontmatter_description_used_as_purpose(self, tmp_path):
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        (mem_dir / "MEMORY.md").write_text(
            "---\ndescription: Main memory file\n---\n# ignored heading\n",
            encoding="utf-8",
        )
        entries = index_memory(str(mem_dir), {}, {}, force=True, verbose=False)
        assert entries[0]["purpose"] == "Main memory file"

    def test_category_is_memory(self, tmp_path):
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        (mem_dir / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
        entries = index_memory(str(mem_dir), {}, {}, force=True, verbose=False)
        assert entries[0]["category"] == "memory"


# ---------------------------------------------------------------------------
# index_plans
# ---------------------------------------------------------------------------


class TestIndexPlans:
    def test_indexes_md_file(self, tmp_path):
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()
        (plans_dir / "my_plan.md").write_text("# Launch Plan\ndetails...", encoding="utf-8")
        entries = index_plans(str(plans_dir), {}, {}, force=True, verbose=False)
        assert len(entries) == 1

    def test_purpose_from_h1_heading(self, tmp_path):
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()
        (plans_dir / "plan.md").write_text("# BM25 Tuning Plan\nsteps...", encoding="utf-8")
        entries = index_plans(str(plans_dir), {}, {}, force=True, verbose=False)
        assert entries[0]["purpose"] == "BM25 Tuning Plan"

    def test_non_md_skipped(self, tmp_path):
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()
        (plans_dir / "plan.txt").write_text("# Plan\n", encoding="utf-8")
        entries = index_plans(str(plans_dir), {}, {}, force=True, verbose=False)
        assert len(entries) == 0

    def test_category_is_plan(self, tmp_path):
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()
        (plans_dir / "p.md").write_text("# A Plan\n", encoding="utf-8")
        entries = index_plans(str(plans_dir), {}, {}, force=True, verbose=False)
        assert entries[0]["category"] == "plan"


# ---------------------------------------------------------------------------
# index_rules
# ---------------------------------------------------------------------------


class TestIndexRules:
    def test_indexes_rule_md_file(self, tmp_path):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "quality.md").write_text("# Flutter Quality Rules\ncontent", encoding="utf-8")
        entries = index_rules(str(rules_dir), {}, {}, force=True, verbose=False)
        assert len(entries) == 1
        assert entries[0]["category"] == "rule"

    def test_non_md_skipped(self, tmp_path):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "rule.json").write_text("{}", encoding="utf-8")
        entries = index_rules(str(rules_dir), {}, {}, force=True, verbose=False)
        assert len(entries) == 0


# ---------------------------------------------------------------------------
# load_index / save_index
# ---------------------------------------------------------------------------


class TestLoadSaveIndex:
    def test_load_nonexistent_returns_empty_structure(self, tmp_path):
        index = load_index(str(tmp_path / "nonexistent.json"))
        assert index["entries"] == []
        assert index["_version"] == INDEX_VERSION

    def test_save_and_load_roundtrip(self, tmp_path):
        index_path = str(tmp_path / "index.json")
        data = {
            "_version": INDEX_VERSION,
            "_generated": "2026-01-01",
            "_state": {},
            "entries": [{"path": "~/test.py", "purpose": "test", "keywords": []}],
            "file_tree": {},
        }
        save_index(data, index_path)
        loaded = load_index(index_path)
        assert loaded["entries"][0]["path"] == "~/test.py"

    def test_corrupt_json_returns_empty_structure(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{{not valid json}}", encoding="utf-8")
        index = load_index(str(bad))
        assert index["entries"] == []


# ---------------------------------------------------------------------------
# strip_internal_fields
# ---------------------------------------------------------------------------


class TestStripInternalFields:
    def test_strips_underscore_prefixed_keys(self):
        entries = [{"path": "~/x.py", "_real": "/real/x.py", "purpose": "test"}]
        cleaned = strip_internal_fields(entries)
        assert "_real" not in cleaned[0]
        assert "path" in cleaned[0]
        assert "purpose" in cleaned[0]

    def test_empty_list_returns_empty(self):
        assert strip_internal_fields([]) == []


# ---------------------------------------------------------------------------
# compute_corpus_stats
# ---------------------------------------------------------------------------


class TestComputeCorpusStats:
    def test_N_equals_number_of_entries(self):
        entries = [
            {
                "path": "~/a.py",
                "purpose": "alpha service",
                "keywords": ["alpha"],
                "symbols": [],
                "aliases": [],
            },
            {
                "path": "~/b.py",
                "purpose": "beta service",
                "keywords": ["beta"],
                "symbols": [],
                "aliases": [],
            },
        ]
        stats = compute_corpus_stats(entries)
        assert stats["N"] == 2

    def test_df_tracks_term_document_frequency(self):
        entries = [
            {
                "path": "~/a.py",
                "purpose": "economy balance",
                "keywords": ["economy"],
                "symbols": [],
                "aliases": [],
            },
            {
                "path": "~/b.py",
                "purpose": "economy roast",
                "keywords": ["roast"],
                "symbols": [],
                "aliases": [],
            },
        ]
        stats = compute_corpus_stats(entries)
        # "economy" appears in both documents
        assert stats["df"].get("economy", 0) == 2
        # "roast" appears in only one
        assert stats["df"].get("roast", 0) == 1

    def test_avgdl_computed_per_field(self):
        entries = [
            {
                "path": "~/a.py",
                "purpose": "alpha service",
                "keywords": [],
                "symbols": [],
                "aliases": [],
            },
        ]
        stats = compute_corpus_stats(entries)
        assert "purpose" in stats["avgdl"]
        assert "filename" in stats["avgdl"]

    def test_empty_entries_returns_zero_N(self):
        stats = compute_corpus_stats([])
        assert stats["N"] == 0
        assert stats["df"] == {}


# ---------------------------------------------------------------------------
# build_state
# ---------------------------------------------------------------------------


class TestBuildState:
    def test_state_built_from_real_files(self, tmp_path):
        f = tmp_path / "script.py"
        f.write_text("x = 1\n", encoding="utf-8")
        norm = f"~/{f.name}" if False else str(f).replace("\\", "/")
        entries = [{"path": norm, "_real": str(f)}]
        state = build_state(entries)
        assert len(state) == 1
        key = list(state.keys())[0]
        assert "mtime" in state[key]
        assert "size" in state[key]

    def test_missing_real_file_skipped(self):
        entries = [{"path": "~/ghost.py", "_real": "/nonexistent/ghost.py"}]
        state = build_state(entries)
        assert len(state) == 0

    def test_entries_without_real_skipped(self):
        entries = [{"path": "~/no_real.py"}]
        state = build_state(entries)
        assert len(state) == 0
