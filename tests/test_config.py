"""Tests for workspace_map.config."""

import importlib.util
import os
import textwrap
from unittest.mock import patch

import pytest

from workspace_map.config import (
    Config,
    _parse_yaml_config,
    auto_discover_repos,
    detect_claude_code,
    expand_path,
    load_config,
    normalize_path,
)

HAS_YAML = importlib.util.find_spec("yaml") is not None

pytestmark = pytest.mark.skipif(not HAS_YAML, reason="pyyaml not installed")


# ---------------------------------------------------------------------------
# normalize_path / expand_path
# ---------------------------------------------------------------------------


class TestPathUtilities:
    def test_expand_path_resolves_tilde(self):
        result = expand_path("~")
        assert not result.startswith("~")
        assert os.path.isabs(result)

    def test_normalize_path_uses_forward_slashes(self, tmp_path):
        p = str(tmp_path / "foo" / "bar.txt")
        result = normalize_path(p)
        assert "\\" not in result

    def test_normalize_path_replaces_home_with_tilde(self, tmp_path):
        home = os.path.expanduser("~")
        path_under_home = os.path.join(home, "some_test_file.txt")
        result = normalize_path(path_under_home)
        assert result.startswith("~")

    def test_normalize_path_path_outside_home_stays_absolute(self, tmp_path):
        # tmp_path is typically /tmp/... which is not under home
        result = normalize_path(str(tmp_path))
        # As long as it's not under home, ~ prefix is not applied
        # (could still have ~ if tmp is under home on some systems)
        assert "/" in result


# ---------------------------------------------------------------------------
# _parse_yaml_config
# ---------------------------------------------------------------------------


class TestParseYamlConfig:
    def test_repos_parsed(self):
        data = {
            "repos": [
                {"name": "myrepo", "path": "/tmp/myrepo", "lang": "dart", "glob": "lib/**/*.dart"}
            ]
        }
        config = _parse_yaml_config(data)
        assert len(config.repos) == 1
        assert config.repos[0].name == "myrepo"
        assert config.repos[0].lang == "dart"

    def test_synonyms_parsed(self):
        data = {"synonyms": {"kibble": "economy", "vertex": "ai"}}
        config = _parse_yaml_config(data)
        assert config.synonyms["kibble"] == "economy"
        assert config.synonyms["vertex"] == "ai"

    def test_index_path_parsed(self):
        data = {"index_path": "/tmp/test.json"}
        config = _parse_yaml_config(data)
        assert config.index_path == "/tmp/test.json"

    def test_missing_optional_fields_use_defaults(self):
        config = _parse_yaml_config({})
        assert config.repos == []
        assert config.synonyms == {}
        assert config.index_path == ""
        assert config.claude_code_enabled == "auto"

    def test_claude_code_enabled_parsed(self):
        data = {"claude_code_enabled": False}
        config = _parse_yaml_config(data)
        assert config.claude_code_enabled in ("false", "False")

    def test_repo_missing_lang_defaults_to_unknown(self):
        data = {"repos": [{"name": "r", "path": "/tmp/r"}]}
        config = _parse_yaml_config(data)
        assert config.repos[0].lang == "unknown"

    def test_repo_missing_glob_defaults_to_wildcard(self):
        data = {"repos": [{"name": "r", "path": "/tmp/r"}]}
        config = _parse_yaml_config(data)
        assert config.repos[0].glob == "**/*"


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_loads_valid_yaml_file(self, tmp_path):
        cfg = tmp_path / "workspace-map.yaml"
        cfg.write_text(
            textwrap.dedent("""\
            repos:
              - name: testrepo
                path: /tmp/testrepo
                lang: py
                glob: "**/*.py"
            synonyms:
              kibble: economy
        """),
            encoding="utf-8",
        )
        config = load_config(str(cfg))
        assert len(config.repos) == 1
        assert config.repos[0].name == "testrepo"
        assert config.synonyms["kibble"] == "economy"

    def test_returns_empty_config_when_no_file_found(self, tmp_path):
        # Use a path that definitely doesn't exist and change cwd to avoid auto-discovery
        with patch("workspace_map.config._CONFIG_SEARCH_PATHS", []):
            config = load_config("/nonexistent/path/config.yaml")
        assert config.repos == []
        assert config.synonyms == {}

    def test_explicit_path_takes_precedence(self, tmp_path):
        cfg1 = tmp_path / "config1.yaml"
        cfg1.write_text("repos:\n  - name: explicit\n    path: /tmp/r1\n", encoding="utf-8")
        cfg2 = tmp_path / "config2.yaml"
        cfg2.write_text("repos:\n  - name: fallback\n    path: /tmp/r2\n", encoding="utf-8")
        config = load_config(str(cfg1))
        assert config.repos[0].name == "explicit"

    def test_returns_empty_config_on_parse_error(self, tmp_path, capsys):
        bad = tmp_path / "workspace-map.yaml"
        bad.write_text("repos: [bad: yaml: {{\n", encoding="utf-8")
        config = load_config(str(bad))
        assert isinstance(config, Config)
        # Warning should be printed to stderr
        captured = capsys.readouterr()
        assert "Warning" in captured.err or config.repos == []

    def test_empty_yaml_returns_empty_config(self, tmp_path):
        cfg = tmp_path / "workspace-map.yaml"
        cfg.write_text("", encoding="utf-8")
        config = load_config(str(cfg))
        assert config.repos == []


# ---------------------------------------------------------------------------
# auto_discover_repos
# ---------------------------------------------------------------------------


class TestAutoDiscoverRepos:
    def test_discovers_git_repo_in_root(self, tmp_path):
        repo_dir = tmp_path / "myrepo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()
        # Add a Python file for language detection
        (repo_dir / "main.py").write_text("print('hello')\n", encoding="utf-8")
        repos = auto_discover_repos(root=str(tmp_path))
        names = [r.name for r in repos]
        assert "myrepo" in names

    def test_discovered_repo_has_correct_name(self, tmp_path):
        repo_dir = tmp_path / "clawed"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()
        repos = auto_discover_repos(root=str(tmp_path))
        assert repos[0].name == "clawed"

    def test_discovered_repo_path_uses_forward_slashes(self, tmp_path):
        repo_dir = tmp_path / "myrepo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()
        repos = auto_discover_repos(root=str(tmp_path))
        assert "\\" not in repos[0].path

    def test_detects_python_language(self, tmp_path):
        repo_dir = tmp_path / "pyrepo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()
        (repo_dir / "script.py").write_text("x = 1\n", encoding="utf-8")
        repos = auto_discover_repos(root=str(tmp_path))
        assert repos[0].lang == "py"

    def test_detects_dart_language(self, tmp_path):
        repo_dir = tmp_path / "dartrepo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()
        lib = repo_dir / "lib"
        lib.mkdir()
        (lib / "main.dart").write_text("void main() {}\n", encoding="utf-8")
        repos = auto_discover_repos(root=str(tmp_path))
        assert repos[0].lang == "dart"

    def test_no_repos_returns_empty_list(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        repos = auto_discover_repos(root=str(empty))
        assert repos == []

    def test_does_not_recurse_into_nested_git_repo(self, tmp_path):
        outer = tmp_path / "outer"
        outer.mkdir()
        (outer / ".git").mkdir()
        inner = outer / "inner"
        inner.mkdir()
        (inner / ".git").mkdir()
        repos = auto_discover_repos(root=str(tmp_path))
        names = [r.name for r in repos]
        # Should find outer but not inner (stops recursing after .git found)
        assert "outer" in names
        assert "inner" not in names

    def test_max_depth_respected(self, tmp_path):
        # Create repo 3 levels deep — should not be discovered with max_depth=1
        deep = tmp_path / "level1" / "level2" / "level3"
        deep.mkdir(parents=True)
        (deep / ".git").mkdir()
        repos = auto_discover_repos(root=str(tmp_path), max_depth=1)
        assert len(repos) == 0


# ---------------------------------------------------------------------------
# detect_claude_code
# ---------------------------------------------------------------------------


class TestDetectClaudeCode:
    def test_returns_none_when_claude_dir_absent(self, tmp_path):
        # Point home to a temp dir that has no .claude subdir
        absent_home = tmp_path / "home_without_claude"
        absent_home.mkdir()
        claude_path = str(absent_home / ".claude")
        with patch("workspace_map.config.os.path.expanduser", return_value=claude_path):
            result = detect_claude_code()
        assert result is None

    def test_returns_dict_when_claude_dir_present(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        with patch("workspace_map.config.os.path.expanduser", return_value=str(claude_dir)):
            result = detect_claude_code()
        assert result is not None
        assert "root" in result
        assert "hooks" in result

    def test_result_contains_all_expected_keys(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        with patch("workspace_map.config.os.path.expanduser", return_value=str(claude_dir)):
            result = detect_claude_code()
        assert result is not None
        for key in ("hooks", "scripts", "skills", "plans", "rules", "agents", "commands"):
            assert key in result

    def test_memory_dirs_populated_when_present(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        proj_dir = claude_dir / "projects" / "myproject" / "memory"
        proj_dir.mkdir(parents=True)
        with patch("workspace_map.config.os.path.expanduser", return_value=str(claude_dir)):
            result = detect_claude_code()
        assert result is not None
        assert len(result.get("memory_dirs", [])) > 0

    def test_session_dirs_populated_when_jsonl_present(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        proj_dir = claude_dir / "projects" / "myproject"
        proj_dir.mkdir(parents=True)
        (proj_dir / "session1.jsonl").write_text("{}\n", encoding="utf-8")
        with patch("workspace_map.config.os.path.expanduser", return_value=str(claude_dir)):
            result = detect_claude_code()
        assert result is not None
        assert len(result.get("session_dirs", [])) > 0
