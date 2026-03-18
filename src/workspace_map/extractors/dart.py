"""Dart symbol and purpose extractors."""

import os
import re

from workspace_map.extractors import register


def extract_symbols_dart(content: str) -> list:
    """Extract classes, enums, mixins, extensions, functions, methods, constants from Dart."""
    symbols = []
    current_class = None
    brace_depth = 0

    for line in content.split("\n"):
        stripped = line.strip()

        # Class, enum, mixin, extension — check BEFORE updating brace depth
        # so single-line definitions (e.g., `enum Foo { a, b }`) don't
        # immediately clear current_class on the same line.
        m = re.match(r"^(?:abstract\s+)?(?:class|enum|mixin|extension)\s+(\w+)", stripped)
        if m:
            kind = "class"
            if "enum " in stripped:
                kind = "enum"
            elif "mixin " in stripped:
                kind = "mixin"
            elif "extension " in stripped:
                kind = "extension"
            symbols.append({"kind": kind, "name": m.group(1)})
            current_class = m.group(1)
            brace_depth += stripped.count("{") - stripped.count("}")
            continue

        # Track brace depth for class scope (non-class lines)
        brace_depth += stripped.count("{") - stripped.count("}")
        if brace_depth <= 0:
            current_class = None
            brace_depth = 0

        # Top-level or class-level const/final
        m = re.match(r"^\s*(?:static\s+)?(?:const|final)\s+\w+\s+(\w+)\s*=", stripped)
        if m:
            sym = {"kind": "const", "name": m.group(1)}
            if current_class:
                sym["parent"] = current_class
            symbols.append(sym)
            continue

        # Methods (inside a class) — public only (no underscore prefix)
        if current_class:
            m = re.match(
                r"^(?:static\s+)?(?:Future<[^>]+>|Stream<[^>]+>|void|int|double|bool|String|List|Map|Set|\w+)"
                r"[\s?]+([a-zA-Z]\w*)\s*[<(]",
                stripped,
            )
            if m and not m.group(1).startswith("_"):
                symbols.append({"kind": "method", "name": m.group(1), "parent": current_class})
                continue

        # Top-level functions (not indented, not a class member)
        if not current_class:
            m = re.match(
                r"^(?:Future<[^>]+>|Stream<[^>]+>|void|int|double|bool|String|List|Map|Set|\w+)"
                r"[\s?]+([a-zA-Z]\w*)\s*[<(]",
                stripped,
            )
            if m and m.group(1) not in (
                "if", "else", "for", "while", "switch", "return",
                "class", "enum", "mixin", "extension", "import", "export", "part",
            ):
                symbols.append({"kind": "function", "name": m.group(1)})
                continue

    return symbols


def purpose_dart(path: str, content: str) -> str:
    # Try to find ///  docstring before class/mixin/enum, then name
    doc_re = re.compile(r"((?:///[^\n]*\n)+)\s*(?:abstract\s+)?(?:class|mixin|enum)\s+(\w+)")
    m = doc_re.search(content)
    if m:
        doc = " ".join(line.strip().lstrip("/").strip() for line in m.group(1).strip().splitlines())
        name = m.group(2)
        return f"{name} — {doc}" if doc else name

    # Fallback: class name + first 2-3 public methods
    cls_re = re.compile(r"(?:abstract\s+)?(?:class|mixin|enum)\s+(\w+)")
    cm = cls_re.search(content)
    name = cm.group(1) if cm else os.path.splitext(os.path.basename(path))[0]

    method_re = re.compile(
        r"(?:Future|Stream|void|String|int|bool|double|List|Map|dynamic)\s+(\w+)\s*\("
    )
    methods = [m2.group(1) for m2 in method_re.finditer(content) if not m2.group(1).startswith("_")][:3]

    import_re = re.compile(r"import ['\"]package:([^/'\".]+)")
    imports = list(dict.fromkeys(import_re.findall(content)))[:3]

    parts = [name]
    if methods:
        parts.append(", ".join(f"{m}()" for m in methods))
    if imports:
        parts.append(f"uses {', '.join(imports)}")
    return " — ".join(parts)


# Self-register
register("dart", extract_symbols_dart, purpose_dart)
