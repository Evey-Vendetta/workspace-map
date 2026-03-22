"""Shared fixtures for workspace-map tests."""

import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dir(tmp_path):
    """Alias for pytest's tmp_path — a fresh temporary directory per test."""
    return tmp_path


# ---------------------------------------------------------------------------
# Sample config YAML string
# ---------------------------------------------------------------------------

SAMPLE_CONFIG_YAML = """\
repos:
  - name: myrepo
    path: /tmp/myrepo
    lang: py
    glob: "**/*.py"
synonyms:
  credits: billing
  llm: ai
index_path: /tmp/test-index.json
"""


@pytest.fixture
def sample_config_yaml():
    """Return a minimal valid YAML config string."""
    return SAMPLE_CONFIG_YAML


@pytest.fixture
def sample_config_file(tmp_path):
    """Write a minimal YAML config to a temp file and return its path."""
    cfg = tmp_path / "workspace-map.yaml"
    cfg.write_text(SAMPLE_CONFIG_YAML, encoding="utf-8")
    return str(cfg)


# ---------------------------------------------------------------------------
# Sample index
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_index():
    """Return a minimal in-memory index suitable for search tests."""
    now = time.time()
    entries = [
        {
            "path": "~/projects/myapp/lib/services/billing_service.dart",
            "repo": "myapp",
            "category": "code",
            "language": "dart",
            "purpose": "BillingService — manages Credits balance and deductions",
            "keywords": ["billing", "credits", "balance", "deduction"],
            "symbols": [
                {"kind": "class", "name": "BillingService"},
                {"kind": "method", "name": "deductCredits", "parent": "BillingService"},
                {"kind": "method", "name": "getBalance", "parent": "BillingService"},
            ],
            "mtime": now - 3600,  # 1 hour old
        },
        {
            "path": "~/projects/myapp/lib/services/task_service.dart",
            "repo": "myapp",
            "category": "code",
            "language": "dart",
            "purpose": "TaskService — dispatches LLM task requests",
            "keywords": ["task", "ai", "llm", "openai"],
            "symbols": [
                {"kind": "class", "name": "TaskService"},
                {"kind": "method", "name": "runTask", "parent": "TaskService"},
            ],
            "mtime": now - 7200,  # 2 hours old
        },
        {
            "path": "~/projects/myapp/lib/screens/upload_screen.dart",
            "repo": "myapp",
            "category": "code",
            "language": "dart",
            "purpose": "UploadScreen — captures photo and triggers task flow",
            "keywords": ["upload", "screen", "photo", "capture"],
            "symbols": [
                {"kind": "class", "name": "UploadScreen"},
            ],
            "mtime": now - 100,  # very recent
        },
        {
            "path": "~/.claude/rules/quality.md",
            "repo": None,
            "category": "rule",
            "purpose": "Flutter quality rules and best practices",
            "keywords": ["flutter", "quality", "dart", "rules"],
            "mtime": now - 86400 * 30,  # 30 days old (for time-decay tests)
        },
    ]

    # Minimal corpus stats for BM25 tests
    from workspace_map.index import compute_corpus_stats

    corpus_stats = compute_corpus_stats(entries)

    return {
        "_version": 4,
        "_generated": "2026-01-01T00:00:00",
        "_state": {},
        "_corpus_stats": corpus_stats,
        "entries": entries,
        "file_tree": {},
    }


# ---------------------------------------------------------------------------
# Fixture file content helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


@pytest.fixture
def dart_source():
    return read_fixture("sample.dart")


@pytest.fixture
def python_source():
    return read_fixture("sample.py")


@pytest.fixture
def js_source():
    return read_fixture("sample.js")


@pytest.fixture
def shell_source():
    return read_fixture("sample.sh")


@pytest.fixture
def markdown_source():
    return read_fixture("sample.md")
