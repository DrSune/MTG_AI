"""R0 consumer scan: AST-level enumeration of Selector zone/zones consumers.

Read-only. Emits JSON to stdout.
"""

import ast
import json
import os
import sys

ROOT = "/home/sune/Desktop/MTG_AI"
CORE = os.path.join(ROOT, "MTG_bot", "core")
TOOLSDIR = os.path.join(ROOT, "tools")

FILES = []
for base in (CORE, TOOLSDIR):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__",)]
        for fn in filenames:
            if fn.endswith(".py"):
                FILES.append(os.path.join(dirpath, fn))
FILES.sort()


def is_test(path):
    return os.path.basename(path).startswith("test_")


def rel(p):
    return os.path.relpath(p, ROOT)


def src_of(node, lines):
    try:
        return ast.get_source_segment("".join(lines), node) or ""
    except Exception:
        return ""


class Mod(ast.NodeVisitor):
    def __init__(self, path, lines, tree):
        self.path = path
        self.lines = lines
        self.calls_attrs = {
            (n.func.lineno, n.func.col_offset)
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr in ("zone", "zones")
        }
        self.stack = []  # enclosing names
        self.cons = []  # Selector(...) constructions
        self.attrs = []  # .zone/.zones attribute reads (and writes)
        self.dictkeys = []  # dict literal / subscript use of "zone"/"zones"

    def _name(self, node):
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        elif isinstance(node, ast.Call):
            parts.append(self._name(node.func) + "()")
        elif isinstance(node, ast.Constant):
            parts.append(repr(node.value))
        else:
            parts.append(type(node).__name__)
        return ".".join(reversed(parts))

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_Call(self, node):
        f = node.func
        fname = (
            f.id
            if isinstance(f, ast.Name)
            else (f.attr if isinstance(f, ast.Attribute) else "")
        )
        if fname == "Selector":
            kwn = [kw.arg for kw in node.keywords if kw.arg]
            self.cons.append(
                {
                    "file": rel(self.path),
                    "line": node.lineno,
                    "enclosing": "/".join(self.stack[-3:]) or "<module>",
                    "npos": len(node.args),
                    "keywords": kwn,
                    "has_zone_kw": "zone" in kwn,
                    "has_zones_kw": "zones" in kwn,
                    "snippet": " ".join(src_of(node, self.lines).split())[:300],
                }
            )
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if node.attr in ("zone", "zones"):
            recv = self._name(node.value)
            ctx = type(node.ctx).__name__
            self.attrs.append(
                {
                    "file": rel(self.path),
                    "line": node.lineno,
                    "attr": node.attr,
                    "recv": recv,
                    "ctx": ctx,
                    "called": (node.lineno, node.col_offset) in self.calls_attrs,
                    "enclosing": "/".join(self.stack[-3:]) or "<module>",
                    "snippet": " ".join(src_of(node, self.lines).split())[:240],
                }
            )
        self.generic_visit(node)

    def visit_Subscript(self, node):
        # obj["zone"] style dict access on serialized IR
        if isinstance(node.slice, ast.Constant) and node.slice.value in (
            "zone",
            "zones",
        ):
            self.dictkeys.append(
                {
                    "file": rel(self.path),
                    "line": node.lineno,
                    "attr": node.slice.value,
                    "recv": self._name(node.value),
                    "ctx": type(node.ctx).__name__,
                    "enclosing": "/".join(self.stack[-3:]) or "<module>",
                    "snippet": " ".join(src_of(node, self.lines).split())[:240],
                }
            )
        self.generic_visit(node)

    def visit_keyword(self, node):
        if node.arg in ("zone", "zones"):
            self.dictkeys.append(
                {
                    "file": rel(self.path),
                    "line": node.lineno,
                    "attr": node.arg,
                    "recv": "<kwarg>",
                    "ctx": "kwarg",
                    "enclosing": "/".join(self.stack[-3:]) or "<module>",
                    "snippet": " ".join(src_of(node, self.lines).split())[:240],
                }
            )
        self.generic_visit(node)


out = {"constructions": [], "attrs": [], "dictkeys": [], "parse_errors": []}
for p in FILES:
    try:
        with open(p, "r", encoding="utf-8") as fh:
            text = fh.read()
        lines = text.splitlines(keepends=True)
        tree = ast.parse(text)
    except Exception as exc:  # pragma: no cover
        out["parse_errors"].append({"file": rel(p), "error": str(exc)})
        continue
    m = Mod(p, lines, tree)
    m.visit(tree)
    tag = "test" if is_test(p) else "prod"
    for c in m.cons:
        c["test"] = tag
        out["constructions"].append(c)
    for a in m.attrs:
        a["test"] = tag
        out["attrs"].append(a)
    for d in m.dictkeys:
        d["test"] = tag
        out["dictkeys"].append(d)

json.dump(out, sys.stdout, indent=1)
