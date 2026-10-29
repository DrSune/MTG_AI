"""Card trees as Python: render any IR node as a constructor expression that evaluates back to an
equal node, and run a mapper's draft in a namespace holding only IR names.

docs/PLAN_CARD_ONBOARDING.md. Mappers read exemplars in this form and write their drafts in it, so
the tree they write is built by the IR's own constructors and validated by them.

- ``A(Verb.X, {"role": value, ...})`` builds ``Atom(verb, AtomArgs(pairs))``. Roles go in a dict
  because one of them is ``"from"``, a Python keyword.
- Fields that equal their dataclass default are left out.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any

from MTG_bot.core import ability_tree as at

WIDTH = 100


def A(verb: at.Verb, roles: dict[str, Any] | None = None, /, **more: Any) -> at.Atom:
    """An Atom from a verb and its roles (``roles`` dict, keywords for the identifier-safe ones)."""
    pairs = {**(roles or {}), **more}
    return at.Atom(verb=verb, args=at.AtomArgs(pairs=tuple(pairs.items())))


def namespace() -> dict[str, Any]:
    """Every public IR class and enum, ``A``, and a few harmless builtins."""
    ns: dict[str, Any] = {
        name: obj
        for name, obj in vars(at).items()
        if not name.startswith("_")
        and isinstance(obj, type)
        and (dataclasses.is_dataclass(obj) or issubclass(obj, enum.Enum))
    }
    ns["A"] = A
    ns["__builtins__"] = {
        "frozenset": frozenset, "tuple": tuple, "list": list, "dict": dict, "range": range,
        "len": len, "True": True, "False": False, "None": None,
    }
    return ns


def _default(field: dataclasses.Field) -> Any:
    if field.default is not dataclasses.MISSING:
        return field.default
    if field.default_factory is not dataclasses.MISSING:
        return field.default_factory()
    return dataclasses.MISSING


def _shape(node: Any) -> str | tuple[str, list[tuple[str, Any]], str]:
    """A leaf's text, or a bracketed node as (head, [(label, child)], tail)."""
    if isinstance(node, at.Atom):
        return (f"A(Verb.{node.verb.name}, {{", [(f"{r!r}: ", v) for r, v in node.args.pairs], "})")
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        kids = [
            (f"{f.name}=", getattr(node, f.name))
            for f in dataclasses.fields(node)
            if getattr(node, f.name) != _default(f)
        ]
        return (f"{type(node).__name__}(", kids, ")")
    if isinstance(node, enum.Enum):
        return f"{type(node).__name__}.{node.name}"
    if isinstance(node, frozenset):
        return "frozenset({" + ", ".join(repr(x) for x in sorted(node)) + "})" if node else "frozenset()"
    if isinstance(node, (tuple, list)):
        opener, closer = ("(", ")") if isinstance(node, tuple) else ("[", "]")
        if isinstance(node, tuple) and len(node) == 1:
            closer = ",)"
        return (opener, [("", x) for x in node], closer)
    if node is None or isinstance(node, (str, int, bool)):
        return repr(node)
    raise TypeError(f"not an IR value: {type(node).__name__}")


def render(node: Any, indent: int = 0, width: int = WIDTH, col: int | None = None) -> str:
    """A Python expression for ``node``: one line when it fits (starting at column ``col``),
    else one child per line, nested four spaces per level."""
    shape = _shape(node)
    if isinstance(shape, str):
        return shape
    head, kids, tail = shape
    flat = head + ", ".join(label + render(v, 0, 10**9) for label, v in kids) + tail
    if (indent if col is None else col) + len(flat) <= width or not kids:
        return flat
    pad = " " * (indent + 4)
    lines = [
        f"{pad}{label}{render(v, indent + 4, width, indent + 4 + len(label))},"
        for label, v in kids
    ]
    return head + "\n" + "\n".join(lines) + "\n" + " " * indent + tail.lstrip(",")


def render_card(keywords: tuple, abilities: tuple, notes: list[str] | None = None) -> str:
    """The draft-file form of a card's tree: ``keywords = [...]`` then ``abilities = [...]``."""
    out = ["keywords = ["] + [f"    {render(k, 4)}," for k in keywords] + ["]", "abilities = ["]
    for i, ab in enumerate(abilities):
        note = notes[i] if notes and i < len(notes) else ""
        out.append(f"    # [{i}] {note}".rstrip())
        out.append(f"    {render(ab, 4)},")
    out.append("]")
    return "\n".join(out)


def run_draft(text: str, compiled: tuple, compiled_keywords: tuple) -> tuple[tuple, tuple]:
    """Execute a draft. It must set ``abilities``; ``keywords`` defaults to the compiled ones.
    ``compiled`` / ``compiled_keywords`` hold the compiler's tree, to keep what it got right."""
    ns = namespace()
    ns["compiled"] = list(compiled)
    ns["compiled_keywords"] = list(compiled_keywords)
    exec(compile(text, "<draft>", "exec"), ns)  # noqa: S102 — local mapper drafts, IR names only
    if "abilities" not in ns:
        raise ValueError("the draft must set `abilities` (a list of ability nodes)")
    return tuple(ns.get("keywords", compiled_keywords)), tuple(ns["abilities"])
