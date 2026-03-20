"""Tests for workspace_map.extractors (all language extractors)."""

from workspace_map.extractors import EXTRACTORS, extract_purpose, extract_symbols
from workspace_map.extractors.dart import extract_symbols_dart, purpose_dart
from workspace_map.extractors.javascript import extract_symbols_js, purpose_js
from workspace_map.extractors.markdown import purpose_markdown
from workspace_map.extractors.python import extract_symbols_python, purpose_python
from workspace_map.extractors.shell import extract_symbols_shell, purpose_shell

# ---------------------------------------------------------------------------
# Helper: find a symbol by kind/name
# ---------------------------------------------------------------------------


def find_symbol(symbols, kind, name):
    return next((s for s in symbols if s["kind"] == kind and s["name"] == name), None)


# ---------------------------------------------------------------------------
# Dart extractor
# ---------------------------------------------------------------------------


class TestDartExtractor:
    def test_class_extracted(self, dart_source):
        syms = extract_symbols_dart(dart_source)
        assert find_symbol(syms, "class", "EconomyService") is not None

    def test_enum_extracted(self, dart_source):
        syms = extract_symbols_dart(dart_source)
        assert find_symbol(syms, "enum", "RoastPersona") is not None

    def test_mixin_extracted(self, dart_source):
        syms = extract_symbols_dart(dart_source)
        assert find_symbol(syms, "mixin", "TimestampMixin") is not None

    def test_public_method_extracted(self, dart_source):
        syms = extract_symbols_dart(dart_source)
        sym = find_symbol(syms, "method", "getBalance")
        assert sym is not None
        assert sym.get("parent") == "EconomyService"

    def test_async_method_extracted(self, dart_source):
        syms = extract_symbols_dart(dart_source)
        assert find_symbol(syms, "method", "deductKibble") is not None

    def test_static_const_extracted(self, dart_source):
        syms = extract_symbols_dart(dart_source)
        assert find_symbol(syms, "const", "kDailyLimit") is not None

    def test_top_level_const_extracted(self, dart_source):
        syms = extract_symbols_dart(dart_source)
        assert find_symbol(syms, "const", "kAppVersion") is not None

    def test_private_method_not_extracted(self):
        code = "class Foo {\n  void _privateMethod() {}\n}"
        syms = extract_symbols_dart(code)
        assert find_symbol(syms, "method", "_privateMethod") is None

    def test_purpose_uses_doc_comment(self, dart_source):
        purpose = purpose_dart("service.dart", dart_source)
        assert "EconomyService" in purpose
        assert "Kibble" in purpose or "economy" in purpose.lower()

    def test_purpose_fallback_to_class_name(self):
        code = "class MyWidget {}"
        purpose = purpose_dart("my_widget.dart", code)
        assert "MyWidget" in purpose

    def test_purpose_fallback_to_filename_when_no_class(self):
        purpose = purpose_dart("my_widget.dart", "// no class here")
        assert purpose  # returns something (filename or comment text)

    def test_dart_registered_in_extractors(self):
        assert "dart" in EXTRACTORS


# ---------------------------------------------------------------------------
# Python extractor
# ---------------------------------------------------------------------------


class TestPythonExtractor:
    def test_class_extracted(self, python_source):
        syms = extract_symbols_python(python_source)
        assert find_symbol(syms, "class", "RoastService") is not None

    def test_second_class_extracted(self, python_source):
        syms = extract_symbols_python(python_source)
        assert find_symbol(syms, "class", "CacheService") is not None

    def test_public_method_extracted(self, python_source):
        syms = extract_symbols_python(python_source)
        sym = find_symbol(syms, "method", "generate_roast")
        assert sym is not None
        assert sym.get("parent") == "RoastService"

    def test_private_method_not_extracted(self, python_source):
        syms = extract_symbols_python(python_source)
        assert find_symbol(syms, "method", "_build_prompt") is None

    def test_top_level_function_extracted(self, python_source):
        syms = extract_symbols_python(python_source)
        assert find_symbol(syms, "function", "build_index") is not None

    def test_second_top_level_function_extracted(self, python_source):
        syms = extract_symbols_python(python_source)
        assert find_symbol(syms, "function", "normalize_path") is not None

    def test_upper_case_constant_extracted(self, python_source):
        syms = extract_symbols_python(python_source)
        assert find_symbol(syms, "const", "MAX_RETRIES") is not None

    def test_lowercase_module_var_not_extracted_as_const(self):
        code = "my_var = 42\n"
        syms = extract_symbols_python(code)
        assert find_symbol(syms, "const", "my_var") is None

    def test_purpose_from_module_docstring(self, python_source):
        purpose = purpose_python("roast_service.py", python_source)
        assert "Roast service" in purpose or "roast" in purpose.lower()

    def test_purpose_fallback_to_hash_comment(self):
        code = "# My utility script\nfoo = 1"
        purpose = purpose_python("script.py", code)
        assert purpose == "My utility script"

    def test_purpose_fallback_to_filename(self):
        purpose = purpose_python("economy_service.py", "foo = 1")
        assert "economy_service" in purpose

    def test_py_registered_in_extractors(self):
        assert "py" in EXTRACTORS


# ---------------------------------------------------------------------------
# JavaScript extractor
# ---------------------------------------------------------------------------


class TestJavaScriptExtractor:
    def test_exported_class_extracted(self, js_source):
        syms = extract_symbols_js(js_source)
        assert find_symbol(syms, "class", "AnalyticsService") is not None

    def test_exported_function_extracted(self, js_source):
        syms = extract_symbols_js(js_source)
        assert find_symbol(syms, "function", "trackEvent") is not None

    def test_arrow_function_const_extracted_as_function(self, js_source):
        syms = extract_symbols_js(js_source)
        assert find_symbol(syms, "function", "formatPayload") is not None

    def test_plain_const_extracted(self, js_source):
        syms = extract_symbols_js(js_source)
        assert find_symbol(syms, "const", "BASE_URL") is not None

    def test_exported_const_extracted(self, js_source):
        syms = extract_symbols_js(js_source)
        assert find_symbol(syms, "const", "MAX_BATCH_SIZE") is not None

    def test_module_exports_member_extracted(self):
        # The extractor matches "word: function" pattern on each line
        code = "module.exports = {\n  myHandler: function() {}\n};\n"
        syms = extract_symbols_js(code)
        assert find_symbol(syms, "function", "myHandler") is not None

    def test_purpose_uses_jsdoc_comment(self, js_source):
        purpose = purpose_js("analytics.js", js_source)
        assert "Analytics" in purpose or "analytics" in purpose.lower()

    def test_purpose_fallback_to_class_name(self):
        code = "class Foo {}"
        purpose = purpose_js("foo.js", code)
        assert "Foo" in purpose

    def test_purpose_fallback_to_basename(self):
        purpose = purpose_js("my_module.js", "const x = 1;")
        assert "my_module" in purpose

    def test_js_registered_in_extractors(self):
        assert "js" in EXTRACTORS


# ---------------------------------------------------------------------------
# Shell extractor
# ---------------------------------------------------------------------------


class TestShellExtractor:
    def test_function_with_parens_extracted(self, shell_source):
        syms = extract_symbols_shell(shell_source)
        assert find_symbol(syms, "function", "deploy_functions") is not None

    def test_second_function_extracted(self, shell_source):
        syms = extract_symbols_shell(shell_source)
        assert find_symbol(syms, "function", "run_tests") is not None

    def test_cleanup_function_extracted(self, shell_source):
        syms = extract_symbols_shell(shell_source)
        assert find_symbol(syms, "function", "cleanup") is not None

    def test_exported_env_var_extracted(self, shell_source):
        syms = extract_symbols_shell(shell_source)
        assert find_symbol(syms, "const", "FIREBASE_PROJECT") is not None

    def test_second_env_var_extracted(self, shell_source):
        syms = extract_symbols_shell(shell_source)
        assert find_symbol(syms, "const", "DEPLOY_ENV") is not None

    def test_lowercase_var_not_extracted(self):
        code = "my_var=foo\n"
        syms = extract_symbols_shell(code)
        assert find_symbol(syms, "const", "my_var") is None

    def test_purpose_from_first_comment(self, shell_source):
        purpose = purpose_shell("deploy.sh", shell_source)
        assert "Deploy" in purpose or "deploy" in purpose.lower()

    def test_purpose_skips_shebang(self, shell_source):
        purpose = purpose_shell("deploy.sh", shell_source)
        assert "!" not in purpose  # shebang line not returned

    def test_purpose_fallback_to_filename(self):
        purpose = purpose_shell("my_script.sh", "#!/bin/bash\n")
        assert "my_script" in purpose

    def test_sh_registered_in_extractors(self):
        assert "sh" in EXTRACTORS


# ---------------------------------------------------------------------------
# Markdown extractor
# ---------------------------------------------------------------------------


class TestMarkdownExtractor:
    def test_purpose_from_h1_header(self, markdown_source):
        purpose = purpose_markdown("arch.md", markdown_source)
        assert purpose == "Roast Engine Architecture"

    def test_purpose_strips_hash_prefix(self, markdown_source):
        purpose = purpose_markdown("arch.md", markdown_source)
        assert not purpose.startswith("#")

    def test_purpose_h2_header_when_no_h1(self):
        content = "## Section Title\nsome content"
        purpose = purpose_markdown("doc.md", content)
        assert purpose == "Section Title"

    def test_purpose_fallback_to_filename(self):
        purpose = purpose_markdown("my_doc.md", "no headings here")
        assert "my_doc" in purpose

    def test_empty_file_returns_filename(self):
        purpose = purpose_markdown("readme.md", "")
        assert "readme" in purpose

    def test_md_returns_empty_symbols(self, markdown_source):
        syms = extract_symbols(markdown_source, "md")
        assert syms == []

    def test_md_registered_in_extractors(self):
        assert "md" in EXTRACTORS


# ---------------------------------------------------------------------------
# Registry dispatch
# ---------------------------------------------------------------------------


class TestExtractorRegistry:
    def test_dart_dispatch_returns_symbols(self, dart_source):
        syms = extract_symbols(dart_source, "dart")
        assert len(syms) > 0

    def test_py_dispatch_returns_symbols(self, python_source):
        syms = extract_symbols(python_source, "py")
        assert len(syms) > 0

    def test_js_dispatch_returns_symbols(self, js_source):
        syms = extract_symbols(js_source, "js")
        assert len(syms) > 0

    def test_sh_dispatch_returns_symbols(self, shell_source):
        syms = extract_symbols(shell_source, "sh")
        assert len(syms) > 0

    def test_unknown_language_returns_empty(self, dart_source):
        syms = extract_symbols(dart_source, "cobol")
        assert syms == []

    def test_dart_purpose_dispatch(self, dart_source):
        purpose = extract_purpose("service.dart", dart_source, "dart")
        assert isinstance(purpose, str)
        assert len(purpose) > 0

    def test_unknown_language_purpose_returns_basename(self):
        purpose = extract_purpose("my_file.xyz", "some content", "cobol")
        assert purpose == "my_file"
