"""Shared helpers of the component review: load the dump, the populations, token kinds."""
from __future__ import annotations

import os
import pickle
import re
from collections import Counter
from pathlib import Path

HOME = ("M21", "M20", "FDN")
REPO = Path(__file__).resolve().parents[2]
#: dump.py's output (gitignored, rebuilt on demand); CR_DUMP overrides it
DUMP = Path(os.environ.get("CR_DUMP", REPO / ".cache" / "component_review" / "dump.pkl"))


def load() -> list[dict]:
    if not DUMP.exists():
        raise SystemExit(f"{DUMP} is missing: run reports/component_review_2026-11-17/dump.py first")
    return pickle.loads(DUMP.read_bytes())


def verified_home(rows: list[dict]) -> list[dict]:
    """The verified cards of M21, M20 and FDN (home stamps and the 6 FDN reprint stamps of M20
    homes), one row per oracle id, the first set's (M21, M20, FDN order)."""
    out, seen = [], set()
    for code in HOME:
        for r in rows:
            if r["set"] == code and r["state"] == "verified" and r["oid"] not in seen:
                seen.add(r["oid"])
                out.append(r)
    return out


def compiled_all(rows: list[dict]) -> list[dict]:
    """Every compiled tree of the 19 sets (refused cards out), one row per oracle id, the first
    set's in corpus order (the learner's ``table_records`` rule)."""
    out, seen = [], set()
    for r in rows:
        if "tokens" in r and r["oid"] not in seen:
            seen.add(r["oid"])
            out.append(r)
    return out


_QTAGS = {"QConst", "QX", "QUnbounded", "QCount", "QPartyCount", "QDistinctColorCount", "QProp",
          "QBin", "QThisTurn", "QAtLeast", "QAtMost"}


def kind(tok: str) -> str:
    """A token's kind, for the reports."""
    if tok.startswith("Verb."):
        return "verb"
    if tok.startswith("FAtomPred."):
        return "filter predicate"
    if tok.startswith("num:") or tok in _QTAGS or tok.startswith(("QPropField.", "QAgg.", "QBinOp.",
                                                                      "ThisTurnKind.", "Rounding.")):
        return "quantity"
    if tok.startswith("Duration"):
        return "duration"
    if tok.startswith("role:"):
        return "role"
    if tok.startswith("Keyword."):
        return "keyword"
    if tok.startswith("@"):
        return "field"
    if tok.startswith(("type:", "sub:", "mv:")):
        return "face"
    if tok.endswith("Event") or tok.startswith(("Phase.", "Step.", "AbilityKind.")):
        return "event"
    if tok.startswith("str:"):
        return "string"
    if tok.startswith(("Cost", "CounterKind.")):
        return "cost/counter"
    if tok.startswith(("SelectorMode.", "ZoneKind.", "ControllerRef.", "ZonePosition.")) or tok in (
            "Selector", "Zone"):
        return "selector/zone"
    return "other"


def doc_freq(rows: list[dict]) -> Counter:
    """How many cards use each token (each card counted once per token)."""
    c: Counter = Counter()
    for r in rows:
        c.update(set(r["tokens"]))
    return c


def norm_sentence(s: str, name: str) -> str:
    """A sentence with the card's name as ~ (as corpus.normalize)."""
    if name:
        s = s.replace(name, "~")
        short = name.split(",")[0]
        if short != name and len(short) > 3:
            s = s.replace(short, "~")
    return s


_NUM_WORDS = r"\b(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|X|\d+)\b"
COLOR_WORDS = ("white", "blue", "black", "red", "green")
TYPE_WORDS = ("artifact", "creature", "enchantment", "land", "planeswalker", "instant", "sorcery",
              "permanent", "spell", "card", "token", "Aura", "Equipment", "Vehicle")


def slot_shape(s: str, name: str = "") -> str:
    """A sentence with its slot words freed: numbers, colour words, card-type words, coloured mana
    symbols, P/T modifiers (207 §4's slots, with types)."""
    s = norm_sentence(s, name)
    s = re.sub(r"[+\-]\d+/[+\-]\d+", "+N/+N", s)
    s = re.sub(r"\b\d+/\d+\b", "N/N", s)
    s = re.sub(r"\{[WUBRG]\}", "{C}", s)
    s = re.sub(r"\{\d+\}", "{N}", s)
    s = re.sub(r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b", "N", s,
               flags=re.IGNORECASE)
    s = re.sub(r"\b(?:" + "|".join(COLOR_WORDS) + r")\b", "COLOR", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(?:non)?(?:" + "|".join(TYPE_WORDS) + r")s?\b", "TYPE", s)
    return s
