"""Reachability census for the open engine faults (KNOWLEDGE/2026-11-18/215).

Walks the compiled trees of the three deal pools (M21, M20 and FDN, `verified` mode: what a
training game deals, one set per game) and, for context, of every ingested set (`all` mode), and
reports for each fault shape the cards that hold it. A fault is reachable in a pool only through
cards of ONE set (a game deals one set: tools/selfplay/learner.py `job["set_code"]`).

    census.py <checkout> <out.txt> [--all-sets]

CPU only; run it niced. Every detector names the fault id of 215's table.
"""
from __future__ import annotations

import dataclasses
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402
from MTG_bot.core.executor import games  # noqa: E402

POOLS = ("M21", "M20", "FDN")
ALL_SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI",
            "M19", "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
# The copy round's cards (209 B3: round 14, COPY_PERM and COPY_SPELL), about to be verified.
B3 = {"M21": ("Double Vision", "Sublime Epiphany"),
      "M20": ("Chandra's Regulator", "Masterful Replication"),
      "FDN": ("Abyssal Harvester", "Electroduplicate", "Extravagant Replication", "Homunculus Horde",
              "Rite of Replication", "Self-Reflection", "Thousand-Year Storm")}
ABILITY_KINDS = ("TriggeredAbility", "ActivatedAbility", "StaticAbility", "SpellAbility",
                 "ReplacementAbility", "EtBState", "DelayedTrigger", "KeywordAbility")


def walk(node, path=()):
    """(path, node) for every dataclass node; path = tuple of (class name, field) pairs, an
    AtomArgs role as ("role", name)."""
    yield path, node
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        for f in dataclasses.fields(node):
            yield from _value(getattr(node, f.name), path + ((type(node).__name__, f.name),))


def _value(v, path):
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        yield from walk(v, path)
    elif isinstance(v, (tuple, frozenset, list)):
        for item in v:
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str):
                yield from _value(item[1], path + (("role", item[0]),))  # an AtomArgs pair
            else:
                yield from _value(item, path)


def outer(path) -> str:
    """The innermost ability kind holding the node (a granted ability inside an effect counts)."""
    return next((c for c, _f in reversed(path) if c in ABILITY_KINDS or c in ("TokenSpec", "EmblemSpec")), "?")


def in_token(path) -> bool:
    return any(c == "TokenSpec" for c, _f in path)


def role_of(path) -> str | None:
    return next((f for c, f in reversed(path) if c == "role"), None)


def is_source_sel(sel) -> bool:
    return isinstance(sel, at.Selector) and (
        sel.referent == "source"
        or sel.referent is None and isinstance(sel.filter, at.FAtom) and sel.filter.pred is at.FAtomPred.IS_SOURCE)


def zones_of(sel) -> set:
    return {z.kind for z in sel.zones} if isinstance(sel, at.Selector) else set()


def atoms(node):
    for path, n in walk(node):
        if isinstance(n, at.Atom):
            yield path, n


def own_atoms(effect):
    """The atoms of one effect, not of abilities granted inside it."""
    for path, n in walk(effect):
        if isinstance(n, at.Atom) and not any(c in ("GRANT", "TokenSpec", "EmblemSpec") for c, _ in path):
            if not any(f == "ability" for c, f in path if c == "role"):
                yield path, n


def selectors(node):
    for path, n in walk(node):
        if isinstance(n, at.Selector):
            yield path, n


DETECTORS = []


def detector(fid: str, what: str):
    def wrap(fn):
        DETECTORS.append((fid, what, fn))
        return fn
    return wrap


# --- F14: an ability whose source left and came back still acts on it -------------------------
@detector("F14 carriers", "an activated or triggered ability's verb (not PUT_COUNTER) acting on its own source")
def acts_on_source(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and outer(path) in ("TriggeredAbility", "ActivatedAbility", "DelayedTrigger") \
                and n.verb is not at.Verb.PUT_COUNTER and not in_token(path):
            for role, val in n.args.pairs:
                if is_source_sel(val):
                    yield f"{outer(path)} {n.verb.name}.{role}"


@detector("F14 enablers", "returns a permanent card to the battlefield from a graveyard, exile or a hand")
def returns_to_battlefield(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb is at.Verb.MOVE_ZONE:
            d = n.args.get("destination")
            if isinstance(d, at.Zone) and d.kind is at.ZoneKind.BATTLEFIELD:
                for role in ("cards", "target"):
                    sel = n.args.get(role)
                    if sel is None:
                        continue
                    zs = zones_of(sel)
                    ref = getattr(sel, "referent", None)
                    if zs & {at.ZoneKind.GRAVEYARD, at.ZoneKind.EXILE, at.ZoneKind.HAND} or ref is not None:
                        yield (f"{outer(path)} {role}: zones={sorted(z.name for z in zs)} ref={ref}"
                               f" duration={type(n.args.get('duration')).__name__}")


@detector("F14b carriers", "reads a chosen quality (NAME_CHOSEN) in an activated or triggered ability")
def reads_choice(card):
    for path, n in walk(card):
        if isinstance(n, at.FAtom) and n.pred is at.FAtomPred.NAME_CHOSEN \
                and outer(path) in ("TriggeredAbility", "ActivatedAbility"):
            yield f"{outer(path)}"


# --- F01: a target-player slot with no legal player ----------------------------------------
@detector("F01", "a trigger designates 'target opponent/player' (a player slot)")
def target_player_trigger(card):
    for path, n in walk(card):
        if outer(path) not in ("TriggeredAbility", "DelayedTrigger") or in_token(path):
            continue
        if isinstance(n, at.Selector) and n.mode is at.SelectorMode.TARGET and at.ZoneKind.PLAYER in zones_of(n):
            yield f"{outer(path)} selector zones={[(z.kind.name, z.controller.name) for z in n.zones]}"
        if isinstance(n, at.ControllerRef) and n in (at.ControllerRef.TARGET_PLAYER, at.ControllerRef.TARGET_OPPONENT):
            yield f"{outer(path)} {n.name} in {role_of(path)}"


@detector("F01h", "gives a player hexproof or protection (a target-player slot can lose every candidate)")
def player_hexproof(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb is at.Verb.GRANT_ABILITY:
            t = n.args.get("target")
            if isinstance(t, at.Selector) and at.ZoneKind.PLAYER in zones_of(t):
                yield f"{outer(path)} GRANT_ABILITY to a player"
        if isinstance(n, at.Atom) and n.verb is at.Verb.PREVENT_EFFECT and outer(path) == "StaticAbility":
            ev = n.args.get("event")
            if isinstance(ev, at.TargetingEvent):
                yield f"StaticAbility PREVENT targeting: {repr(ev)[:90]}"


# --- F04: Verb.DISCARD has no handler ------------------------------------------------------
@detector("F04", "Verb.DISCARD (no executor handler)")
def verb_discard(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb is at.Verb.DISCARD:
            yield outer(path)


# --- F05: the b5b put-counter template places +1/+1 counters whatever the card prints ---------
@detector("F05", "PUT_COUNTER of a kind other than +1/+1 (a misprint would show here)")
def counter_kinds(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb is at.Verb.PUT_COUNTER:
            yield n.args.get("counter_kind").name


# --- F10: once-per-event triggers and dealer triggers ---------------------------------------
@detector("F10a", "a once-per-event trigger (its event kind)")
def once_per_event(card):
    for path, n in walk(card):
        if isinstance(n, (at.TriggeredAbility, at.DelayedTrigger)) and n.once_per_event:
            yield type(n.event).__name__


@detector("F10d", "a damage trigger naming a dealer and no recipient (split by trample or blockers)")
def dealer_no_recipient(card):
    for path, n in walk(card):
        if isinstance(n, (at.TriggeredAbility, at.DelayedTrigger)) and isinstance(n.event, at.DamageDealtEvent):
            ev = n.event
            universal = isinstance(ev.filter, at.FAnd) and not ev.filter.children
            if ev.source is not None and universal:
                yield f"combat={ev.combat} source={repr(ev.source)[:80]}"


# --- F11: a blocker of several attackers --------------------------------------------------
@detector("F11", "a creature can block more than one attacker")
def multi_block(card):
    for path, n in walk(card):
        if isinstance(n, at.KeywordAbility) and "BLOCK" in n.keyword.name:
            yield n.keyword.name
        if isinstance(n, at.FAtom) and "BLOCK_ADDITIONAL" in n.pred.name:
            yield n.pred.name


# --- F16: two "target" words with the same text --------------------------------------------
@detector("F16", "two TARGET selectors with the same bytes in one ability (one slot, CR 601.2c)")
def twin_targets(card):
    for ab in card.abilities:
        reprs = defaultdict(int)
        for path, n in walk(ab):
            if isinstance(n, at.Selector) and n.mode is at.SelectorMode.TARGET and not in_token(path):
                reprs[repr(n)] += 1
        for r, k in reprs.items():
            if k > 1:
                yield f"{type(ab).__name__} x{k}: {r[:100]}"


# --- F17: an activation with an X cost and a target ---------------------------------------
@detector("F17", "an activated ability with X in its cost and a TARGET (X announced after targets)")
def x_and_target(card):
    for ab in card.abilities:
        if isinstance(ab, at.ActivatedAbility):
            has_x = any(isinstance(n, at.QX) for _p, n in walk(ab.cost))
            has_t = any(isinstance(n, at.Selector) and n.mode is at.SelectorMode.TARGET for _p, n in walk(ab.effect))
            if has_x and has_t:
                yield "ActivatedAbility"


# --- F18: multi-slot triggers ---------------------------------------------------------------
@detector("F18", "a trigger with two or more designations (multi-slot)")
def multi_slot_trigger(card):
    for path, n in walk(card):
        if isinstance(n, (at.TriggeredAbility, at.DelayedTrigger)):
            sels = {repr(s) for _p, s in walk(n.effect) if isinstance(s, at.Selector) and s.mode is at.SelectorMode.TARGET}
            if len(sels) > 1:
                has_choose = any(isinstance(x, at.Choose) for _p, x in walk(n.effect))
                yield f"{len(sels)} slots choose={has_choose}"


# --- F20: an EachPlayer body of two instructions, or with a choice ----------------------------
@detector("F20", "EachPlayer whose body is a Seq (two instructions) or holds a choice")
def each_player(card):
    for path, n in walk(card):
        if isinstance(n, at.EachPlayer):
            body = n.effect if hasattr(n, "effect") else None
            kinds = sorted({a.verb.name for _p, a in walk(n) if isinstance(a, at.Atom)})
            seq = isinstance(body, at.Seq)
            choice = any(isinstance(s, at.Selector) and s.mode in (at.SelectorMode.CHOOSE, at.SelectorMode.ONE_OF)
                         and s.referent is None for _p, s in walk(n))
            yield f"seq={seq} choice={choice} verbs={kinds} ref={repr(n.ref)[:40]}"


# --- F23: a state trigger ("when there are N or more counters") ------------------------------
@detector("F23", "a counter-threshold trigger (CR 603.8 state trigger compiled as an event)")
def state_trigger(card):
    for path, n in walk(card):
        if isinstance(n, at.TriggeredAbility) and isinstance(n.event, at.CounterPlacedEvent) and n.condition is not None:
            yield f"{n.event.counter_kind.name} cond={repr(n.condition)[:80]}"


# --- F24: an extra trigger made by a carrier trigger ------------------------------------------
@detector("F24", "TRIGGER_ADDITIONAL (Yarok, Sanctum of All)")
def trigger_additional(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb is at.Verb.TRIGGER_ADDITIONAL:
            yield outer(path)


# --- F25: fights and dealer-filtered damage triggers --------------------------------------
@detector("F25f", "FIGHT")
def fights(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb is at.Verb.FIGHT:
            yield outer(path)


@detector("F25d", "a damage trigger with a dealer filter (source) that a creature-to-creature blow can match")
def dealer_filtered(card):
    for path, n in walk(card):
        if isinstance(n, (at.TriggeredAbility, at.DelayedTrigger)) and isinstance(n.event, at.DamageDealtEvent) \
                and n.event.source is not None:
            yield f"combat={n.event.combat} filter={repr(n.event.filter)[:70]} source={repr(n.event.source)[:60]}"


# --- F27: damage a source deals to its own controller (lifelink nets the journal) ------------
@detector("F27", "DEAL_DAMAGE whose recipients can include its controller ('each player', 'you', 'any target')")
def self_damage(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb is at.Verb.DEAL_DAMAGE:
            t = n.args.get("target")
            if isinstance(t, at.Selector) and at.ZoneKind.PLAYER in zones_of(t):
                ctrls = sorted({z.controller.name for z in t.zones if z.kind is at.ZoneKind.PLAYER})
                if any(c in ("ANY", "YOU", "EACH") for c in ctrls) or t.mode is at.SelectorMode.ALL:
                    yield f"{outer(path)} mode={t.mode.name} players={ctrls}"


@detector("F27l", "grants or has lifelink")
def lifelink(card):
    for path, n in walk(card):
        if isinstance(n, at.KeywordAbility) and n.keyword is at.Keyword.LIFELINK:
            yield outer(path) if path else "printed"
        if isinstance(n, at.Keyword) and n is at.Keyword.LIFELINK:
            yield f"keyword in {outer(path)}"


# --- F29: two token specs sharing a name with different abilities -----------------------------
TOKEN_SPECS: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))


@detector("F29", "a TokenSpec with abilities (its record is keyed by name)")
def token_specs(card):
    for path, n in walk(card):
        if isinstance(n, at.TokenSpec):
            yield f"{n.name} abilities={len(n.abilities)} sha={hash(repr(n)) & 0xffff:04x}"


# --- F30, F23: watchers of counter placements ------------------------------------------------
@detector("F30", "a CounterPlacedEvent trigger (a watcher of placements)")
def counter_watchers(card):
    for path, n in walk(card):
        if isinstance(n, (at.TriggeredAbility, at.DelayedTrigger)) and isinstance(n.event, at.CounterPlacedEvent):
            yield f"{n.event.counter_kind.name} filter={repr(n.event.filter)[:70]}"


# --- F31: "exiled with" readers ---------------------------------------------------------
@detector("F31", "IS_EXILED_WITH_SOURCE (a reader of 'exiled with ~')")
def exiled_with(card):
    for path, n in walk(card):
        if isinstance(n, at.FAtom) and n.pred.name == "IS_EXILED_WITH_SOURCE":
            yield outer(path)


# --- F33: CAST_THIS_TURN_FROM readers -----------------------------------------------------
@detector("F33", "a cast-zone read (CAST_THIS_TURN_FROM or kin)")
def cast_from(card):
    for path, n in walk(card):
        if isinstance(n, at.FAtom) and "CAST" in n.pred.name and "FROM" in n.pred.name:
            yield f"{outer(path)} {n.pred.name}"


# --- F34: a referent over a register that can bind several objects --------------------------
@detector("F34", "a referent 'target'/'result' selector in an ability whose designation or producer is plural")
def plural_referent(card):
    for ab in card.abilities:
        plural_target = False
        for _p, s in walk(ab):
            if isinstance(s, at.Selector) and s.mode is at.SelectorMode.TARGET:
                c = s.count
                if isinstance(c, at.QAtMost) or (isinstance(c, at.QConst) and c.value > 1):
                    plural_target = True
        plural_result = any(isinstance(a, at.Atom) and a.verb in (at.Verb.CREATE_TOKEN, at.Verb.SEARCH, at.Verb.MOVE_ZONE, at.Verb.CHOOSE)
                            for _p, a in walk(ab))
        for path, n in walk(ab):
            if isinstance(n, at.Atom):
                for role, val in n.args.pairs:
                    if isinstance(val, at.Selector) and val.referent == "target" and plural_target:
                        yield f"{type(ab).__name__} {n.verb.name}.{role} <- plural target"
                    if isinstance(val, at.Selector) and val.referent == "result" and plural_result:
                        yield f"{type(ab).__name__} {n.verb.name}.{role} <- result"


# --- F35: replacement effects of one event class ------------------------------------------
@detector("F35l", "a life-gain replacement")
def life_replacements(card):
    for path, n in walk(card):
        if isinstance(n, at.ReplacementAbility) and isinstance(n.event, at.LifeGainedEvent):
            yield repr(n.action)[:100]


@detector("F35z", "a zone-change replacement")
def zone_replacements(card):
    for path, n in walk(card):
        if isinstance(n, at.ReplacementAbility) and isinstance(n.event, at.ZoneChangeEvent):
            ev = n.event
            yield f"{ev.from_zone.kind.name}/{ev.from_zone.controller.name} -> {ev.to_zone.kind.name}/{ev.to_zone.controller.name} subj={repr(ev.subject)[:60]} -> {sorted({a.verb.name for _p, a in walk(n.action) if isinstance(a, at.Atom)})}"


# --- F36: an ALL over a library's top -----------------------------------------------------
@detector("F36", "an ALL selector over a library's top (the look window's partition)")
def all_over_top(card):
    for path, n in walk(card):
        if isinstance(n, at.Selector) and n.mode is at.SelectorMode.ALL and any(
                z.kind is at.ZoneKind.LIBRARY and z.position is at.ZonePosition.TOP for z in n.zones):
            yield f"{outer(path)} role={role_of(path)}"


# --- F37: "any number" ---------------------------------------------------------------------
@detector("F37", "a CHOOSE with QUnbounded count ('any number')")
def any_number(card):
    for path, n in walk(card):
        if isinstance(n, at.Selector) and n.mode is at.SelectorMode.CHOOSE and isinstance(n.count, at.QUnbounded) \
                and n.referent is None:
            yield f"{outer(path)} role={role_of(path)} zones={[(z.kind.name, z.controller.name) for z in n.zones]}"


# --- F38: "as this enters" effects ---------------------------------------------------------
@detector("F38", "an EtBState effect (only CHOOSE_NAME runs)")
def etb_effects(card):
    for path, n in walk(card):
        if isinstance(n, at.EtBState) and n.effect is not None:
            yield sorted({a.verb.name for _p, a in walk(n.effect) if isinstance(a, at.Atom)})


# --- F41: an "in any order" pick from another player's library or hand ----------------------
@detector("F41", "a move into a library of cards picked from another player's zone")
def into_other_library(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb is at.Verb.MOVE_ZONE:
            d = n.args.get("destination")
            if isinstance(d, at.Zone) and d.kind is at.ZoneKind.LIBRARY and d.controller not in (at.ControllerRef.YOU,):
                yield f"{outer(path)} dest={d.controller.name}"


# --- F43: a may-offer whose action can be impossible ---------------------------------------
@detector("F43", "an OptionalEffect whose action needs an object (sacrifice, discard, pay with a cost)")
def may_needs_object(card):
    for path, n in walk(card):
        if isinstance(n, at.OptionalEffect):
            verbs = sorted({a.verb.name for _p, a in walk(n.inner) if isinstance(a, at.Atom)})
            if set(verbs) & {"SACRIFICE", "MOVE_ZONE", "PAY", "DISCARD", "CHOOSE"}:
                yield f"{outer(path)} {verbs}"


# --- F44: Auras and what could make their host stop matching -------------------------------
@detector("F44a", "an Aura's enchant filter")
def aura_filter(card):
    if "Aura" in card.subtypes:
        for path, n in walk(card):
            if isinstance(n, at.KeywordAbility) and n.keyword.name == "ENCHANT":
                yield repr(n.params)[:110]


@detector("F44b", "changes control, types or creature-ness of a permanent (an Aura's host can stop matching)")
def host_changes(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb in (at.Verb.GAIN_CONTROL, at.Verb.GRANT_TYPE, at.Verb.SET_PT):
            yield f"{outer(path)} {n.verb.name} duration={type(n.args.get('duration')).__name__}"


# --- F45: "until ~ leaves" durations, simultaneous Aura returns ------------------------------
@detector("F45a", "a DurationUntilLeaves")
def until_leaves(card):
    for path, n in walk(card):
        if isinstance(n, at.DurationUntilLeaves):
            yield f"{outer(path)} source={n.source}"


@detector("F45p", "phases a permanent out")
def phasing(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb in (at.Verb.PHASE_OUT, at.Verb.PHASE_IN):
            yield outer(path)


@detector("F45d", "returns two or more permanent cards to the battlefield at once (an Aura among them)")
def multi_return(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb is at.Verb.MOVE_ZONE:
            d = n.args.get("destination")
            if isinstance(d, at.Zone) and d.kind is at.ZoneKind.BATTLEFIELD:
                for role in ("cards", "target"):
                    sel = n.args.get(role)
                    if isinstance(sel, at.Selector) and (zones_of(sel) & {at.ZoneKind.GRAVEYARD, at.ZoneKind.EXILE}):
                        c = sel.count
                        many = sel.mode is at.SelectorMode.ALL or isinstance(c, (at.QUnbounded, at.QAtMost)) or (
                            isinstance(c, at.QConst) and c.value > 1)
                        if many:
                            yield f"{outer(path)} {role} mode={sel.mode.name} count={c!r}"


# --- F46: MOVE_ZONE's top-n lane into a hand -------------------------------------------------
@detector("F46", "MOVE_ZONE top-n of a library into a hand with a non-YOU destination or another player's library")
def top_n_lane(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb is at.Verb.MOVE_ZONE and n.args.get("pop_order") is not None:
            d = n.args.get("destination")
            if isinstance(d, at.Zone) and d.kind is at.ZoneKind.HAND:
                yield f"{outer(path)} dest={d.controller.name} ctrl={n.args.get('controller')!r}"


# --- F47: a Conditional after a step that made several tokens ------------------------------
@detector("F47", "a Conditional after a CREATE_TOKEN of two or more")
def cond_after_tokens(card):
    for path, n in walk(card):
        if isinstance(n, at.Seq):
            seen_many = False
            for step in n.steps:
                if isinstance(step, at.Atom) and step.verb is at.Verb.CREATE_TOKEN:
                    c = step.args.get("count")
                    seen_many = not (c is None or isinstance(c, at.QConst) and c.value == 1)
                elif isinstance(step, at.Conditional) and seen_many:
                    yield f"{outer(path)}"


# --- F48, F21: an object moved twice in one resolution ---------------------------------------
@detector("F48", "an effect that moves an object and then moves or acts on it again ('exile it, then return it')")
def moved_twice(card):
    for path, n in walk(card):
        if isinstance(n, at.Seq):
            moved = False
            for step in n.steps:
                for _p, a in walk(step):
                    if isinstance(a, at.Atom) and a.verb is at.Verb.MOVE_ZONE:
                        sel = a.args.get("cards") or a.args.get("target")
                        if moved and isinstance(sel, at.Selector) and sel.referent in ("result", "target", "event"):
                            d = a.args.get("destination")
                            yield f"{outer(path)} then {d.kind.name if isinstance(d, at.Zone) else d}"
                        moved = True


# --- F49: "doesn't untap" and untap effects ---------------------------------------------------
@detector("F49n", "a 'doesn't untap' prevention (PREVENT_EFFECT over an untap)")
def no_untap(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb is at.Verb.PREVENT_EFFECT:
            ev = n.args.get("event")
            if isinstance(ev, at.TapStateEvent) or "UNTAP" in repr(ev)[:200]:
                yield f"{outer(path)} step={n.args.get('step')!r} duration={type(n.args.get('duration')).__name__}"


@detector("F49u", "UNTAP of a permanent by an effect")
def untaps(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb is at.Verb.UNTAP:
            yield outer(path)


# --- F50: damage to an object the same resolution moved ------------------------------------
@detector("F50", "an effect that moves or sacrifices an object and then deals damage (same resolution)")
def damage_after_move(card):
    for path, n in walk(card):
        if isinstance(n, at.Seq):
            moved = False
            for step in n.steps:
                verbs = {a.verb for _p, a in walk(step) if isinstance(a, at.Atom)}
                if moved and at.Verb.DEAL_DAMAGE in verbs:
                    yield outer(path)
                if verbs & {at.Verb.MOVE_ZONE, at.Verb.SACRIFICE, at.Verb.DESTROY}:
                    moved = True


# --- F52: casting another player's card; zone-change replacements on draws, casts, land drops --
@detector("F52", "a CAST or PERMIT over another player's cards")
def cast_others(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb in (at.Verb.CAST, at.Verb.PERMIT):
            s = n.args.get("source")
            if isinstance(s, at.Selector):
                ctrls = {z.controller.name for z in s.zones}
                if ctrls - {"YOU"}:
                    yield f"{outer(path)} {n.verb.name} zones={[(z.kind.name, z.controller.name) for z in s.zones]} ref={s.referent}"


# --- F53: "from anywhere" self-replacements ---------------------------------------------------
@detector("F53", "a zone-change replacement on its own source from ANY zone")
def from_anywhere(card):
    for path, n in walk(card):
        if isinstance(n, at.ReplacementAbility) and isinstance(n.event, at.ZoneChangeEvent):
            ev = n.event
            if ev.from_zone.kind is at.ZoneKind.ANY and isinstance(ev.subject, at.FAtom) and ev.subject.pred is at.FAtomPred.IS_SOURCE:
                yield f"{ev.from_zone.kind.name} -> {ev.to_zone.kind.name}"


# --- F54, F56: mana retention, hybrid ---------------------------------------------------------
@detector("F56", "a hybrid mana cost")
def hybrid(card):
    for path, n in walk(card):
        if isinstance(n, at.CostManaHybrid):
            yield outer(path) if path else "mana cost"


# --- F57-F59, F02: multiplayer readers ----------------------------------------------------
@detector("F57", "a singular OPPONENT/ALL_OPPONENTS/ANY ref on a one-player verb (raises at 3+ seats)")
def singular_opponent(card):
    one_player = {at.Verb.DRAW, at.Verb.SCRY, at.Verb.LOOK_AT, at.Verb.REVEAL, at.Verb.ADD_MANA, at.Verb.GAIN_CONTROL}
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb in one_player:
            c = n.args.get("controller")
            if isinstance(c, at.ControllerRef) and c in (at.ControllerRef.OPPONENT, at.ControllerRef.ALL_OPPONENTS, at.ControllerRef.ANY):
                yield f"{outer(path)} {n.verb.name}.controller={c.name}"


@detector("F02", "a comparison of opponents' counts ('an opponent controls more ... than you')")
def opp_compare(card):
    for path, n in walk(card):
        if isinstance(n, at.FAtom) and n.pred is at.FAtomPred.QTY_GE and "OPPONENT" in repr(n):
            yield f"{outer(path)} {repr(n)[:120]}"


# --- F60, F40: copy effects and chosen qualities on entering ------------------------------------
@detector("F60", "Verb.COPY (no executor handler)")
def copies(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb is at.Verb.COPY:
            yield outer(path)


@detector("F40", "an EtBState CHOOSE_NAME (a token copy of it would enter choosing, or not)")
def etb_choose(card):
    for path, n in walk(card):
        if isinstance(n, at.EtBState) and n.effect is not None and any(
                isinstance(a, at.Atom) and a.verb is at.Verb.CHOOSE_NAME for _p, a in walk(n.effect)):
            yield "EtBState CHOOSE_NAME"


# --- F61: Sagas and second main phases ---------------------------------------------------------
@detector("F61", "a Saga or a postcombat-main trigger")
def sagas(card):
    if "Saga" in card.subtypes:
        yield "Saga"


# --- F63: SCRY and REVEAL (the journal's knowledge rows) --------------------------------------
@detector("F63", "REVEAL of a hand (journalled as the library)")
def reveal_hand(card):
    for path, n in walk(card):
        if isinstance(n, at.Atom) and n.verb is at.Verb.REVEAL:
            yield f"{outer(path)} count={n.args.get('count')!r}"[:90]


def text_of(raw, oid) -> str:
    rc = raw.get(oid)
    return " ".join(rc.sentences) if rc is not None else ""


def main() -> None:
    out_path = Path(sys.argv[2])
    all_sets = "--all-sets" in sys.argv
    lines: list[str] = []
    hits: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    b3_hits: dict[str, list[str]] = defaultdict(list)
    wide: dict[str, set[str]] = defaultdict(set)
    for code in POOLS:
        supply = games.get_supply("verified", code)
        for oid in supply.deckable:
            card = supply.pool.results[oid].card
            for fid, _what, fn in DETECTORS:
                for h in fn(card):
                    hits[fid][code].append(f"{card.name} | {h}")
        every = games.get_supply("all", code)
        names = set(B3.get(code, ()))
        for oid, res in every.pool.results.items():
            if res.card.name in names and not res.card.is_token:
                for fid, _what, fn in DETECTORS:
                    for h in fn(res.card):
                        b3_hits[fid].append(f"{code} {res.card.name} | {h}")
    if all_sets:
        for code in ALL_SETS:
            try:
                supply = games.get_supply("all", code)
            except Exception as e:  # noqa: BLE001 - a census row, not a crash
                lines.append(f"[{code}: {type(e).__name__}: {e}]")
                continue
            for oid, res in supply.pool.results.items():
                if res.card.is_token:
                    continue
                for fid, _what, fn in DETECTORS:
                    if any(True for _ in fn(res.card)):
                        wide[fid].add(f"{code} {res.card.name}")
    for fid, what, _fn in DETECTORS:
        lines.append(f"\n== {fid}: {what}")
        for code in POOLS:
            rows = hits[fid][code]
            cards = sorted({r.split(' | ')[0] for r in rows})
            lines.append(f"  {code} deal pool: {len(rows)} hits on {len(cards)} cards")
            for r in sorted(set(rows)):
                lines.append(f"    {r}")
        if b3_hits[fid]:
            lines.append(f"  B3 (copy round) cards: {len(b3_hits[fid])}")
            for r in sorted(set(b3_hits[fid])):
                lines.append(f"    {r}")
        if all_sets:
            lines.append(f"  19 sets (all mode): {len(wide[fid])} cards")
    out_path.write_text("\n".join(lines) + "\n")
    print(f"wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
