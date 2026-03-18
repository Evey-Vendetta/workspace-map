# Contributing to workspace-map

Thanks for your interest in contributing.

## Prerequisites

- Python 3.10 or later
- git

## Dev Setup

```bash
git clone https://github.com/Evey-Vendetta/workspace-map.git
cd workspace-map

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[ai]"
pip install pytest ruff
```

## Running Tests

```bash
pytest
```

Run a specific test file:

```bash
pytest tests/test_tokenizer.py
```

## Running the Linter

```bash
ruff check src tests
ruff format --check src tests
```

To auto-fix:

```bash
ruff check --fix src tests
ruff format src tests
```

## Code Style

- Ruff defaults with `line-length = 100` (see `pyproject.toml`)
- Type hints are encouraged for all public functions and methods
- No `print()` in library code — use `logging` or return values
- Keep functions focused; split large modules into submodules

## Adding a Language Extractor

Extractors live in `src/workspace_map/extractors/`. Each extractor is a
Python module that handles one language.

1. Create `src/workspace_map/extractors/<lang>.py`
2. Implement two functions:

   ```python
   def extract_symbols(source: str) -> list[str]:
       """Return class/function/method/constant names found in source."""
       ...

   def extract_purpose(source: str, path: str) -> str:
       """Return a short description of what this file does, or empty string."""
       ...
   ```

3. Register the extractor in `src/workspace_map/extractors/__init__.py`:

   ```python
   from .mylang import extract_symbols, extract_purpose
   EXTRACTORS["mylang"] = {"extensions": [".ml", ".mli"], ...}
   ```

4. Add tests in `tests/test_extractor_<lang>.py`
5. Update the feature list in `README.md`

## PR Process

1. Fork the repo and create a branch: `git checkout -b feat/my-feature`
2. Make your changes with tests
3. Ensure `pytest` and `ruff check` pass cleanly
4. Open a pull request against `main`
5. Fill in the pull request template

For significant changes (new features, architecture changes), open an issue
first to discuss the approach before writing code.

## Reporting Issues

Use the issue templates in `.github/ISSUE_TEMPLATE/`. Include your OS,
Python version, workspace-map version (`wmap --version`), and a minimal
reproduction case.
