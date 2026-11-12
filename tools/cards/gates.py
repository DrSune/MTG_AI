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

from probe import Probe

from MTG_bot.core.ability_tree import (
    DESIGNATED_PLAYER_REFS,
    Ability,
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
    FAnd,
    FAtom,
    FAtomPred,
    Keyword,
    KeywordAbility,
    OptionalEffect,
    Phase,
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
from MTG_bot.core.executor.query import _player_widening_applies
from MTG_bot.core.identity import LegalityFlags

_NUM_WORDS = {w: i for i, w in enumerate(
    ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"))}

# CR 207.2c: ability words have no rules meaning, so a tree has nothing to show for them (the
# ability itself is checked like any other clause). MTGJSON lists them with the keywords, and the
# Keyword enum carries one (BATTALION); spelled as G0 normalises MTGJSON keywords.
ABILITY_WORDS = frozenset(w.upper().replace(" ", "_") for w in (
    "adamant", "addendum", "alliance", "battalion", "bloodrush", "celebration", "channel", "chroma",
    "cohort", "constellation", "converge", "council's dilemma", "coven", "delirium", "descend 4",
    "descend 8", "domain", "eerie", "eminence", "enrage", "fateful hour", "fathomless descent",
    "ferocious", "flurry", "formidable", "grandeur", "hellbent", "hero's reward", "heroic", "imprint",
    "inspired", "join forces", "kinship", "landfall", "lieutenant", "magecraft", "metalcraft",
    "morbid", "pack tactics", "paradox", "parley", "radiance", "raid", "rally", "revolt",
    "secret council", "spell mastery", "strive", "survival", "sweep", "tempting offer", "threshold",
    "underdog", "undergrowth", "valiant", "will of the council"))


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
    # Keyword actions the compiler writes as their verb (scry, mill, fight exist as both a Verb and
    # a Keyword): the verb in the tree satisfies the printed keyword.
    tree_kw |= {n.verb.name for n in walk(card) if isinstance(n, Atom)}
    # ... or as the merged MOVE atom, whose journal_kind slot names the keyword action it
    # performs: the mill shape writes "MILL" (verbs.py _v_move_zone), so it satisfies "Mill".
    tree_kw |= {str(n.args.get("journal_kind")) for n in walk(card)
                if isinstance(n, Atom) and n.verb is Verb.MOVE_ZONE} & set(Keyword.__members__)
    unknown = sorted(k for k in printed_kw - tree_kw if k in Keyword.__members__)
    if unknown:
        fails.append(f"MTGJSON keywords missing from the tree: {unknown}")
    absent = sorted(k for k in printed_kw - tree_kw if k not in Keyword.__members__)
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
    if clauses is not None:
        covered = " ".join(c.get("clause", "") for c in clauses)
        for sentence in raw.sentences:
            core = re.sub(r"\s*\([^)]*\)", "", sentence).strip()
            if core and core not in covered:
                fails.append(f"clause not traced to the tree: {core!r}")
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
    """Token specs on the M21 golden trees (the BUGCATCH-verified pool): a card creating a
    byte-identical token (a Treasure, a Soldier) need not re-prove the token's own abilities."""
    if not _TOKENS:
        from MTG_bot.core.compiler.compiler import compile_pool
        from MTG_bot.core.compiler.coverage import build_full_registry
        from MTG_bot.core.compiler.ingest import ingest_pool

        pool = compile_pool(ingest_pool(HERE.parents[1] / "MTG_bot" / "data" / "M21.json"),
                            build_full_registry())
        seen: list[TokenSpec] = []
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
    """The REVEAL roles of ``ability`` no game state can observe (see ``mutants``): REVEAL is a
    recorded no-op (verbs.py ``_look``: it moves nothing, the journal has no row for it, the seat
    view tracks no revealed card). Its only outputs are the look window, read by a Conditional
    right after it, a ONE_OF/REST partition over the library top or a REVEAL right after it, and
    the ``result`` register, read by a ``referent="result"`` node, THAT_MANY_COUNT or FIGHT's
    attacker. With none of those in the ability, controller and count are dead. A Conditional
    judges the window's first card, the top card for any count >= 1, so it leaves count dead.
    Several REVEALs qualify when each sits in its own option of one "choose one" (a count-1
    Choose: the executor runs exactly one option, so at most one REVEAL runs; query.choose_options
    reads no option's contents), the "search your library and/or graveyard" zone choice."""
    if not isinstance(ability, (TriggeredAbility, ActivatedAbility, SpellAbility)):
        return set()
    nodes = list(walk(ability))
    looks = [n for n in nodes if isinstance(n, Atom) and n.verb in (Verb.REVEAL, Verb.LOOK_AT)]
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


def _window_reveal(ability: Any) -> Atom | None:
    """The REVEAL of "look at N cards ... you may reveal one from among them" whose controller and
    count no game state can observe (see ``mutants``), or None. It runs right after the ability's
    one LOOK_AT, so ``_look`` takes its prior-window branch whenever that window holds a card:
    the controller is not read, the count only slices the window, the window is kept and nothing
    is written to ``result``. The window is empty only when the LOOK_AT's library is: its count
    is a constant >= 1 or a damage trigger's AMOUNT (no damage event deals 0, CR 120.8). Then the
    mutant reveals another library's cards, which no reader here can see: no Conditional, no
    ``result`` reader and only partitions over your own library top, which drop cards not in it.
    Both look atoms name you, and no mode or condition reorders the atoms."""
    if not isinstance(ability, (TriggeredAbility, ActivatedAbility, SpellAbility)):
        return None
    nodes = list(walk(ability))
    atoms = [n for n in nodes if isinstance(n, Atom)]
    looks = [n for n in atoms if n.verb in (Verb.REVEAL, Verb.LOOK_AT)]
    if len(looks) != 2 or looks[0].verb is not Verb.LOOK_AT or looks[1].verb is not Verb.REVEAL:
        return None
    look, reveal = looks
    if atoms.index(reveal) != atoms.index(look) + 1 or any(a.args.get("duration") is not None for a in looks):
        return None
    if any(a.args.get("controller") is not ControllerRef.YOU for a in looks):
        return None
    if not (isinstance(reveal.args.get("count"), QConst) and reveal.args.get("count").value >= 1):
        return None
    count = look.args.get("count")
    damage_amount = (isinstance(count, QProp) and count.referent == "event" and count.field is QPropField.AMOUNT
                     and isinstance(ability, TriggeredAbility) and isinstance(ability.event, DamageDealtEvent))
    if not (isinstance(count, QConst) and count.value >= 1) and not damage_amount:
        return None
    for n in nodes:
        if isinstance(n, (Conditional, Choose)) or getattr(n, "referent", None) == "result" or (
                isinstance(n, QProp) and n.field is QPropField.THAT_MANY_COUNT) or (
                isinstance(n, Atom) and n.verb is Verb.FIGHT):
            return None
        if isinstance(n, Selector) and n.mode in (SelectorMode.ONE_OF, SelectorMode.REST) and any(
                z.kind is ZoneKind.LIBRARY and z.position is ZonePosition.TOP and z.controller is not ControllerRef.YOU
                for z in n.zones):
            return None
    return reveal


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
    - Activated abilities stay out: ``activate`` validates no targets."""
    if isinstance(ability, SpellAbility):
        if isinstance(ability.effect, Choose):
            return set()  # a modal spell
    elif not isinstance(ability, TriggeredAbility):
        return set()
    found = list(_paths(ability, base))
    nodes = dict(found)
    sels = [(p, n) for p, n in found if isinstance(n, Selector) and n.mode is SelectorMode.TARGET]
    if len(sels) < 2 or any(n != sels[0][1] for _, n in sels) or any(p[-2:] != ("args", "target") for p, _ in sels):
        return set()
    if any(isinstance(n, ControllerRef) and n in DESIGNATED_PLAYER_REFS for _, n in found):
        return set()
    blocked: tuple[type, ...] = (*_ABILITY_TYPES, DelayedTrigger, TokenSpec)
    if isinstance(ability, TriggeredAbility):
        blocked = (*blocked, Choose)
    if any(isinstance(nodes.get(p[:k]), blocked) for p, _ in sels for k in range(len(base) + 1, len(p))):
        return set()
    sel = sels[0][1]
    if not (isinstance(sel.count, QConst) and sel.count.value >= 1) or sel.referent is not None \
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
    drawn. The idiom is an unpartitioned, referent-free, unfiltered selector over one library."""
    sel = atom.args.get("cards")
    dest = atom.args.get("destination")
    return (atom.verb is Verb.MOVE_ZONE and isinstance(sel, Selector) and isinstance(dest, Zone)
            and dest.kind is ZoneKind.HAND
            and sel.mode not in (SelectorMode.ONE_OF, SelectorMode.REST) and sel.referent is None
            and len(sel.zones) == 1 and sel.zones[0].kind is ZoneKind.LIBRARY
            and isinstance(sel.filter, FAnd) and not sel.filter.children)


_FLIP = {ControllerRef.YOU: ControllerRef.OPPONENT, ControllerRef.OPPONENT: ControllerRef.YOU,
         ControllerRef.ALL_OPPONENTS: ControllerRef.YOU}
_ZONE_SWAP = {ZoneKind.GRAVEYARD: ZoneKind.EXILE, ZoneKind.EXILE: ZoneKind.GRAVEYARD,
              ZoneKind.HAND: ZoneKind.BATTLEFIELD, ZoneKind.BATTLEFIELD: ZoneKind.HAND,
              ZoneKind.LIBRARY: ZoneKind.GRAVEYARD}


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
            dead.add(path)  # a token byte-identical to one the M21 goldens verify: proven there
        if isinstance(node, Cost):
            in_cost.add(path)
        if type(node).__name__ == "CostDeltaReduceGeneric" and isinstance(getattr(node, "amount", None), QConst) \
                and node.amount.value >= generic:
            dead.add((*path, "amount"))
        # Each rule below is proven in test_gates.py:
        # - the merged MOVE atom's mill shape (pop_order TOP) and discard shape (from HAND) move the
        #   cards of the `controller` role's player: `from` and `destination` are read for their
        #   kind only (verbs.py _v_move_zone), so their controller fields are dead;
        # - ZONE_COUNT_GE counts the zone of its `who` players; the zone's controller is never read
        #   (quantity.py, ZONE_COUNT_GE: "reading WHO is the whole answer");
        # - a REST partition is the complement of the ONE_OF pick, its count is never read
        #   (selectors.py REST branch, query.py "count ignored (like ALL)", verbs.py partition lane);
        # - a CHOOSE over the one zone Zone(PLAYER, YOU) has one player to pick, so every count >= 1
        #   picks that player (selectors.py CHOOSE branch, ``ordered[:k]``; a static's population is
        #   enumerate_candidates, which reads no count). Cost selectors are left out.
        if isinstance(node, Atom) and node.verb is Verb.MOVE_ZONE and (
                node.args.get("pop_order") == "TOP"
                or getattr(node.args.get("from"), "kind", None) is ZoneKind.HAND):
            dead |= {(*path, "args", "from", "controller"), (*path, "args", "destination", "controller")}
        if isinstance(node, FAtom) and node.pred is FAtomPred.ZONE_COUNT_GE:
            dead.add((*path, "zone", "controller"))
        if isinstance(node, Selector) and node.referent is None and (
                node.mode is SelectorMode.REST
                or node.mode is SelectorMode.CHOOSE and len(node.zones) == 1
                and node.zones[0].kind is ZoneKind.PLAYER and node.zones[0].controller is ControllerRef.YOU
                and not any(path[: len(c)] == c for c in in_cost)):
            dead.add((*path, "count"))
        # Proven in test_gates.py like the above:
        # - SEARCH and MOVE_ZONE put a card into its OWNER's hand, library, graveyard or exile,
        #   whatever player the destination names (CR 400.3; selectors.move_destination):
        #   only a battlefield destination names a player. MOVE_ZONE's top-n draw idiom reads it
        #   (zone_owner picks whose library is drawn) and is left out;
        # - a discard takes its CHOOSE/RANDOM/ALL picks from the discarding players' own hands,
        #   reading the cards selector's filter, mode and count only (verbs.py _discard_picks): its
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
    # already requires your turn; the condition of a printed static's PREVENT_EFFECT.
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
        roles = _reveal_dead_roles(ability)
        for path, node in _paths(ability, (1, i)) if roles else ():
            if isinstance(node, Atom) and node.verb is Verb.REVEAL:
                dead |= {(*path, "args", role) for role in roles}
        window_reveal = _window_reveal(ability)
        for path, node in _paths(ability, (1, i)) if window_reveal is not None else ():
            if node is window_reveal:
                dead |= {(*path, "args", "controller"), (*path, "args", "count")}
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
            cands.append(("each occurrence -> once per event", dataclasses.replace(node, once_per_event=True)))
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
                mutant = dataclasses.replace(card, keywords=kws, abilities=abilities)
            except (ValueError, TypeError, AttributeError):
                continue  # stillborn: the IR's own validation refuses it
            key = repr(mutant)
            if key in seen or mutant == card:
                continue
            seen.add(key)
            yield op, "/".join(str(p) for p in path), mutant


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

