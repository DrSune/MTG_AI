"""The engine primer: how the engine reads cards, measured for coverage (owner request 2026-10-24).

The owner: models should get "a description of how abilities interact, such that they understand
at least 99% of scenarios for how an atomic subcomponent would work … as little dubious as
possible". This module makes that target measurable.

**What a component is.** The engine compiles every card's oracle text into a tree of components.
Each is counted under its meaning: an effect verb, a selector mode, a keyword, a filter
predicate, or a cost, event, duration, quantity or control node. Structural wrappers are not
counted.

**What "exercised" means, and what it does not.** A component is *exercised* when at least one
scripted scenario pack that the engine passes puts a card containing it into play. That is NOT yet
proof that the pack's assertions depend on the component. Reporting it as proof would repeat the
parse-coverage-as-semantics mistake the review flags (REVIEW A-4). *Verified* coverage needs
mutation testing (perturb the component, require some pack to fail); it is the next step and is
reported separately once it exists. Packs are the only ground truth here.
Nothing in the primer is a paraphrase written from memory: each entry is the component's name, how
often the pools use it, a real card whose oracle text uses it, and how many verified packs
exercise it.

**The 99% number** is ``coverage()``: the share of all component OCCURRENCES in the pools whose
component is exercised. It is weighted by frequency because a component on 90 cards matters more
than one on 1. The uncovered list says exactly which packs to write next.

Packs are also track-R items. Once worked examples are embedded in the primer, the packs used
there must leave the evaluation split, or the primer leaks answers (docs/DESIGN_BENCHMARK.md §5).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from MTG_bot.core.ability_tree import (
    Atom,
    BackFace,
    FAtom,
    KeywordAbility,
    Selector,
    walk,
)
from MTG_bot.core.executor.games import get_supply

if TYPE_CHECKING:
    from MTG_bot.bench.masking import NameMasker

PACK_DIR = Path(__file__).resolve().parents[2] / "tools" / "scenarios"
#: Containers and connectives: they carry no game meaning of their own.
STRUCTURAL = frozenset(
    {"AtomArgs", "CardRecord", "Zone", "QConst", "Cost", "SpellAbility", "FAnd", "FOr", "FNot", "BackFace"}
)
ENGINE_SIMPLIFICATIONS = (
    "No priority passing: the active player gets one action window per turn, in the first main phase, then combat.",
    "Opponents can respond to a spell only with a counterspell, and in combat only with combat instants.",
    "Mana pools do not empty between steps or turns.",
    "Drawing from an empty library loses the game at the draw (CR 121.3); two simultaneous losers draw.",
    "Spells with more than one separate target slot cannot be cast yet.",
    "An effect that would have an opponent choose is decided by the engine for some cards (gap L-27).",
)


def component_of(node: Any) -> str | None:
    if isinstance(node, Atom):
        return f"verb:{node.verb.name}"
    if isinstance(node, Selector):
        return f"selector:{node.mode.name}"
    if isinstance(node, KeywordAbility):
        return f"keyword:{getattr(node.keyword, 'name', node.keyword)}"
    if isinstance(node, FAtom):
        return f"filter:{node.pred.name}"
    name = type(node).__name__
    return None if name in STRUCTURAL else f"node:{name}"


def components(card: Any) -> Counter[str]:
    # skip=BackFace, as every engine verdict does: the engine never plays a back face.
    return Counter(c for node in walk(card, skip=BackFace) if (c := component_of(node)) is not None)


#: Mana-cost components live on the cost line, which every card view shows; a text example for them
#: would point at an unrelated rules line.
NO_TEXT_EXAMPLE = frozenset({"node:CostManaColor", "node:CostManaGeneric", "node:CostManaHybrid"})


@dataclass
class Entry:
    component: str
    occurrences: int = 0
    cards: set[str] = field(default_factory=set)
    example: tuple[str, str] | None = None  # (card name, oracle text): the shortest text using it
    packs: set[str] = field(default_factory=set)

    @property
    def exercised(self) -> bool:
        return bool(self.packs)


def census(set_codes: tuple[str, ...] = ("M21", "ZNR"), pool_mode: str = "all") -> dict[str, Entry]:
    from MTG_bot.bench.view import OracleIndex  # compiled records keep no oracle text

    oracle = OracleIndex.for_sets(*set_codes)
    entries: dict[str, Entry] = {}
    for code in set_codes:
        supply = get_supply(pool_mode, code)
        for oid, result in supply.pool.results.items():
            card = result.card
            text = oracle.text(oid).strip()
            for comp, n in components(card).items():
                entry = entries.setdefault(comp, Entry(comp))
                entry.occurrences += n
                entry.cards.add(card.name)
                if comp in NO_TEXT_EXAMPLE or not text:
                    continue
                if entry.example is None or len(text) < len(entry.example[1]):
                    entry.example = (card.name, text)
    return entries


def _pack_cards(pack: dict, supply: Any) -> list[Any]:
    by_name = {meta.name: supply.pool.results[oid].card for oid, meta in supply.metas.items()}
    tokens = {r.card.name: r.card for r in supply.pool.results.values() if r.card.is_token}
    out = []
    names = [c["real"] for c in pack.get("cards", ()) if "real" in c]
    names += [s["real"] for s in pack.get("steps", ()) if s.get("op") == "cast" and "real" in s]
    for name in names:
        record = by_name.get(name) or tokens.get(name)
        if record is not None:
            out.append(record)
    return out


def attach_pack_evidence(entries: dict[str, Entry], pack_dir: Path = PACK_DIR) -> dict[str, int]:
    """Credit each component with the PASSING packs that put a card containing it into play."""
    from tools.run_scenarios import (
        run_pack,  # tools/ is a repo package, imported lazily
    )

    tally = Counter()
    for path in sorted(pack_dir.glob("*.json")):
        pack = json.loads(path.read_text())
        supply = get_supply("all", str(pack.get("set", "M21")))
        if run_pack(path, supply):
            tally["failing"] += 1
            continue
        tally["passing"] += 1
        for card in _pack_cards(pack, supply):
            for comp in components(card):
                if comp in entries:
                    entries[comp].packs.add(path.stem)
    return dict(tally)


def coverage(entries: dict[str, Entry]) -> dict[str, Any]:
    total = sum(e.occurrences for e in entries.values())
    covered = sum(e.occurrences for e in entries.values() if e.exercised)
    families: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for e in entries.values():
        fam = families[e.component.split(":", 1)[0]]
        fam[0] += e.occurrences * e.exercised
        fam[1] += e.occurrences
    uncovered = sorted((e for e in entries.values() if not e.exercised), key=lambda e: -e.occurrences)
    return {
        "components": len(entries),
        "exercised_components": sum(e.exercised for e in entries.values()),
        "occurrences": total,
        "exercised_occurrence_share": round(covered / total, 4) if total else 0.0,
        "verified_occurrence_share": None,  # needs mutation testing; never inferred from exercise
        "by_family": {k: round(v[0] / v[1], 4) for k, v in sorted(families.items()) if v[1]},
        "uncovered": [(e.component, e.occurrences, len(e.cards)) for e in uncovered],
    }


def render_primer(entries: dict[str, Entry], masker: NameMasker | None = None) -> str:
    """The text an agent gets. Real cards as examples, counts, and verification status only."""
    name = masker.label if masker else (lambda n: n)
    text = masker.mask if masker else (lambda t: t)
    cov = coverage(entries)
    lines = [
        "ENGINE PRIMER: how this engine reads cards (generated from the compiled card pools).",
        "Every card's text is compiled into components. Below, each component is listed with how often",
        "the pool uses it, one real card whose text uses it, and how many engine-checked scenarios exercise it.",
        f"Share of all component uses exercised by a passing scenario: {cov['exercised_occurrence_share']:.1%}.",
        "",
        "Engine simplifications (this is the game you are playing):",
        *(f"- {s}" for s in ENGINE_SIMPLIFICATIONS),
        "",
        "Components, most used first:",
    ]
    for e in sorted(entries.values(), key=lambda e: (-e.occurrences, e.component)):
        line = f"- {e.component}: {e.occurrences} uses on {len(e.cards)} cards"
        line += f"; exercised by {len(e.packs)} scenario(s)" if e.packs else "; NOT exercised by any scenario"
        if e.example:
            line += f'. Example, {name(e.example[0])}: "{text(e.example[1]).replace(chr(10), " / ")}"'
        lines.append(line)
    return "\n".join(lines)
