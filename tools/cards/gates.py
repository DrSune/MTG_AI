"""Automatic gates G0 (static) and G3 (adequacy by mutation analysis). docs/PLAN_CARD_ONBOARDING.md.

G0 never needs a model: strict round trip, printed facts unchanged, every number of the text in the
tree, MTGJSON keywords present, verbs the executor supports, castable if it is a permanent spell,
clause traceability, and component shapes never compiled before (flagged for review, not failed).

G3 mutates the tree with fault-model operators that mirror the bugs an RL policy would exploit (a
wrong amount, a lost duration, a flipped controller, a widened scope, a dropped step, a dropped
cost, an optional made mandatory, a wrong zone, a dropped keyword), probes every viable mutant, and
reports the mutants whose probe trace is identical to the original's: parts of the card no evidence
exercised. Those need a spec pack (gate G4) before the card can be verified.
"""

from __future__ import annotations

import dataclasses
import re
import sys
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, get_args

HERE = Path(__file__).resolve().parent
for _p in (HERE.parents[1], HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import lints
from probe import Probe

from MTG_bot.core.ability_tree import (
    DESIGNATED_PLAYER_REFS,
    Ability,
    AbilityTriggerEvent,
    ActivatedAbility,
    Atom,
    AtomArgs,
    CardRecord,
    Choose,
    Conditional,
    ControllerRef,
    Cost,
    DamageDealtEvent,
    DelayedTrigger,
    DurationEot,
    DurationPermanent,
    EtBState,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    Keyword,
    KeywordAbility,
    OptionalEffect,
    Phase,
    QAtMost,
    QBin,
    QBinOp,
    QConst,
    QProp,
    QPropField,
    QUnbounded,
    ReplacementAbility,
    Selector,
    SelectorMode,
    Seq,
    SpellAbility,
    StaticAbility,
    TargetingEvent,
    TokenSpec,
    TriggeredAbility,
    TurnPhaseEvent,
    Verb,
    Zone,
    ZoneKind,
    ZonePosition,
    from_dict,
    gathers_occurrences,
    orders_a_library,
    to_dict,
    walk,
)
from MTG_bot.core.compiler.compiler import CompileResult, _engine_supported
from MTG_bot.core.compiler.ingest import RawCard
from MTG_bot.core.executor import SUPPORTED_VERBS_V2
from MTG_bot.core.executor.games import deck_rule_copies
from MTG_bot.core.executor.query import _player_widening_applies
from MTG_bot.core.identity import LegalityFlags

_NUM_WORDS = {w: i for i, w in enumerate(
    ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"))}

# CR 207.2c: ability words have no rules meaning, so a tree has nothing to show for them (the
# ability itself is checked like any other clause). MTGJSON lists them with the keywords; spelled
# as G0 normalises MTGJSON keywords.
ABILITY_WORDS = frozenset(w.upper().replace(" ", "_") for w in (
    "adamant", "addendum", "alliance", "battalion", "bloodrush", "celebration", "channel", "chroma",
    "cohort", "constellation", "converge", "council's dilemma", "coven", "delirium", "descend 4",
    "descend 8", "domain", "eerie", "eminence", "enrage", "fateful hour", "fathomless descent",
    "ferocious", "flurry", "formidable", "grandeur", "hellbent", "hero's reward", "heroic", "imprint",
    "inspired", "join forces", "kinship", "landfall", "lieutenant", "magecraft", "metalcraft",
    "morbid", "pack tactics", "paradox", "parley", "radiance", "raid", "rally", "revolt",
    "secret council", "spell mastery", "strive", "survival", "sweep", "tempting offer", "threshold",
    "underdog", "undergrowth", "valiant", "will of the council"))
# CR 701.22, 701.17: keyword actions MTGJSON lists with the keywords that have no Keyword member
# (ontology round R12): the tree performs them as its verb (SCRY) or as the merged MOVE whose
# journal_kind names them (MILL, verbs.py _v_move_zone), and G0 demands that as it demands a keyword.
KEYWORD_ACTIONS = frozenset({"SCRY", "MILL"})


# ----------------------------------------------------------------------------- G0
def _ints(node: Any) -> set[int]:
    out: set[int] = set()

    def visit(x: Any) -> None:
        if isinstance(x, bool):
            return
        if isinstance(x, int):
            out.add(abs(x))
        elif dataclasses.is_dataclass(x) and not isinstance(x, type):
            if isinstance(x, AtomArgs):
                for _, v in x.pairs:
                    visit(v)
                return
            if (isinstance(x, FNot) and isinstance(x.inner, FAtom) and x.inner.pred is FAtomPred.QTY_GE
                    and isinstance(x.inner.count, QConst)):
                out.add(abs(x.inner.count.value - 1))  # "N or less": the comparison at N + 1, negated
            for f in dataclasses.fields(x):
                visit(getattr(x, f.name))
        elif isinstance(x, (tuple, list, frozenset)):
            for item in x:
                visit(item)

    visit(node)
    return out


def text_numbers(raw: RawCard) -> set[int]:
    """Numbers the rules text states (reminder text in parentheses left out)."""
    nums: set[int] = set()
    for sentence in raw.sentences:
        s = re.sub(r"\([^)]*\)", "", sentence)
        s = s.replace(raw.identity.name, "~")
        nums |= {int(m) for m in re.findall(r"(?<![\w/])[+\-−]?(\d+)", s)}
        nums |= {_NUM_WORDS[w.lower()] for w in re.findall(r"\b(" + "|".join(_NUM_WORDS) + r")\b", s, re.IGNORECASE)}
    nums.discard(0)
    return nums


#: The tree paths a clause's ``ir`` names: "abilities[1].effect.steps[0]", "keywords[0]".
_IR_PATH = re.compile(r"\b(abilities|keywords)\[(\d+)\]")
#: The labels a clause's ``ir`` may carry in place of a tree path (docs/MAPPER_GUIDE.md "Labelled
#: sentences"): a card's own deck-construction rule (CR 100.2a, ``games.deck_rule_copies``), and a
#: sentence labelled inert for good (``lints.INERT``). Each is accepted on its sentences only.
_IR_LABEL = re.compile(r"^(deck rule|inert)\b")


def clause_trace_faults(raw: RawCard, card: CardRecord, clauses: list[dict]) -> list[str]:
    """What is wrong with a draft's clause trace beyond coverage: each clause's ``ir`` names a
    tree path the card has, or is a label its sentence takes. A clause of reminder text alone
    needs no trace."""
    inert = {s for oid, s in lints.INERT if oid == raw.identity.oracle_id}
    out = []
    for clause in clauses:
        core = re.sub(r"\s*\([^)]*\)", "", str(clause.get("clause", ""))).strip()
        ir = str(clause.get("ir", "")).strip()
        if not core:
            continue
        label = m.group(1) if (m := _IR_LABEL.match(ir)) else None
        for name, holds in (("deck rule", deck_rule_copies(core, raw.identity.name) is not None),
                            ("inert", lints.rules_sentence(raw, core) in inert)):
            if holds and label != name:
                out.append(f"clause {core[:60]!r} has no tree: trace it as {name!r}")
            elif label == name and not holds:
                out.append(f"clause {core[:60]!r}: {name!r} labels only "
                           + ("a card's own deck-construction rule (CR 100.2a)" if name == "deck rule"
                              else "a sentence lints.INERT lists"))
        if label is not None:
            continue
        paths = _IR_PATH.findall(ir)
        if not paths:
            out.append(f"clause {core[:60]!r}: its ir {ir[:40]!r} names no tree path (abilities[i], "
                       "keywords[i]) and no label")
        out += [f"clause {core[:60]!r}: its ir names {kind}[{i}], which the tree does not have"
                for kind, i in paths if int(i) >= len(getattr(card, kind))]
    return out


def g0(raw: RawCard, base: CardRecord, card: CardRecord, *, clauses: list[dict] | None,
       known_signatures: dict[str, int] | None) -> tuple[list[str], list[str]]:
    """(failures, warnings) for one card tree."""
    fails: list[str] = []
    warns: list[str] = []
    for kw in card.keywords:
        if from_dict("KeywordAbility", to_dict(kw)) != kw:
            fails.append(f"keyword {kw} does not round-trip")
    for ab in card.abilities:
        if from_dict(to_dict(ab)["tag"], to_dict(ab)) != ab:
            fails.append(f"ability {type(ab).__name__} does not round-trip")
    for field in ("name", "type_line", "types", "subtypes", "supertypes", "colors", "mana_cost",
                  "mana_value", "power", "toughness", "loyalty", "is_token"):
        if getattr(card, field) != getattr(base, field) and not (
            field in ("power", "toughness") and getattr(base, field) is None
        ):
            fails.append(f"printed fact changed: {field}")
    tree_ints = _ints(card.abilities) | _ints(card.keywords) | _ints(card.mana_cost) | _ints(
        (card.power, card.toughness, card.loyalty))
    missing = sorted(text_numbers(raw) - tree_ints)
    if missing:
        warns.append(f"numbers in the text but not in the tree: {missing}")
    printed_kw = {k.upper().replace(" ", "_") for k in raw.keywords} - ABILITY_WORDS
    tree_kw = {k.keyword.name for k in card.keywords} | {
        n.keyword.name for n in walk(card) if isinstance(n, KeywordAbility)}
    # Keyword actions the compiler writes as their verb (scry; fight is both a Verb and a Keyword):
    # the verb in the tree satisfies the printed keyword.
    tree_kw |= {n.verb.name for n in walk(card) if isinstance(n, Atom)}
    # ... or as the merged MOVE atom, whose journal_kind slot names the keyword action it
    # performs: the mill shape writes "MILL" (verbs.py _v_move_zone), so it satisfies "Mill".
    tree_kw |= {str(n.args.get("journal_kind")) for n in walk(card)
                if isinstance(n, Atom) and n.verb is Verb.MOVE_ZONE} & KEYWORD_ACTIONS
    # MTGJSON lists a token's artifact type with the keywords ("Food"): the subtype of a token the
    # tree makes satisfies it (MAPPER_GUIDE "Food tokens").
    tree_kw |= {s.upper() for n in walk(card) if isinstance(n, TokenSpec) for s in n.subtypes}
    demanded = set(Keyword.__members__) | KEYWORD_ACTIONS
    unknown = sorted(k for k in printed_kw - tree_kw if k in demanded)
    if unknown:
        fails.append(f"MTGJSON keywords missing from the tree: {unknown}")
    absent = sorted(k for k in printed_kw - tree_kw if k not in demanded)
    if absent:
        warns.append(f"MTGJSON keywords with no Keyword atom (check how the tree expresses them): {absent}")
    if not _engine_supported(card, set(SUPPORTED_VERBS_V2)):
        verbs = sorted({n.verb.name for n in walk(card) if isinstance(n, Atom)} - {v.name for v in SUPPORTED_VERBS_V2})
        fails.append(f"verbs the executor does not support: {verbs or 'a shape gate (X-kicker / non-constant EtB counters)'}")
    spells = sum(isinstance(a, SpellAbility) for a in card.abilities)
    if spells > 1:
        fails.append(f"{spells} SpellAbility nodes: a card has one (the compiler may already carry the "
                     "permanent's cast carrier; do not append another)")
    permanent = any(t in card.types for t in ("Creature", "Enchantment", "Artifact", "Planeswalker"))
    # A token is created, never cast (it cannot be in a hand, CR 111.8), so it needs no carrier.
    if (permanent and "Land" not in card.types and not card.is_token
            and not any(isinstance(a, SpellAbility) for a in card.abilities)):
        fails.append("a permanent spell with no SpellAbility cannot be cast (add the carrier "
                     "SpellAbility(kind=SpellKind.<TYPE>) last, as the compiler does for creatures)")
    fails += [f"lint {f}" for f in lints.lint(raw, card)]  # tree against text (lints.py)
    if clauses is not None:
        covered = " ".join(c.get("clause", "") for c in clauses)
        for sentence in raw.sentences:
            core = re.sub(r"\s*\([^)]*\)", "", sentence).strip()
            if core and core not in covered:
                fails.append(f"clause not traced to the tree: {core!r}")
        fails += clause_trace_faults(raw, card, clauses)
    if known_signatures is not None:
        from corpus import signatures_of

        new = sorted({s for s in signatures_of(card) if s not in known_signatures})
        if new:
            warns.append("component shapes no compiled card has (review them in the probe): " + "; ".join(new))
    return fails, warns


# ----------------------------------------------------------------------------- G3
def _rebuild(node: Any, path: tuple, new: Any) -> Any:
    """``node`` with the value at ``path`` replaced (a path of field names / tuple indexes)."""
    if not path:
        return new
    head, rest = path[0], path[1:]
    if isinstance(node, AtomArgs):
        pairs = tuple((r, _rebuild(v, rest, new) if r == head else v) for r, v in node.pairs)
        return AtomArgs(pairs=pairs)
    if isinstance(node, tuple):
        items = list(node)
        items[head] = _rebuild(items[head], rest, new)
        return tuple(items)
    return dataclasses.replace(node, **{head: _rebuild(getattr(node, head), rest, new)})


def _paths(node: Any, path: tuple = ()) -> Iterator[tuple[tuple, Any]]:
    yield path, node
    if isinstance(node, AtomArgs):
        for role, v in node.pairs:
            yield from _paths(v, (*path, role))
    elif isinstance(node, tuple):
        for i, v in enumerate(node):
            yield from _paths(v, (*path, i))
    elif dataclasses.is_dataclass(node) and not isinstance(node, type):
        for f in dataclasses.fields(node):
            yield from _paths(getattr(node, f.name), (*path, f.name))


_TOKENS: list[TokenSpec] = []
_ABILITY_TYPES: tuple[type, ...] = get_args(Ability)
_ACTOR_YOU = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)


def _verified_tokens() -> list[TokenSpec]:
    """Token specs proven elsewhere, so a card creating a byte-identical token (a Treasure, a
    Soldier, a Food) need not re-prove the token's own abilities: those on the M21 golden trees
    (the BUGCATCH-verified pool), and the one Food (``lints.FOOD``, the R_FOOD ruling; the
    ``food`` lint refuses every other Food spec), every part of which two suite packs pin:
    mapped/FDN bake_into_a_pie_destroys_and_bakes_a_food ({2}, the sacrifice, the 3 life) and
    bake_into_a_pie_a_tapped_food_cannot_be_eaten ({T}). A golden token record proves nothing
    here: FDN's own Food record compiles to no ability at all (test_gates)."""
    if not _TOKENS:
        from MTG_bot.core.compiler.compiler import compile_pool
        from MTG_bot.core.compiler.coverage import build_full_registry
        from MTG_bot.core.compiler.ingest import ingest_pool

        pool = compile_pool(ingest_pool(HERE.parents[1] / "MTG_bot" / "data" / "M21.json"),
                            build_full_registry())
        seen: list[TokenSpec] = [lints.FOOD]
        for card in pool.cards.values():
            seen += [n for n in walk(card) if isinstance(n, TokenSpec) and n not in seen]
        _TOKENS.extend(seen)
    return _TOKENS


def _is_self(filter_: Any) -> bool:
    if isinstance(filter_, FAtom):
        return filter_.pred is FAtomPred.IS_SOURCE
    if isinstance(filter_, FAnd):
        return any(_is_self(c) for c in filter_.children)
    return False


def _reveal_dead_roles(ability: Any) -> set[str]:
    """The roles of the top-of-library REVEALs of ``ability`` (``controller`` and ``count``) no game
    state can observe (see ``mutants``): REVEAL is a recorded no-op (verbs.py ``_look``: it moves
    nothing, the journal has no row for it, and no reader of its event-log row plays: the seat view
    tracks no revealed card). Its only outputs are the look window, read by a Conditional right
    after it or a ONE_OF/REST partition over the library top, and the ``result`` register, read by
    a ``referent="result"`` node, THAT_MANY_COUNT or FIGHT's attacker. With none of those in the
    ability, controller and count are dead. A Conditional judges the window's first card, the top
    card for any count >= 1, so it leaves count dead. Several REVEALs qualify when each sits in its
    own option of one "choose one" (a count-1 Choose: the executor runs exactly one option, so at
    most one REVEAL runs; query.choose_options reads no option's contents). A REVEAL of named
    ``cards`` (a hand, or the ``result`` of the instruction before: DESIGN_ATOM_ONTOLOGY §19) is
    no look here: it opens no window, and its outputs are its row and, for the cards found, the
    ``result`` register written again with the same cards, which only a bare Conditional after it
    reads as fresh. ``mutants`` holds its ``cards`` dead; no operator yields another valid
    ``cards`` today (a hand's controller flip names no one player's hand, and the referent admits
    RESULT_REFERENT alone). An operator that does must leave a ``result`` reveal live before a
    Conditional (BACKLOG, the scaffold)."""
    if not isinstance(ability, (TriggeredAbility, ActivatedAbility, SpellAbility)):
        return set()
    nodes = list(walk(ability))
    looks = [n for n in nodes if isinstance(n, Atom) and n.verb in (Verb.REVEAL, Verb.LOOK_AT)
             and n.args.get("cards") is None]
    if not looks or any(n.verb is not Verb.REVEAL or n.args.get("duration") is not None for n in looks):
        return set()
    if len(looks) > 1 and not _one_per_option(ability, looks):
        return set()
    for n in nodes:
        if getattr(n, "referent", None) == "result" or (
                isinstance(n, QProp) and n.field is QPropField.THAT_MANY_COUNT) or (
                isinstance(n, Atom) and n.verb is Verb.FIGHT) or (
                isinstance(n, Selector) and n.mode in (SelectorMode.ONE_OF, SelectorMode.REST)
                and any(z.kind is ZoneKind.LIBRARY and z.position is ZonePosition.TOP for z in n.zones)):
            return set()
    return {"count"} if any(isinstance(n, Conditional) for n in nodes) else {"controller", "count"}


def _one_card_result_moves(ability: Any, base: tuple) -> set[tuple]:
    """Paths of the MOVE_ZONE atoms of ``ability`` that move the ``result`` of a one-card look, so
    that their library-order mutant is dead (see ``mutants``): Garruk, Savage Herald's +1, "Reveal
    the top card of your library. If it's a creature card, put it into your hand. Otherwise, put
    it on the bottom of your library." The ability's one REVEAL or LOOK_AT takes QConst(1) cards
    and no ``until``, and the step right after it in a Seq is the move, or a Conditional or
    OptionalEffect around it, reading ``referent="result"``. That look is a fresh top-of-library
    look (the ability has no other, so ``_look`` has no prior window), which writes the top card
    alone to ``result`` (none from an empty library), and nothing runs in between, so the move
    holds at most one card and has no order to choose (``verbs._arrange`` asks nothing)."""
    looks = [n for n in walk(ability) if isinstance(n, Atom) and n.verb in (Verb.REVEAL, Verb.LOOK_AT)]
    if len(looks) != 1 or looks[0].args.get("count") != QConst(1) or looks[0].args.get("until") is not None:
        return set()
    out: set[tuple] = set()
    for path, node in _paths(ability, base):
        if not isinstance(node, Seq) or node.steps[0] is not looks[0] or len(node.steps) < 2:
            continue
        step, at = node.steps[1], (*path, "steps", 1)
        branches = [(step, at)]
        if isinstance(step, Conditional):
            branches = [(step.then_effect, (*at, "then_effect")), (step.else_effect, (*at, "else_effect"))]
        elif isinstance(step, OptionalEffect):
            branches = [(step.inner, (*at, "inner"))]
        out |= {p for move, p in branches if isinstance(move, Atom) and move.verb is Verb.MOVE_ZONE
                and getattr(move.args.get("cards"), "referent", None) == "result"}
    return out


def _static_disclosures(ability: Any, base: tuple) -> set[tuple]:
    """Paths of the controller and count of the REVEAL and LOOK_AT atoms a static ability
    performs itself ("You may look at the top card of your library any time": M21 Radha, Heart of
    Keld, M20 Mystic Forge; "Play with the top card of your library revealed": Conspicuous Snoop),
    which no game state can observe (see ``mutants``): the static lane registers each as a
    "disclosure" layer record (``layers.LayerRegistry._new_static``) that nothing reads, and runs
    no look. A duration stays live: one the layer lane cannot parse drops the whole static, its
    permission beside the look included. Only the static's own instructions (its effect's steps,
    a "you may" around one), never an ability it grants."""
    if not isinstance(ability, StaticAbility):
        return set()
    out: set[tuple] = set()

    def visit(node: Any, path: tuple) -> None:
        if isinstance(node, Atom) and node.verb in (Verb.REVEAL, Verb.LOOK_AT):
            out.update({(*path, "args", "controller"), (*path, "args", "count")})
        elif isinstance(node, Seq):
            for i, step in enumerate(node.steps):
                visit(step, (*path, "steps", i))
        elif isinstance(node, OptionalEffect):
            visit(node.inner, (*path, "inner"))

    visit(ability.effect, (*base, "effect"))
    return out


def _one_card_picks(ability: Any, base: tuple) -> set[tuple]:
    """Paths of the counts no game can observe on a CHOOSE or ONE_OF selector of one card over the
    top or the bottom of one player's library (see ``mutants``): the zone holds that one card
    (``selectors.enumerate_zone``), so a count of 2 or more picks it too (a CHOOSE slices its
    population; a ONE_OF over one candidate takes it, resolving as much as it can, CR 608.2c).
    M20 Mystic Forge's "{T}, Pay 1 life: Exile the top card of your library". Only the count 1:
    a count that can be 0 picks nothing then, and a larger one over the top card is a
    miscompile ("the top three cards") whose mutants a pack must still catch. A ONE_OF over the
    library top reads the look window instead when a look opened one (``resolve_selector``), so
    the ability must have no REVEAL or LOOK_AT; a cost's selector is the payment ask's."""
    nodes = list(_paths(ability, base))
    if any(isinstance(n, Atom) and n.verb in (Verb.REVEAL, Verb.LOOK_AT) for _p, n in nodes):
        return set()
    costs = [p for p, n in nodes if isinstance(n, Cost)]
    one_player = (ControllerRef.YOU, *DESIGNATED_PLAYER_REFS)
    return {
        (*path, "count")
        for path, n in nodes
        if isinstance(n, Selector) and n.referent is None and n.count == QConst(1)
        and n.mode in (SelectorMode.CHOOSE, SelectorMode.ONE_OF) and len(n.zones) == 1
        and n.zones[0].kind is ZoneKind.LIBRARY and n.zones[0].controller in one_player
        and n.zones[0].position in (ZonePosition.TOP, ZonePosition.BOTTOM)
        and not any(path[: len(c)] == c for c in costs)
    }


def _one_per_option(ability: Any, atoms: list[Atom]) -> bool:
    """Each of ``atoms`` lies in a different option of the same count-1 Choose of ``ability``."""
    found: list[tuple[tuple, Any]] = list(_paths(ability))
    where = [next(p for p, n in found if n is atom) for atom in atoms]
    owners = set()
    for path in where:
        cut = next((k for k in range(len(path) - 1, -1, -1)
                    if isinstance(dict(found).get(path[:k]), Choose) and path[k:k + 1] == ("options",)), None)
        if cut is None:
            return False
        owners.add((path[:cut], path[cut + 1]))
    choose_paths = {c for c, _ in owners}
    if len(choose_paths) != 1 or len(owners) != len(atoms):
        return False
    choose = dict(found)[next(iter(choose_paths))]
    return isinstance(choose.count, QConst) and choose.count.value == 1


def _twin_targets(ability: Any, base: tuple) -> set[tuple]:
    """Paths of the TARGET selectors in ``ability`` that "target->all" cannot change (see
    ``mutants``). Two or more atoms carry the same TARGET selector in their ``target`` role and
    nothing else designates (no other TARGET selector, no designated player: a second slot
    makes a multi-slot designation, whose ALL atom would read the union binding), so there is
    one designation slot, which the remaining twins keep whichever one is mutated, and
    role_handles hands a referent-free ALL selector in the bound role the designation itself.
    The selector keeps role_handles' self-resolving shapes out (anaphora, referent-filtered
    population, player side, graveyard sweep, a player designation into a card population):
    an exact count >= 1, battlefield or stack zones (a counterspell's COUNTER_SPELL reads its
    target through role_handles too), no referent in it, and no "any target" player widening
    (query._player_widening_applies). Twins under a nested ability, token, or delayed or
    reflexive trigger are designated by that object, not by this one, so they stay out.
    - A spell: the cast lane walks every TARGET selector of its effect, those in a Choose made
      as the effect resolves included (query.spell_target_slots), and refuses a cast whose slot
      is not designated (stack._validate_spell_targets), so the designation binds whatever
      option resolution picks (Gods Willing's colour). A modal spell (its effect a top-level
      Choose, query.modal_choose) announces its modes as it is cast and only their targets
      exist (query.with_modes), so a mutant's chosen mode could hold no slot: it stays out.
    - A triggered ability: binding.TriggerBinder._designate designates the one distinct
      selector as the trigger goes on the stack, removes the trigger when a required slot has
      no legal choice (CR 603.3d) and checks it again as it resolves (CR 608.2b). A slot is
      required outside every Choose (binding._required_target_keys: the union over Seq,
      Conditional, OptionalEffect, Repeat and EachPlayer, the intersection over a Choose's
      options), so with no Choose above a twin every mutant's slot is required, and the
      mutant designates, is removed and resolves exactly as the card. Twins in the options of
      a Choose (Tolarian Kraken's reflexive "tap or untap target creature") stay out: the
      mutant's slot is no longer required, so with no legal target its trigger still goes on
      the stack.
    - An activated ability (Sorin, Imperious Bloodlord's first +1): ``activate`` validates the
      designation against query.activation_target_slots (every TARGET selector of the
      ability's own nodes, deduped by repr) and refuses an empty one for a slot that needs a
      target before any cost is paid (legality.activation_target_reason, CR 602.2b, 601.2c);
      the act menu offers the row only when every slot can be designated (menu.can_designate);
      resolve_activated re-checks the same slot (CR 608.2b) and binds ``target``. Every mutant
      keeps the slot, so it is offered, refused, designated and resolved as the card. A lone
      TARGET selector is no twin: its mutant has no slot and is activated with no target
      (Celestial Enforcer). A Choose above a twin stays out here too. Here an "up to one"
      count (QAtMost(1)) qualifies as well (Garruk, Unleashed's +1, Mu Yanling, Sky Dancer's
      +2): a designation that chose nothing is bound as the empty designation
      (resolve_activated binds ``target`` to [] whenever query.designates finds a slot, which
      the remaining twin keeps), so role_handles hands the ALL twin no object; a chosen target
      that is illegal on resolution stops the whole ability (CR 608.2b). A lone "up to" TARGET
      has no slot left in its mutant, nothing is bound, and the ALL selector acts on its whole
      population. Spells and triggers bind the empty designation too, but no card in the 19
      sets has "up to" twins there, so they keep the exact count."""
    if isinstance(ability, SpellAbility):
        if isinstance(ability.effect, Choose):
            return set()  # a modal spell
    elif not isinstance(ability, (TriggeredAbility, ActivatedAbility)):
        return set()
    found = list(_paths(ability, base))
    nodes = dict(found)
    sels = [(p, n) for p, n in found if isinstance(n, Selector) and n.mode is SelectorMode.TARGET]
    if len(sels) < 2 or any(n != sels[0][1] for _, n in sels) or any(p[-2:] != ("args", "target") for p, _ in sels):
        return set()
    if any(isinstance(n, ControllerRef) and n in DESIGNATED_PLAYER_REFS for _, n in found):
        return set()
    blocked: tuple[type, ...] = (*_ABILITY_TYPES, DelayedTrigger, TokenSpec)
    if not isinstance(ability, SpellAbility):
        blocked = (*blocked, Choose)
    if any(isinstance(nodes.get(p[:k]), blocked) for p, _ in sels for k in range(len(base) + 1, len(p))):
        return set()
    sel = sels[0][1]
    up_to_one = isinstance(ability, ActivatedAbility) and sel.count == QAtMost(n=1)
    if not (isinstance(sel.count, QConst) and sel.count.value >= 1 or up_to_one) or sel.referent is not None \
            or any(getattr(n, "referent", None) is not None for n in walk(sel.filter)) \
            or not all(z.kind in (ZoneKind.BATTLEFIELD, ZoneKind.STACK) for z in sel.zones) \
            or _player_widening_applies(sel):
        return set()
    return {p for p, _ in sels}


def _scope_fixed_by_condition(trigger: Any) -> bool:
    """Is the "your turn -> each turn" mutant of ``trigger``'s TurnPhaseEvent dead (see
    ``mutants``)? The event's actor is "you" (CONTROLLER_IS YOU over the active player,
    binding._match_node) and the trigger's condition requires TURN_OF YOU at its top: the raid
    idiom "at the beginning of your end step, if you attacked this turn" (TURN_OF YOU and an
    attack this turn). Without the actor the event matches on another player's turn, but
    TriggerBinder._queue checks the intervening "if" at once (CR 603.4) and queues nothing:
    no instance, no seq, no journal row. The one thing it does first is layers.recompute(),
    a no-op where the layers are current. They are at the end step's marker: the second main
    phase's state checks recomputed them, and ending a step only empties mana pools
    (Executor._end_step; combat's end recomputes in _leave_combat). The upkeep's marker comes
    after the untap step expires "until your next turn" effects with no recompute
    (Executor._turn_based_actions), so a recompute there could change what a later matcher
    reads: only END_TURN takes the rule."""
    if not isinstance(trigger, TriggeredAbility) or not isinstance(trigger.event, TurnPhaseEvent):
        return False
    if trigger.event.phase is not Phase.END_TURN or trigger.event.actor != _ACTOR_YOU:
        return False
    cond = trigger.condition
    turn_of_you = FAtom(pred=FAtomPred.TURN_OF, who=ControllerRef.YOU)
    return cond == turn_of_you or isinstance(cond, FAnd) and turn_of_you in cond.children


def _static_prevention_conditions(ability: Any, base: tuple) -> set[tuple]:
    """Paths of the ``condition`` roles of the PREVENT_EFFECT atoms of a printed static (see
    ``mutants``) that nothing reads. layers._new_static registers each such atom as a
    PreventionRecord whose condition is the StaticAbility's own ``condition`` (Tome Anima's
    "as long as"), never the atom's: the atom's ``condition`` mirrors its event's filter in
    every corpus prevention shape, and the consumers (replacements.prevents_counter_placement,
    the attack, block and activation vetoes, prevents_countering) judge the record's condition
    and the event. The atom's ``condition`` has two readers: verbs._v_prevent, the resolved
    lane (a spell, activated or triggered prevention: live), and
    legality._own_targeting_restrictions, a static over a TargetingEvent (Enthralling Hold's
    "you can't choose ... as you cast it"), which stays out. ``_new_static`` strips one
    OptionalEffect and parses an Atom or a Seq of Atoms."""
    if not isinstance(ability, StaticAbility):
        return set()
    effect, path = ability.effect, (*base, "effect")
    if isinstance(effect, OptionalEffect):
        effect, path = effect.inner, (*path, "inner")
    steps = [(effect, path)] if isinstance(effect, Atom) else (
        [(s, (*path, "steps", j)) for j, s in enumerate(effect.steps)] if isinstance(effect, Seq) else [])
    return {(*p, "args", "condition") for s, p in steps
            if isinstance(s, Atom) and s.verb is Verb.PREVENT_EFFECT
            and not isinstance(s.args.get("event"), TargetingEvent)}


def _granted_policy_may(atom: Any) -> bool:
    """Is ``atom`` a GRANT_ABILITY of a static whose "you may" is the damage step's ask (see
    ``mutants``)? Garruk, Savage Herald's -7: creatures gain "You may have this creature assign
    its combat damage as though it weren't blocked." A granted static is never parsed as a layer
    (layers._apply_add files it in the granted map); the one reader of its body,
    layers.policy_as_unblocked, unwraps the OptionalEffect and the Seq, and the combat damage
    step asks the policy question of every creature that carries it (Executor, the
    ``policy:`` ask), wrapper or not. The other readers of granted entries take triggered or
    activated abilities or keyword rows; LOSE_ABILITY matches a granted node by repr and no
    card in the 19 sets loses a non-keyword ability."""
    if not (isinstance(atom, Atom) and atom.verb is Verb.GRANT_ABILITY):
        return False
    granted = atom.args.get("ability")
    if not (isinstance(granted, StaticAbility) and isinstance(granted.effect, OptionalEffect)):
        return False
    inner = granted.effect.inner
    steps = inner.steps if isinstance(inner, Seq) else (inner,)
    return all(isinstance(s, Atom) and s.verb is Verb.DAMAGE_ASSIGN_POLICY for s in steps)


# Zones a moving card always enters as its OWNER's (CR 400.3; selectors.move_destination).
_OWNER_ZONES = (ZoneKind.HAND, ZoneKind.LIBRARY, ZoneKind.GRAVEYARD, ZoneKind.EXILE)
# Static permissions whose "you may" is the use, not a layer gate: layers._new_static strips the
# OptionalEffect before it parses the payload (the MAY belongs to the USE side).
_PERMISSION_VERBS = (Verb.ADD_LAND_PLAY, Verb.MANA_POLICY, Verb.GRANT_ACTIVATION)


def _partition_step(step: Any) -> bool:
    """Executor._partition_step: a MOVE_ZONE whose cards selector is a ONE_OF/REST partition."""
    sel = step.args.get("cards") if isinstance(step, Atom) and step.verb is Verb.MOVE_ZONE else None
    return isinstance(sel, Selector) and sel.mode in (SelectorMode.ONE_OF, SelectorMode.REST)


def _draw_idiom(atom: Atom) -> bool:
    """MOVE_ZONE's top-n draw idiom (verbs.py _v_move_zone: "move THE top n of your library to
    hand"), the one move lane whose destination names a player: zone_owner picks whose library is
    drawn. The idiom is an unpartitioned, referent-free, unfiltered selector over one library.
    The partition is the executor's own (``partition`` there): a ONE_OF/REST pick, and an ALL over
    a library's top, which moves the looked-at cards as resolved, each to its owner's hand (See the
    Truth's "put all cards looked at this way into your hand"; verification wave 6 found its
    destination-controller mutant offered and surviving, BACKLOG G1)."""
    sel = atom.args.get("cards")
    dest = atom.args.get("destination")
    if not (atom.verb is Verb.MOVE_ZONE and isinstance(sel, Selector) and isinstance(dest, Zone)):
        return False
    partition = sel.mode in (SelectorMode.ONE_OF, SelectorMode.REST) or (
        sel.mode is SelectorMode.ALL
        and any(z.kind is ZoneKind.LIBRARY and z.position is ZonePosition.TOP for z in sel.zones))
    return (dest.kind is ZoneKind.HAND and not partition and sel.referent is None
            and len(sel.zones) == 1 and sel.zones[0].kind is ZoneKind.LIBRARY
            and isinstance(sel.filter, FAnd) and not sel.filter.children)


_FLIP = {ControllerRef.YOU: ControllerRef.OPPONENT, ControllerRef.OPPONENT: ControllerRef.YOU,
         ControllerRef.ALL_OPPONENTS: ControllerRef.YOU}
_ZONE_SWAP = {ZoneKind.GRAVEYARD: ZoneKind.EXILE, ZoneKind.EXILE: ZoneKind.GRAVEYARD,
              ZoneKind.HAND: ZoneKind.BATTLEFIELD, ZoneKind.BATTLEFIELD: ZoneKind.HAND,
              ZoneKind.LIBRARY: ZoneKind.GRAVEYARD}


def _without_unread_choices(keywords: tuple, abilities: tuple) -> tuple:
    """``abilities`` less every "As this enters, choose ..." node whose quality nothing in the
    card reads any more. A mutant that drops the last read ("creatures you control of the chosen
    type" widened to every creature you control) drops the choice with it, as the zone swap of an
    arranged move drops ``arrange``: the IR refuses a choice nothing reads
    (ability_tree.chosen_quality_fault), so the mutant would be stillborn and the fault untested.
    Only a node that does nothing but choose goes. The effect is tested before the node is
    compared with ``EtBState(effect=...)``: built with no effect, that node is refused (a no-op
    state), which made every mutant of a card entering tapped or with counters stillborn."""
    read = {n.string_value for _p, n in _paths((keywords, abilities))
            if isinstance(n, FAtom) and n.pred is FAtomPred.NAME_CHOSEN}
    return tuple(a for a in abilities if not (
        isinstance(a, EtBState) and isinstance(a.effect, Atom) and a.effect.verb is Verb.CHOOSE_NAME
        and a.effect.args.get("quality") not in read and a == EtBState(effect=a.effect)))


def mutants(card: CardRecord) -> Iterator[tuple[str, str, CardRecord]]:
    """(operator, where, mutant card) for every viable fault-model mutant of the card's tree."""
    root = (card.keywords, card.abilities)
    seen: set[str] = set()
    # A self-designation ("this creature": a selector whose filter is IS_SOURCE) picks exactly one
    # object whatever its count says, so mutating that count is an equivalent mutant: skip it.
    self_counts = {
        (*path, "count")
        for path, node in _paths(root)
        if isinstance(node, Selector) and _is_self(node.filter)
    }
    # More equivalent mutants (they can change nothing the engine does, so a survivor would block a
    # correct card): SEARCH's controller role is never read (the searched zone comes from the cards
    # selector, divergence D12); a cost victim is designated by the payment ask whatever its
    # selector's mode says (costs never target, D13); a cost reduction already as large as the
    # card's generic mana cannot reduce more.
    dead: set[tuple] = set()
    in_cost: set[tuple] = set()
    generic = sum(getattr(getattr(p, "amount", None), "value", 0) for p in (card.mana_cost.parts if card.mana_cost else ())
                  if type(p).__name__ == "CostManaGeneric")
    nodes = dict(_paths(root))

    def under(path: tuple, cls: type) -> bool:
        return any(isinstance(nodes.get(path[:k]), cls) for k in range(len(path)))

    for path, node in _paths(root):
        if isinstance(node, Atom) and node.verb is Verb.SEARCH:
            dead.add((*path, "args", "controller"))
        if isinstance(node, TokenSpec) and node in _verified_tokens():
            dead.add(path)  # a token byte-identical to one proven elsewhere (_verified_tokens)
        if isinstance(node, Cost):
            in_cost.add(path)
        if type(node).__name__ == "CostDeltaReduceGeneric" and isinstance(getattr(node, "amount", None), QConst) \
                and node.amount.value >= generic:
            dead.add((*path, "amount"))
        # Each rule below is proven in test_gates.py:
        # - the merged MOVE atom's mill shape (pop_order TOP) and discard shape (from HAND) move the
        #   cards of the `controller` role's player: `from` and `destination` are read for their
        #   kind only (verbs.py _v_move_zone), so their controller fields are dead;
        # - a REST partition is the complement of the ONE_OF pick, its count is never read
        #   (selectors.py REST branch, query.py "count ignored (like ALL)", verbs.py partition lane);
        # - a CHOOSE or ONE_OF over the one zone Zone(PLAYER, YOU) has one player to pick, so every
        #   count >= 1 picks that player (selectors.py CHOOSE branch, ``ordered[:k]``; the ONE_OF
        #   branch resolves k of n best effort and query.py gives ONE_OF no exact-count gate; a
        #   static's population is enumerate_candidates, which reads no count: FDN Crystal
        #   Barricade's "You have hexproof"). Cost selectors are left out.
        if isinstance(node, Atom) and node.verb is Verb.MOVE_ZONE and (
                node.args.get("pop_order") == "TOP"
                or getattr(node.args.get("from"), "kind", None) is ZoneKind.HAND):
            dead |= {(*path, "args", "from", "controller"), (*path, "args", "destination", "controller")}
        if isinstance(node, Selector) and node.referent is None and (
                node.mode is SelectorMode.REST
                or node.mode in (SelectorMode.CHOOSE, SelectorMode.ONE_OF) and len(node.zones) == 1
                and node.zones[0].kind is ZoneKind.PLAYER and node.zones[0].controller is ControllerRef.YOU
                and not any(path[: len(c)] == c for c in in_cost)):
            dead.add((*path, "count"))
        # - a ONE_OF partition after the one SEARCH of its Seq picks among the cards that search
        #   found (Executor._run_effect's search_partition, selectors.resolve_selector's
        #   search_found lane; a library-TOP zone reads a look window instead): after a search for
        #   one card it has one card at most, so every count >= 1 picks it (FDN Campus Guide's
        #   "put that card on top").
        if isinstance(node, Seq) and any(_partition_step(step) for step in node.steps):
            searches = [i for i, step in enumerate(node.steps)
                        if isinstance(step, Atom) and step.verb is Verb.SEARCH]
            if len(searches) == 1 and node.steps[searches[0]].args.get("cards").count == QConst(1):
                dead |= {(*path, "steps", i, "args", "cards", "count")
                         for i, step in enumerate(node.steps) if i > searches[0] and _partition_step(step)
                         and (sel := step.args.get("cards")).mode is SelectorMode.ONE_OF and sel.referent is None
                         and not any(z.kind is ZoneKind.LIBRARY and z.position is ZonePosition.TOP
                                     for z in sel.zones)}
        # Proven in test_gates.py like the above:
        # - SEARCH and MOVE_ZONE put a card into its OWNER's hand, library, graveyard or exile,
        #   whatever player the destination names (CR 400.3; selectors.move_destination):
        #   only a battlefield destination names a player. MOVE_ZONE's top-n draw idiom reads it
        #   (zone_owner picks whose library is drawn) and is left out;
        # - a discard takes its CHOOSE/RANDOM/ALL picks from the discarding players' own hands,
        #   reading the cards selector's filter, mode and count only (verbs.py _hand_picks): its
        #   zones are dead, unless a "you may" above it enumerates them for its offer
        #   (query.optional_offer);
        # - a damage replacement whose action is a DEAL_DAMAGE rewrites the event's amount and never
        #   runs the action (replacements.replacements_for_damage): the action's dealer is dead.
        if isinstance(node, Atom) and node.verb in (Verb.SEARCH, Verb.MOVE_ZONE):
            dest = node.args.get("destination")
            if isinstance(dest, Zone) and dest.kind in _OWNER_ZONES and not _draw_idiom(node):
                dead.add((*path, "args", "destination", "controller"))
        if isinstance(node, Atom) and node.verb is Verb.MOVE_ZONE and node.args.get("pop_order") != "TOP" \
                and getattr(node.args.get("from"), "kind", None) is ZoneKind.HAND and not under(path, OptionalEffect):
            sel = node.args.get("cards")
            if isinstance(sel, Selector) and sel.referent is None \
                    and sel.mode in (SelectorMode.CHOOSE, SelectorMode.RANDOM, SelectorMode.ALL):
                dead |= {(*path, "args", "cards", "zones", i, "controller") for i in range(len(sel.zones))}
        if isinstance(node, ReplacementAbility) and isinstance(node.event, DamageDealtEvent) \
                and isinstance(node.action, Atom) and node.action.verb is Verb.DEAL_DAMAGE:
            dead.add((*path, "action", "args", "dealer"))
        # A Seq with a ONE_OF/REST partition MOVE_ZONE among its
        # direct steps runs its SEARCH steps designate-only (ctx.search_partition, set by the same
        # shallow scan in Executor._run_effect and the guarded lane; verbs._v_search returns before
        # moving anything): such a SEARCH's destination is a compile-time placeholder, never used.
        if isinstance(node, Seq) and any(_partition_step(step) for step in node.steps):
            dead |= {(*path, "steps", i, "args", "destination") for i, step in enumerate(node.steps)
                     if isinstance(step, Atom) and step.verb is Verb.SEARCH}
    # Ability-level rules (their docstrings carry the argument): a REVEAL nothing reads; a TARGET
    # selector whose twin keeps the one designation slot (role_handles gives a referent-free ALL
    # selector in the bound role the designation itself); an end-step trigger whose condition
    # already requires your turn; the condition of a printed static's PREVENT_EFFECT; a static's
    # own look or reveal (a disclosure record nothing reads); the count of a pick from the one
    # card on top of or under a library.
    twins: set[tuple] = set()
    scope_fixed = {(1, i, "event") for i, ability in enumerate(card.abilities) if _scope_fixed_by_condition(ability)}
    # A static permission's "you may" is stripped before its payload is parsed (layers._new_static),
    # and nothing else reads a static's top-level OptionalEffect: optional->mandatory is dead there.
    # A granted damage-policy static's "you may" is the damage step's ask (_granted_policy_may).
    permissions = {(1, i, "effect") for i, ability in enumerate(card.abilities)
                   if isinstance(ability, StaticAbility) and isinstance(ability.effect, OptionalEffect)
                   and isinstance(ability.effect.inner, Atom) and ability.effect.inner.verb in _PERMISSION_VERBS}
    permissions |= {(*path, "args", "ability", "effect") for path, node in _paths(root) if _granted_policy_may(node)}
    one_card: set[tuple] = set()  # moves of a one-card look's result: no library order (_one_card_result_moves)
    for i, ability in enumerate(card.abilities):
        twins |= _twin_targets(ability, (1, i))
        one_card |= _one_card_result_moves(ability, (1, i))
        dead |= _static_prevention_conditions(ability, (1, i))
        dead |= _static_disclosures(ability, (1, i))
        dead |= _one_card_picks(ability, (1, i))
        roles = _reveal_dead_roles(ability)
        for path, node in _paths(ability, (1, i)):
            if isinstance(node, Atom) and node.verb is Verb.REVEAL:
                # a reveal of named cards opens no window, and its row is read by nothing that
                # plays (_reveal_dead_roles): a scaffold until memory reads the rows (BACKLOG)
                dead |= ({(*path, "args", "cards")} if node.args.get("cards") is not None
                         else {(*path, "args", role) for role in roles})
    for path, node in _paths(root):
        cands: list[tuple[str, Any]] = []
        at = path  # where the candidates are rebuilt; the zone swap of an arranged move rebuilds the move
        if isinstance(node, QConst) and path in self_counts:
            continue
        if path in dead or any(path[: len(d)] == d for d in dead):
            continue
        if isinstance(node, Selector) and any(path[: len(c)] == c for c in in_cost):
            continue  # cost victims: the payment ask designates them, mode is not a cost axis
        if isinstance(node, TurnPhaseEvent):
            if node.actor is None:
                cands.append(("trigger scope: each turn -> your turn only", dataclasses.replace(node, actor=_ACTOR_YOU)))
            elif path not in scope_fixed:
                cands.append(("trigger scope: your turn -> each turn", dataclasses.replace(node, actor=None)))
        elif isinstance(node, DelayedTrigger) and node.reflexive:
            # "When you do" written as "If you do": the effect in this resolution, its targets
            # chosen with the ability's own (Sorin, Imperious Bloodlord's first mapping, CR 603.12).
            cands.append(("trigger timing: when you do -> if you do", node.effect))
        elif isinstance(node, (TriggeredAbility, DelayedTrigger)) and node.once_per_event:
            cands.append(("trigger count: once per event -> each occurrence",
                          dataclasses.replace(node, once_per_event=None)))
        elif isinstance(node, (TriggeredAbility, DelayedTrigger)) and gathers_occurrences(node.event):
            try:
                cands.append(("each occurrence -> once per event", dataclasses.replace(node, once_per_event=True)))
            except ValueError:
                pass  # stillborn: the effect reads one object of the event ("its power")
        elif isinstance(node, AbilityTriggerEvent) and node.cause is not None:
            # Yarok's "a permanent entering causes" dropped doubles every trigger of yours (gate
            # round W3, MINOR-6); Naban's Wizard widened to any permanent
            cands.append(("extra-trigger cause dropped", dataclasses.replace(node, cause=None)))
            if node.cause.subject is not None:
                cands.append(("extra-trigger cause widened",
                              dataclasses.replace(node, cause=dataclasses.replace(node.cause, subject=None))))
        elif isinstance(node, Atom) and orders_a_library(node) and path not in one_card:
            # CR 401.4: the owner arranges the cards, unless "in a random order" (arrange RANDOM)
            pairs = tuple(p for p in node.args.pairs if p[0] != "arrange")
            if len(pairs) < len(node.args.pairs):
                cands.append(("library order: random -> the owner's", Atom(node.verb, AtomArgs(pairs))))
            else:
                cands.append(("library order: the owner's -> random",
                              Atom(node.verb, AtomArgs((*pairs, ("arrange", "RANDOM"))))))
        elif isinstance(node, QConst):
            cands.append(("amount+1", QConst(node.value + 1)))
            if node.value > 1:
                cands.append(("amount-1", QConst(node.value - 1)))
        elif isinstance(node, DurationEot):
            cands.append(("until-end-of-turn->permanent", DurationPermanent()))
        elif isinstance(node, DurationPermanent):
            cands.append(("permanent->until-end-of-turn", DurationEot()))
        elif isinstance(node, ControllerRef) and node in _FLIP:
            cands.append((f"controller {node.name}->{_FLIP[node].name}", _FLIP[node]))
        elif isinstance(node, Zone) and node.kind in _ZONE_SWAP and path and path[-1] == "destination":
            other = dataclasses.replace(node, kind=_ZONE_SWAP[node.kind])
            move = nodes.get(path[:-2])
            if isinstance(move, Atom) and move.args.get("arrange") is not None:
                # "in a random order" orders only cards that go into a library (orders_a_library):
                # moving them elsewhere drops the order with it, or the mutant would be stillborn
                at = path[:-2]
                other = Atom(move.verb, AtomArgs(tuple(
                    (r, other if r == "destination" else v) for r, v in move.args.pairs if r != "arrange")))
            cands.append((f"zone {node.kind.name}->{_ZONE_SWAP[node.kind].name}", other))
        elif isinstance(node, FAtom) and node.pred is FAtomPred.QTY_GE and (
                node.who is not None or _measure_plus_one(node.count) is not None):
            # The comparison's two likely mapping errors (ontology round R12): "an opponent has N"
            # read as "you have N" (`who` dropped: an opponent's zone and `who` YOU are refused,
            # so no flip reaches it), and "more than" read as "at least as many" (the + 1 dropped
            # from a measured threshold, which amount-1 cannot reach: N + 0 is refused).
            if node.who is not None:
                cands.append((f"controller who {node.who.name}->none (your own zone)",
                              dataclasses.replace(node, who=None)))
            bare = _measure_plus_one(node.count)
            if bare is not None:
                cands.append(("amount: more than -> at least as many", dataclasses.replace(node, count=bare)))
        elif isinstance(node, Selector) and node.mode is SelectorMode.TARGET and path not in twins:
            cands.append(("target->all", dataclasses.replace(node, mode=SelectorMode.ALL, count=QUnbounded())))
        elif isinstance(node, Seq) and len(node.steps) >= 2:
            for i in range(len(node.steps)):
                rest = node.steps[:i] + node.steps[i + 1:]
                cands.append((f"drop step {i}", rest[0] if len(rest) == 1 else Seq(steps=rest)))
        elif isinstance(node, OptionalEffect) and path not in permissions:
            cands.append(("optional->mandatory", node.inner))
        elif isinstance(node, FAnd) and len(node.children) >= 2:
            for i in range(len(node.children)):
                cands.append((f"widen filter (drop part {i})", FAnd(children=node.children[:i] + node.children[i + 1:])))
        elif isinstance(node, Cost) and node.parts and path and path[-1] != "mana_cost":
            for i in range(len(node.parts)):
                cands.append((f"drop cost part {i} ({type(node.parts[i]).__name__})",
                              Cost(parts=node.parts[:i] + node.parts[i + 1:])))
        elif isinstance(node, tuple) and path == (0,) and node:
            for i in range(len(node)):
                cands.append((f"drop keyword {node[i].keyword.name}", node[:i] + node[i + 1:]))
        for op, new in cands:
            try:
                kws, abilities = _rebuild(root, at, new)
                mutant = dataclasses.replace(card, keywords=kws,
                                             abilities=_without_unread_choices(kws, abilities))
            except (ValueError, TypeError, AttributeError):
                continue  # stillborn: the IR's own validation refuses it
            key = repr(mutant)
            if key in seen or mutant == card:
                continue
            seen.add(key)
            yield op, "/".join(str(p) for p in path), mutant


def _measure_plus_one(count: Any) -> Any:
    """The measure of a "more than <measure>" threshold (QBin(ADD, <measure>, 1)), or None."""
    if isinstance(count, QBin) and count.op is QBinOp.ADD and count.right == QConst(1) \
            and not isinstance(count.left, QConst):
        return count.left
    return None


@contextmanager
def swapped(supply: Any, oid: str, card: CardRecord) -> Generator[None]:
    """The supply with ``card`` as the tree of ``oid``, restored afterwards."""
    old = supply.pool.results[oid]
    supply.pool.results[oid] = CompileResult(card=card, legality=LegalityFlags(True, True), record="mutant")
    old_card = supply.pool.cards.get(oid)
    supply.pool.cards[oid] = card
    try:
        yield
    finally:
        supply.pool.results[oid] = old
        if old_card is not None:
            supply.pool.cards[oid] = old_card


def g3(supply: Any, set_code: str, oid: str, limit: int = 80) -> dict[str, Any]:
    """Mutation analysis: which fault-model mutants the probe trace cannot tell from the card."""
    base = Probe(supply, set_code, oid).report()
    card = supply.pool.results[oid].card
    killed, survived, errored = [], [], []
    for n, (op, where, mutant) in enumerate(mutants(card)):
        if n >= limit:
            break
        with swapped(supply, oid, mutant):
            try:
                rep = Probe(supply, set_code, oid).report()
            except Exception as exc:  # noqa: BLE001 — a mutant the probe cannot even run is killed
                errored.append((op, where, f"{type(exc).__name__}: {exc}"[:120]))
                continue
        (killed if rep.sha() != base.sha() else survived).append((op, where))
    total = len(killed) + len(survived) + len(errored)
    return {"base_sha": base.sha(), "mutants": total, "killed": len(killed) + len(errored),
            "survived": survived, "score": (len(killed) + len(errored)) / total if total else None}


def is_critical(op: str) -> bool:
    """Survivors of these operators block verification (gate G3): they are the abusable faults."""
    return op.startswith(("amount", "until-end", "permanent->", "controller", "zone", "drop cost",
                          "target->all", "optional", "trigger scope", "trigger count", "each occurrence",
                          "library order", "trigger timing"))

