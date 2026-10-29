"""The corpus the card tools work from: every set's compile, per-sentence outcomes as exemplars, and
the component signatures already in use. docs/PLAN_CARD_ONBOARDING.md.

- ``compile_set`` compiles a set the way the supply does, but tolerant of refused cards (they are
  reported, not dropped silently), with card records applied (``require_verified=False``).
- ``Exemplars`` indexes every parsed sentence of every set with its template id and its tree as
  Python, and retrieves the ones worded most like a query (TF-IDF over word uni- and bigrams, after
  the card's own name becomes ``~`` and numbers become ``N``).
- ``signatures`` lists a tree's component shapes; a shape no compiled card has is flagged for
  review by gate G0 (a composition the executor has never run).
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass, is_dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (REPO, HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import irpy

from MTG_bot.core.ability_tree import Atom, Selector, walk
from MTG_bot.core.compiler import card_records
from MTG_bot.core.compiler.compiler import (
    CompileResult,
    _is_rule_reminder,
    compile_card,
    compile_pool,
)
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import RawCard, ingest_pool
from MTG_bot.core.errors import StateCorruptionError

DATA = REPO / "MTG_bot" / "data"
CACHE = REPO / ".cache" / "cards"
SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
_NUMBER_WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


@dataclass
class SetCompile:
    code: str
    raw: dict[str, RawCard]
    results: dict[str, CompileResult]
    refused: dict[str, str]  # oracle id -> the compiler's refusal
    records: dict[str, dict[str, Any]]

    def by_name(self, name: str) -> str:
        hits = [oid for oid, r in self.raw.items() if r.identity.name.lower() == name.lower()]
        if not hits:
            hits = [oid for oid, r in self.raw.items() if name.lower() in r.identity.name.lower()]
        if len(hits) != 1:
            raise SystemExit(f"{self.code}: {len(hits)} cards match {name!r}: "
                             + ", ".join(self.raw[o].identity.name for o in hits[:8]))
        return hits[0]


def compile_set(code: str, extra_records: dict[str, dict[str, Any]] | None = None) -> SetCompile:
    raw = ingest_pool(DATA / f"{code}.json")
    records = {**card_records.load_records(code), **(extra_records or {})}
    registry = build_full_registry()
    results: dict[str, CompileResult] = {}
    refused: dict[str, str] = {}
    for oid, rc in raw.items():
        try:
            out = compile_pool({oid: rc}, registry, records=records, require_verified=False)
            results[oid] = out.results[oid]
        except (StateCorruptionError, ValueError) as exc:
            refused[oid] = f"{type(exc).__name__}: {exc}"[:200]
    return SetCompile(code, raw, results, refused, records)


def normalize(sentence: str, name: str = "") -> str:
    s = sentence
    if name:
        s = s.replace(name, "~")
        short = name.split(",")[0]
        if short != name and len(short) > 3:
            s = s.replace(short, "~")
    s = re.sub(r"\b\d+\b", "N", s)
    s = re.sub(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b", "N", s, flags=re.IGNORECASE)
    return s


def _tokens(s: str) -> list[str]:
    words = re.findall(r"[a-z~]+|[+\-]n/[+\-]n|\{[^}]*\}|n", s.lower())
    return words + [f"{a} {b}" for a, b in itertools.pairwise(words)]


def sentence_status(raw: RawCard, result: CompileResult, sentence: str, registry: Any) -> str:
    if sentence in {s for s, _ in result.unparsed} or sentence in {s for s, _ in result.back_face_unparsed}:
        hint = next((h for s, h in (*result.unparsed, *result.back_face_unparsed) if s == sentence), "")
        return f"UNPARSED ({hint})"
    if result.record is not None:
        return "mapped (card record)"
    if _is_rule_reminder(sentence, raw) is not None:
        return "reminder"
    matches = registry.match(sentence)
    if matches:
        return matches[0].template.tid
    return "parsed (fallback or continuation)"


def _outcome_tree(outcome: Any) -> Any:
    for attr in ("effect", "ability", "cost"):
        if hasattr(outcome, attr):
            return getattr(outcome, attr)
    if hasattr(outcome, "keyword"):
        return outcome
    return outcome


def _cache_key() -> str:
    h = hashlib.sha256()
    for path in sorted((REPO / "MTG_bot" / "core" / "compiler").glob("*.py")):
        h.update(path.read_bytes())
    h.update((REPO / "MTG_bot" / "core" / "ability_tree.py").read_bytes())
    for code in SETS:
        h.update(str((DATA / f"{code}.json").stat().st_size).encode())
    return h.hexdigest()[:16]


class Exemplars:
    """Parsed sentences of all sets, retrievable by wording."""

    def __init__(self, rows: list[dict[str, Any]], signatures: dict[str, int]) -> None:
        self.rows = rows
        self.signatures = signatures
        self.df: Counter = Counter()
        self.vecs: list[dict[str, float]] = []
        for row in rows:
            self.df.update(set(_tokens(row["shape"])))
        n = len(rows)
        for row in rows:
            self.vecs.append(self._vec(row["shape"], n))

    def _vec(self, shape: str, n: int | None = None) -> dict[str, float]:
        n = n or len(self.rows)
        tf = Counter(_tokens(shape))
        v = {t: c * math.log((1 + n) / (1 + self.df.get(t, 0))) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def search(self, sentence: str, k: int = 6, name: str = "") -> list[tuple[float, dict[str, Any]]]:
        q = self._vec(normalize(sentence, name))
        scored = []
        seen: set[str] = set()
        for row, v in zip(self.rows, self.vecs, strict=True):
            score = sum(x * v.get(t, 0.0) for t, x in q.items())
            scored.append((score, row))
        scored.sort(key=lambda sr: -sr[0])
        out = []
        for score, row in scored:
            if row["shape"] in seen:
                continue
            seen.add(row["shape"])
            out.append((score, row))
            if len(out) >= k:
                break
        return out

    @classmethod
    def load(cls, rebuild: bool = False) -> Exemplars:
        CACHE.mkdir(parents=True, exist_ok=True)
        path = CACHE / f"exemplars_{_cache_key()}.json"
        if path.exists() and not rebuild:
            data = json.loads(path.read_text())
            return cls(data["rows"], data["signatures"])
        registry = build_full_registry()
        rows: list[dict[str, Any]] = []
        signatures: Counter = Counter()
        for code in SETS:
            sc = compile_set(code)
            for oid, result in sc.results.items():
                raw = sc.raw[oid]
                if result.record is None:
                    for sig in signatures_of(result.card):
                        signatures[sig] += 1
                for sentence in raw.sentences:
                    status = sentence_status(raw, result, sentence, registry)
                    if status.startswith(("UNPARSED", "mapped", "reminder", "parsed (")):
                        continue
                    outcome = registry.match(sentence)[0].outcome
                    try:
                        tree = irpy.render(_outcome_tree(outcome), 4)
                    except TypeError:
                        continue
                    rows.append({"set": code, "card": raw.identity.name, "sentence": sentence,
                                 "shape": normalize(sentence, raw.identity.name), "tid": status,
                                 "tree": tree})
        path.write_text(json.dumps({"rows": rows, "signatures": dict(signatures)}))
        return cls(rows, dict(signatures))


def signatures_of(card: Any) -> list[str]:
    """Component shapes: each atom's verb with its role names, each selector's mode and zones, and
    each ability's node type with its event type."""
    out = []
    for node in walk(card):
        if isinstance(node, Atom):
            out.append(f"atom {node.verb.name}(" + ",".join(r for r, _ in node.args.pairs) + ")")
        elif isinstance(node, Selector):
            zones = ",".join(sorted(z.kind.name for z in node.zones))
            out.append(f"selector {node.mode.name} [{zones}]")
        elif is_dataclass(node) and type(node).__name__.endswith("Ability"):
            event = getattr(node, "event", None)
            out.append(f"ability {type(node).__name__}" + (f" on {type(event).__name__}" if event else ""))
    return out


def compiled_card(sc: SetCompile, oid: str) -> CompileResult | None:
    return sc.results.get(oid)


def printed_only(raw: RawCard) -> CompileResult:
    """The card with its printed facts and no text: the base a mapper builds a refused card on."""
    from dataclasses import replace

    return compile_card(replace(raw, sentences=(), back_face=None), build_full_registry())
