"""Python symbol and purpose extractors."""

import os
import re

from workspace_map.extractors import register


def extract_symbols_python(content: str) -> list:
    """Extract classes, methods, functions, and UPPER_CASE constants from Python.

    Rules:
    - class Foo: / class Foo(Base): → kind "class"
    - Top-level def / async def → kind "function" (private _ prefix kept)
    - Indented def / async def inside a class → kind "method", parent set;
      private methods (starting with _) are skipped
    - Decorated defs/classes: decorator lines (@...) are skipped; the
      def/class on the following non-blank line is attributed normally
    - Module-level UPPER_CASE = ... → kind "const"
    """
    symbols = []
    current_class = None
    class_indent = -1

    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        # Measure indent
        indent = len(line) - len(line.lstrip())

        # Decorator — skip line; next def/class is picked up as usual
        if stripped.startswith("@"):
            continue

        # Class definition (top-level or nested — track only one level deep)
        m = re.match(r"^class\s+(\w+)", stripped)
        if m:
            symbols.append({"kind": "class", "name": m.group(1)})
            current_class = m.group(1)
            class_indent = indent
            continue

        # If indent dropped to class level or above, leave class scope
        if current_class and indent <= class_indent:
            current_class = None
            class_indent = -1

        # def / async def
        m = re.match(r"^(?:async\s+)?def\s+(\w+)", stripped)
        if m:
            name = m.group(1)
            if indent == 0:
                # Top-level function — always include (even private _name)
                symbols.append({"kind": "function", "name": name})
            elif current_class and indent > class_indent:
                # Class method — skip private (underscore prefix)
                if not name.startswith("_"):
                    symbols.append({"kind": "method", "name": name, "parent": current_class})
            continue

        # Module-level constant (UPPER_CASE = ...) — top-level only
        if indent == 0:
            m = re.match(r"^([A-Z][A-Z0-9_]{2,})\s*=", line)
            if m:
                symbols.append({"kind": "const", "name": m.group(1)})

    return symbols


def purpose_python(path: str, content: str) -> str:
    doc_re = re.compile(r'"""(.*?)"""', re.DOTALL)
    m = doc_re.search(content)
    if m:
        first_line = m.group(1).strip().splitlines()[0].strip()
        return first_line[:150]
    # Fallback: first # comment
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#") and not line.startswith("#!"):
            return line.lstrip("#").strip()[:150]
    return os.path.splitext(os.path.basename(path))[0]


# Self-register
register("py", extract_symbols_python, purpose_python)
