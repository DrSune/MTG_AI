#!/usr/bin/env python3
"""Scenario-pack runner: the executable rules-conformance suite.

A pack is a SMALL deterministic world-script: a handful of cards, one or
two scripted engine actions, and a post-condition block. Packs prove rules
interactions end to end through the REAL executor (compiled trigger IR
included), not just through unit fixtures.

Usage:
    .venv/bin/python tools/run_scenarios.py [--dir tools/scenarios]

Exit code 0 = every pack passed. A failing expect prints the pack, the
key and observed-vs-expected — nothing else.

Pack vocabulary (all keys required as noted):
  world   : {"life": int, "seed": int}
  cards   : [{"key": str, "zone": "hand"|"battlefield"|"library"|"graveyard"
                    |"exile", "controller": 0|1,
              "real": "<pool card name>"  OR  "<compiled token name>"
                                            (a token golden — "Treasure" —
                                            addressed by name through the
                                            pool fallback; is_token records
                                            only), OR
              "name"/"power"/"toughness"/"type" (synthetic; optional
                                            "colors", "keywords", and
                                            "token": true for a token)}]
  mana    : {"0": {"G": 5}, ...}            optional, per seat index
  mulligan: [word...]                       optional (CR 103.5): the pack starts
                                            like a dealt game, each seat drawing seven from its
                                            library, and the London mulligan runs before the
                                            first turn (games.mulligans). The words answer its
                                            asks in order, exactly one per ask: "keep" or
                                            "mulligan", or the pack key of the card a mulligan
                                            puts on the bottom ("first-legal" takes the first
                                            offered card)
  steps   : [{"op": "deal_damage"|"fight", "source": key, "target": key
              [, "amount": int]},
             {"op": "cast", "real": name, "x": int?, "targets": [key...],
                                            (a target may be "p0"/"p1": a player)
              "decisions": [str...]},       each word must be offered by the ask it
                                            answers (a pack key resolves to its handle;
                                            "first-legal" takes the first offered word).
                                            The cast reads its modes and designations
                                            from the front (CR 601.2b-c); the step's
                                            later asks take the words after them
             {"op": "end_turn"} | {"op": "advance_turn"},
             {"op": "enter", "key": k}      hand -> battlefield (journalled:
                                            the sickness clock sees it),
             {"op": "enter", "key": k, "hold_triggers": true}
                                            the triggers the entry arms wait,
                                            unresolved, until the NEXT step's
                                            settle — the stand-in for "in
                                            response to the trigger" (the
                                            engine has no priority window
                                            for triggers),
             {"op": "move", "key": k, "to": "hand"|"graveyard"|"exile"
              |"battlefield"|"library"}     a journalled move by "another
                                            effect" (a bounce, a destroy, an
                                            exile) to the card's OWNER's
                                            zone; its settle drains held
                                            triggers after the move,
             {"op": "play", "key": k}       the REAL land drop (CR 305.1,
                                            legality + once-per-turn +
                                            EtBState entry hook),
             {"op": "enter"|"enchant"|"play", ...,
              "decisions": [str...]}        ordered words the step's asks
                                            consume (scry, modes, may-offers);
                                            never forces a word the
                                            vocabulary lacks,
             {"op": "enchant", "aura": k, "host": k}   attach an aura
                                            (restores a battlefield-declared
                                            aura the setup CR 704.5q sweep
                                            already buried, then attaches via
                                            the real API — journalled
                                            re-entry RE-REGISTERS its static),
             {"op": "loyalty", "key": k, "set": n}    seed the loyalty ledger,
             {"op": "mana", "seat": 0|1, "add": {"R": 1}}  add mana to a
                                            pool at this step (pools empty as
                                            each step and phase ends, CR 500.5;
                                            stands in for the lands tapped),
             {"op": "activate", "key": k, "idx": i,   the folded ACTIVATE
              "seat": 0|1, "targets": [k...],         move (legality+pay+run),
              "decisions": [str...], "x": int?},      x: the announced X of an
                                            X-cost activation (CR 602.2b);
                                            absent, the X ask takes a word
             {"op": "act", "seat": 0|1, "words": [word...]}
                                            the seat's priority decisions
                                            through the bench router until it
                                            passes, as a dealt game asks them
                                            (bench/router.py). The
                                            words answer its asks in order,
                                            one word per ask: the menu row
                                            ("cast:<key>[:k][:x<N>]",
                                            "act:<key>:<index>",
                                            "land:<key>"), then the asks it
                                            opens (the mode, then one target
                                            ask per pick, slot by slot, CR
                                            601.2c; "DONE" ends an "up to"
                                            slot); the window passes when the
                                            words are used up. A word an ask
                                            does not offer raises, naming the
                                            ask and its words,
             {"op": "resolve"}              every player passes once: the
                                            top object of the stack resolves
                                            (CR 117.4), nothing after it (what
                                            it put on the stack waits too),
             {"op": "pass"}                 both players pass until the stack
                                            is empty,
             {"op": "to_step", "step": S}   both players pass until step S
                                            ("COMBAT" for the beginning of
                                            combat, "END_TURN" for the end
                                            step, ...) holds priority,
             "hold": true on any step: the player keeps
                                            priority and receives it again (CR
                                            117.3c): the waiting triggers go on
                                            the stack (CR 117.5), nobody passes,
                                            and what is on the stack waits for
                                            the next steps to respond to; every
                                            other step ends with both players
                                            passing until the stack is empty,
             "tap": true on a cast step: the caster taps the mana sources
                                            that pay it (the menu's automatic
                                            payment, CR 601.2g, 605.3a),
             {"op": "combat", "seat": 0|1, "attack": {key: bool|pwKey},
                                            (a planeswalker's pack key
                                            attacks that planeswalker)
              "may": {key: bool},
              "block": {blockerKey: attackerKey|null},  per-blocker pick
              "order": {attackerKey: [slot...]},        order asks
              "trample": {attackerKey: [amount...]},    excess asks
              "policy": {attackerKey: "UNBLOCKED"|
                                  "AS_BLOCKED"},        damage-assignment policy
              "respond": {STEP: [step...]}}  steps run when that combat step
                                            (DECLARE_ATTACKERS,
                                            DECLARE_BLOCKERS, ...) has
                                            priority with an empty stack: an
                                            instant cast after blocks
                                            the whole COMBAT phase; the
                                            ask provider answers ONLY from
                                            these maps and the step's
                                            "decisions" (the engine narrows
                                            the vocabulary; an unspecified
                                            block is NONE). A caller's own
                                            answerer (the G1 probe) keeps the
                                            asks no map or word claims that
                                            are not combat declarations]
  expect  : {"life": {"0": int...}, "zone": {key: zone...},  zone may be
                                            "ceased": a token gone (CR 704.5d),
              "damage": {key: int...},      — the damage mark ledger
              "damage_received": {key: int...}, — historical card DAMAGE rows
                                         summed (survives cleanup; subset lane)
              "attackers": {key: bool},     — the DECLARE_ATTACKERS rows,
             "blocked": {key: [blockerKey...]} — the DECLARE_BLOCKERS rows
                                        of the last group,
             "asks": {key: "ATTACK,DECLINE"},  — vocab per attack site,
             "block_asks": {key: "a,b,NONE"},— vocab per block site,
             "policy_asks": {key: "..."},    — vocab per policy ask,
             "not_asked": [key...],        — creatures never asked,
             "not_asked_to_block": [key],  — never offered a block ask,
             "tokens": {Name: n},          — battlefield token records
             "tapped": {key: bool},
             "attached": {key: hostKey|null},  the attachment table
             "hand": {"0": int},
             "lost": {"0": bool},          the seat is in
                                            executor.lost_players (LOSE_GAME,
                                            or CR 704.5a/b: a step that ends the
                                            game is the last one that runs),
             "mana_pool": {"0": {"W": 1}},  the PlayerState.mana_pool totals
                                            (an absent colour equals 0)
             "kick_rows": {key: {"kicked": bool, "x": int|null}},
                                        the LAST CAST journal row of the
                                        key's card (the same 6-tuple
                                        WAS_KICKED reads: paid flag + the
                                        declared X). A never-cast key FAILS
                                        loudly — no row, no silent False.
             "counters": {key: {"KIND": n}},  the counter table,
             "power": {key: int},             ledger effective_pt,
             "toughness": {key: int},         (base->timestamp fold),
             "library": {"0": [names...TOP-first]},   exact order,
             "graveyard": {"0": [names...]},          exact bag
             "turn_seats": [0, 0, 1],  the seat of every turn begun, in
                                        order (CR 500.7 extra turns)
             "phased_out": {key: bool},  the CR 702.26 status
             "controller": {key: 0|1}}  the effective controller's seat
                                        (CR 610.3c)
  setup cards may carry "counters": {"KIND": n}; an activate step's targets
  may name a player as "p0"/"p1".
  any step may carry "expect_raise": "<text>": the step must raise, with the
  text in its message (a refusal: "illegal target"). A step without
  "decisions" raises at its first ask that is not a response window, and the
  message names the ask and every word it offers: "mana:card:1 needs a
  decision from ('W', 'U', 'B', 'R', 'G')". So expect_raise pins an ask's exact
  words, which is how a pack says "X is not offered" (a decision word the ask
  lacks fails the pack instead). The step stops at that ask; a pack puts it
  last.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from MTG_bot.core.ability_tree import (
    ControllerRef,
    FAnd,
    Keyword,
    QConst,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor, GameOver
from MTG_bot.core.executor.events import KIND_CAST, KIND_DAMAGE
from MTG_bot.core.executor.games import OPENING_HAND, get_supply, identity_of, mulligans
from MTG_bot.core.executor.stack import cast, play_land
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)

ZONE_OF_NAME = {
    "battlefield": ZONE_BATTLEFIELD,
    "hand": ZONE_HAND,
    "graveyard": ZONE_GRAVEYARD,
    "exile": ZONE_EXILE,
    "library": ZONE_LIBRARY,  # search/tutor assertions
}
UNIV = FAnd(())
# The "move" op's destinations.
_MOVE_TO = {
    "battlefield": ZoneKind.BATTLEFIELD,
    "hand": ZoneKind.HAND,
    "graveyard": ZoneKind.GRAVEYARD,
    "exile": ZoneKind.EXILE,
    "library": ZoneKind.LIBRARY,
}


class PackError(Exception):
    pass


def _keyword_tuple(card: dict) -> tuple[str, ...]:
    """A synthetic card's printed keywords. A bare string ("FLYING") is refused: it would
    become a tuple of letters, and the card would silently have no keyword."""
    keywords = card.get("keywords", ())
    if isinstance(keywords, str):
        raise PackError(f"card {card.get('key')!r}: keywords must be a list, got {keywords!r}")
    return tuple(keywords)


def _atom(verb, **roles):
    from MTG_bot.core.ability_tree import Atom, AtomArgs

    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


def _bf_target():
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        UNIV,
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )


#: A decision word that takes the ask's first offered word: for an ask the pack does not test.
#: Any other word must be one the ask offers, or the pack fails (a silent fallback would let a
#: shifted queue pass).
FIRST_LEGAL = "first-legal"
#: The asks a combat step's maps describe: the combat itself (attackers, blockers, damage order,
#: trample excess, damage policy). An unspecified one keeps the combat op's default.
COMBAT_DECLARATIONS = ("attack:", "block:", "order:", "trample:", "policy:")
_ORACLES: dict[str, Any] = {}  # the act op's card text, one index per set


class ScenarioRunner:
    def __init__(self, pack: dict, supply, setup_provider=None):
        self.pack = pack
        self.supply = supply
        #: pack-written decision words an ask did not offer; the ask took a default instead,
        #: so the pack did not test what it says (reported as failures by run_pack)
        self.unoffered: list[str] = []
        #: the running step's queue of decision words (None outside a step with words)
        self.queue: list[str] | None = None
        world_cfg = pack.get("world", {})
        self.world = GameWorld(
            num_players=2,
            start_life=world_cfg.get("life", 20),
            master_seed=world_cfg.get("seed", 7),
        )
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.seats = [self.p0, self.p1]
        self.ex = Executor(self.world)
        self.handles: dict[str, Any] = {}
        synth = 0
        start_tapped: list[Any] = []
        for card in pack["cards"]:
            if "real" in card:
                record = None
                for oid, meta in supply.metas.items():
                    if meta.name == card["real"]:
                        record = supply.pool.results[oid].card
                        break
                if record is None:
                    # Token identities are compiled golden rows, never dealt
                    # pool metas (supply('all') filters is_token out of metas
                    # in games.compile_supply), so a metas miss falls back to
                    # the compiled token record by name. Only is_token records
                    # qualify: the lane never substitutes a printed identity,
                    # and the golden's real oracle_id is what
                    # binder.attach_pool files under ``records`` and
                    # legality.spell_record reads, so the pack-keyed token
                    # carries the same compiled ActivatedAbility the engine's
                    # own tokens carry.
                    for result in supply.pool.results.values():
                        if result.card.is_token and result.card.name == card["real"]:
                            record = result.card
                            break
                if record is None:
                    raise PackError(f"pool has no card {card['real']!r}")
                identity = identity_of(record)
            else:
                synth += 1
                identity = CardIdentity(
                    oracle_id=f"9{synth:07d}-1111-2222-3333-444444444444",
                    name=card["name"],
                    type_line=card.get("type", "Creature"),
                    power=card.get("power"),
                    toughness=card.get("toughness"),
                    cmc=card.get("cmc", 2),
                    # Optional colour and printed keywords; absent keys are the dataclass defaults.
                    colors=tuple(card.get("colors", ())),
                    keywords=_keyword_tuple(card),
                    # A synthetic TOKEN ("token": true), e.g. a token copy of a legendary creature.
                    is_token=bool(card.get("token", False)),
                    # A synthetic planeswalker may declare its printed loyalty, so damage
                    # removes loyalty (CR 120.3c) instead of marking it like creature damage.
                    loyalty=str(card["loyalty"]) if "loyalty" in card else None,
                )
            zone = ZONE_OF_NAME[card.get("zone", "battlefield")]
            self.handles[card["key"]] = self.world.add_card(
                identity, self.seats[card["controller"]], zone
            )
            # A permanent that starts tapped ("start_tapped", or the older "tapped"). Applied
            # after the opening begin_turn below, whose untap step would untap seat 0's.
            if card.get("start_tapped") or card.get("tapped"):
                start_tapped.append(self.handles[card["key"]])
            # Counters a setup card starts with, e.g. {"PLUS_1_PLUS_1": 1}.
            for kind, n in card.get("counters", {}).items():
                self.world.cards[self.handles[card["key"]]].counters[kind] = int(n)
        # The real cards' triggers/abilities register from the compiled pool.
        self.ex.attach_pool(supply.pool)
        if "mulligan" in pack:
            self._mulligans(list(pack["mulligan"]))
        # The clock opens for real (begin_turn: markers, ledger; turn 1 of a two-player game, so
        # seat 0 skips its draw step, CR 103.8a); a faked turn would desync world.turn and the
        # sickness clock against advance_turn. A card pre-placed on the battlefield can trigger
        # at this first begin_turn (an upkeep or beginning-of-turn trigger) before any step
        # installs an answerer; a caller may pass one for setup.
        self.ex.decisions.provider = setup_provider
        try:
            self.ex.begin_turn(self.p0)
        finally:
            self.ex.decisions.provider = None
        for handle in start_tapped:
            self.world.cards[handle].tapped = True
        # The pack's mana is the pool in the first main phase: put in after the opening
        # begin_turn, whose steps each empty the pools as they end (CR 500.4).
        for seat, colors in pack.get("mana", {}).items():
            for color, n in colors.items():
                self.world.players[self.seats[int(seat)]].mana_pool[color] = n
        # The asks the engine made, and libraries deep enough for real
        # begin_turn/advance_turn draws.
        self.asks_seen: list[tuple[str, tuple[str, ...]]] = []
        # Every kickback ask the engine made ("unless its controller pays"),
        # as (tag, vocab, ANSWER) triples; the expect lane kickback_asks reads
        # these.
        self.rung1_asks: list[tuple[str, tuple[str, ...], str]] = []
        # The filler below lands ON TOP of a pack's typed library cards, so
        # library-peek/scry asks would offer opaque "Library N" candidates.
        # A pack that sets ``"world": {"library_top": true}`` re-raises its
        # OWN library-zone cards above the filler (relative order preserved).
        for seat_idx in (0, 1):
            for i in range(6):
                self.world.add_card(
                    CardIdentity(
                        oracle_id=f"9f00000{i}-0000-0000-0000-00000000000{seat_idx}",
                        name=f"Library {i}",
                        type_line="Creature",
                        power="1",
                        toughness="1",
                        cmc=1,
                    ),
                    self.seats[seat_idx],
                    ZONE_LIBRARY,
                )
        if pack.get("world", {}).get("library_top"):
            for key, handle in self.handles.items():
                if self.world.zone_of(handle).kind != ZONE_LIBRARY:
                    continue
                pl = self.world.players[self.world.controller_of(handle)]
                entries = pl.zone(ZONE_LIBRARY).entries
                entries.remove(handle)
                entries.append(handle)

    def _mulligans(self, words: list[str]) -> None:
        """The pack's ``mulligan`` lane: opening hands, then CR 103.5 answered word for word."""
        for seat in self.seats:
            self.world.draw(seat, OPENING_HAND)

        def answer(vocab: tuple[str, ...], what: str) -> str:
            if not words:
                raise PackError(f"mulligan: no word left for {what} {tuple(vocab)}")
            word = words.pop(0)
            got = vocab[0] if word == FIRST_LEGAL else str(self.handles.get(word, word))
            if got not in vocab:
                raise PackError(f"mulligan: {what}: word {word!r} not offered in {tuple(vocab)}")
            return got

        self.ex.decisions.provider = answer
        try:
            mulligans(self.ex, self.seats)
        finally:
            self.ex.decisions.provider = None
        if words:
            raise PackError(f"mulligan: words no ask took: {words}")

    def run_step(self, step: dict) -> None:
        if step.get("decisions") and step["op"] != "combat":
            # The decision channel: a non-combat step (an ETB that scrys, a
            # mode choice, a may-offer) carries the ordered words its asks
            # consume, IN ARRIVAL ORDER. A word the vocabulary does not carry
            # is never forced: the ask takes its default and the miss fails
            # the pack (self.unoffered).
            queue = list(step["decisions"])

            def prov(vocab, what):
                self.asks_seen.append((what, tuple(vocab)))
                rung1 = what.startswith("pay:")
                # A kickback ask the queue does not reach takes "PASS" (a
                # pack that wants another answer says so with a word).
                if not queue:
                    answer = "PASS" if rung1 else vocab[0]
                    if rung1:
                        self.rung1_asks.append((what, tuple(vocab), answer))
                    return answer
                got = queue.pop(0)
                if got in self.handles:
                    # A DESIGNATION answer may be given as a PACK KEY
                    # ("sheep", not "card:1") — resolved to the handle
                    # string the vocabulary actually carries. Pack-card
                    # order is deterministic, so the pin stays replay-exact
                    # and the pack says WHO, not an accident of numbering.
                    got = str(self.handles[got])
                if got == FIRST_LEGAL:
                    got = vocab[0]
                answer = got if got in vocab else ("PASS" if rung1 else vocab[0])
                if answer != got:
                    self.unoffered.append(f"{what}: pack word {got!r} not offered in {tuple(vocab)}")
                if rung1:
                    self.rung1_asks.append((what, tuple(vocab), answer))
                return answer

            self.ex.decisions.provider = prov
            self.queue = queue
            try:
                self._dispatch(step)
            finally:
                self.ex.decisions.provider = None
                self.queue = None
            return
        if step["op"] != "combat":
            # A step WITHOUT a decisions queue still answers kickback asks
            # with PASS. Every OTHER ask raises the engine's own exhaustion
            # message verbatim.
            def quiet(vocab, what):
                self.asks_seen.append((what, tuple(vocab)))
                if what.startswith("pay:"):
                    self.rung1_asks.append((what, tuple(vocab), "PASS"))
                    return "PASS"
                raise ValueError(
                    f"executor: {what} needs a decision from {tuple(vocab)}, "
                    "nothing is primed and no answerer is registered"
                )

            self.ex.decisions.provider = quiet
            try:
                self._dispatch(step)
            finally:
                self.ex.decisions.provider = None
            return
        self._dispatch(step)

    def _dispatch(self, step: dict) -> None:
        """One step. ``"hold": true``: the step's player keeps priority and
        receives it again (CR 117.3c), so state-based actions are checked and
        the waiting triggers go on the stack (CR 117.5), and nobody passes yet:
        what is on the stack waits there for the next steps to respond to. Any
        step without it ends with both players passing until the stack is
        empty."""
        if step.get("hold"):
            with self.ex.holding_priority():
                self._dispatch_op(step)
                self.ex._priority_check()
            return
        self._dispatch_op(step)
        if step["op"] != "resolve" and not self.ex.driven and self.ex.stack.frames:
            self.ex.fire_triggers()  # what an earlier step held resolves now

    def _dispatch_op(self, step: dict) -> None:
        op = step["op"]
        if op in ("deal_damage", "fight"):
            verb = Verb.DEAL_DAMAGE if op == "deal_damage" else Verb.FIGHT
            roles: dict[str, Any] = {"target": _bf_target()}
            if op == "deal_damage":
                roles["amount"] = QConst(step["amount"])
            self.ex.execute(
                _atom(verb, **roles),
                source=self.handles[step["source"]],
                controller=self.seats[step.get("controller", 0)],
                bindings={"target": self.handles[step["target"]]},
            )
        elif op == "cast":
            spell_key = step.get("key") or f"cast_{step['real']}"
            if spell_key not in self.handles:
                raise PackError(f"no hand card {spell_key!r} — add it under cards")
            targets = [self._target_handle(k) for k in step.get("targets", ())]
            # A cast step's "player:N" decision token is a PLAYER
            # designation for the spell's target slot. The ASK channel never
            # answers CAST-time multi-candidate targeting (that stays loud by
            # harness policy), so the token lifts straight into the explicit
            # target list — the pack says WHO, seat-indexed.
            for tok in step.get("decisions", ()):
                if isinstance(tok, str) and tok.startswith("player:"):
                    targets.append(self.seats[int(tok.split(":", 1)[1])])
            seat = self.seats[step.get("controller", 0)]
            if step.get("tap"):
                # "tap": the caster taps the mana sources that pay it, as a player
                # does while casting (CR 601.2g, 605.3a; the menu's automatic payment).
                from MTG_bot.core.executor.legality import tap_for_payment
                from MTG_bot.core.executor.menu import cast_taps

                taps = cast_taps(
                    self.ex, seat, self.handles[spell_key], bool(step.get("kicked", False)),
                    step.get("x"), tuple(targets),
                )
                if taps is None:
                    raise PackError(f"cast {spell_key}: its mana sources cannot pay it")
                tap_for_payment(self.ex, seat, taps)
            words = tuple(step.get("decisions", ()))
            with self.ex.holding_priority():
                frame = cast(
                    self.ex,
                    self.seats[step.get("controller", 0)],
                    self.handles[spell_key],
                    x=step.get("x"),
                    kicked=bool(step.get("kicked", False)),
                    targets=tuple(targets),
                    decisions=words,
                )
            if self.queue is not None:
                # The cast read its modes and designations from the front of the words
                # (CR 601.2b-c); the step's later asks take the words after them.
                del self.queue[: len(words) - len(frame.decisions)]
            self.ex._finish_op()  # undriven: both players pass until the stack is empty
        elif op == "resolve":
            # Every player passes once (CR 117.4): the top object resolves, and
            # what it put on the stack waits until the next step says so.
            with self.ex.holding_priority():
                self.ex.all_pass()
        elif op == "pass":
            # Both players pass until the stack is empty.
            self.ex.fire_triggers()
        elif op == "to_step":
            # Both players pass until the step holds priority with an empty stack (an
            # instant in the opponent's beginning of combat or end step).
            self.ex.pass_until(step["step"])
            if self.ex.phase != step["step"]:
                raise PackError(f"to_step: the step {step['step']!r} never came")
        elif op == "end_turn":
            self.ex.end_turn()
        elif op == "advance_turn":
            self.ex.advance_turn()
        elif op == "play":
            # The REAL land drop (CR 305.1) — legality re-check,
            # once-per-turn ledger, and the journal's entry hook that
            # stamps the compiled EtBState (the M21 checklands and
            # temples enter TAPPED; asserting the printed promise).
            play_land(
                self.ex,
                self.seats[int(step.get("seat", 0))],
                self.handles[step["key"]],
            )
        elif op == "enter":
            handle = self.handles[step["key"]]
            atom = _atom(
                Verb.MOVE_ZONE,
                cards=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    UNIV,
                    zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),),
                ),
                destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                tapped_on_enter=bool(step.get("tapped", False)),
            )
            # "hold_triggers" leaves the armed triggers queued, through the binder's own
            # hold flag (nothing goes on the stack); the next step's settle resolves
            # them after its own action (a response).
            binder = self.ex.binder
            held = bool(step.get("hold_triggers"))
            was_holding = binder.hold
            if held:
                binder.hold = True
            try:
                self.ex.execute(
                    atom,
                    source=handle,
                    controller=self.world.controller_of(handle),
                    bindings={"cards": handle},
                )
            finally:
                binder.hold = was_holding
        elif op == "move":
            # A journalled zone move by another effect, to the card's owner's zone
            # (the destroy / bounce / exile stand-in).
            handle = self.handles[step["key"]]
            self.ex.execute(
                _atom(
                    Verb.MOVE_ZONE,
                    cards=Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        UNIV,
                        zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
                    ),
                    destination=Zone(_MOVE_TO[step["to"]], ControllerRef.OWNER),
                ),
                source=handle,
                controller=self.world.controller_of(handle),
                bindings={"cards": handle},
            )
        elif op == "enchant":
            # A pack that DECLARES an aura on the battlefield meets the
            # CR 704.5q unattached-aura SBA at setup (begin_turn's settle):
            # the sweep graves the aura and expires its static layer. So
            # restore the aura through the world, journal the move so the
            # binder lifecycle RE-REGISTERS the static (attach_source mints
            # fresh layer records), then attach via the canonical API.
            aura = self.handles[step["aura"]]
            host = self.handles[step["host"]]
            before = self.ex.journal.snapshot()
            if self.world.zone_of(aura).kind != ZONE_BATTLEFIELD:
                self.world.move_to_zone(
                    aura, self.world.controller_of(aura), ZONE_BATTLEFIELD
                )
            self.ex.attach_aura(aura, host)  # attachments table + recompute
            self.ex.journal.record_atom(before, None, "ATTACH", [])
            self.ex.binder.on_events()  # GY->BF re-entry re-registers
            self.ex.layers.recompute()
            # on_events only QUEUES: drain like the activate op, so the
            # aura's own EtB ("tap enchanted creature", Capture Sphere)
            # resolves. The attachment is already in the table when the
            # trigger RESOLVES, so "enchanted creature" reads the new host.
            self.ex.fire_triggers()
        elif op == "loyalty":
            # harness ledger write: seed the CR 606.3 loyalty counter so a
            # minus ability with a big cost (Herald's -7) is payable.
            handle = self.handles[step["key"]]
            self.world.cards[handle].counters["LOYALTY"] = int(step["set"])
        elif op == "life":
            # harness ledger write, as the loyalty seed: set a seat's life
            # directly. The LIFE_LEAD_OVER_START_GE lane reads current life
            # minus the executor's starting-life snapshot, so this sets up a
            # "gained N since the start" scenario without a healing spell.
            seat = self.seats[int(step["seat"])]
            self.world.players[seat].life = int(step["set"])
        elif op == "mana":
            # harness pool write, as loyalty/life: mana empties as each step
            # and phase ends (CR 500.5), so a pack that pays after a phase or
            # turn change adds the seat's mana at that step, standing in for
            # the lands it would tap there.
            pool = self.world.players[self.seats[int(step["seat"])]].mana_pool
            for color, n in step["add"].items():
                pool[color] = pool.get(color, 0) + int(n)
        elif op == "activate":
            from MTG_bot.core.executor.legality import activate

            activate(
                self.ex,
                self.handles[step["key"]],
                int(step.get("idx", 0)),
                seat=self.seats[int(step.get("seat", 0))],
                # "p0"/"p1" designate a player (a "target opponent", or a "target
                # player" that may be the caster); any other word is a pack key.
                targets=tuple(self._target_handle(k) for k in step.get("targets", ())),
                # No decisions pool: the step's words answer its asks through the provider
                # alone (run_step), in arrival order, so one word never answers two asks (a
                # may-offer and the counter window the cast opens, CR 601.2i).
                # The activation's X (CR 602.2b -> 601.2b): an explicit announcement;
                # absent, X is asked through the decision channel.
                x=step.get("x"),
            )
            if not self.ex.driven:
                self.ex.fire_triggers()
        elif op == "combat":
            self._combat(step)
        elif op == "act":
            self._act_window(step)
        else:
            raise PackError(f"unknown op {op!r}")

    def _target_handle(self, key: str):
        """A ``targets`` entry: a pack key, ``p0``/``p1`` for a player (so a "target
        player" slot can name the caster in a cast or an activate step), or
        ``ability:<key>`` for that card's topmost ability on the stack."""
        if key in ("p0", "p1") and key not in self.handles:
            return self.seats[int(key[1])]
        if key.startswith("ability:"):  # the topmost ability on the stack of that pack card
            source = self.handles[key.split(":", 1)[1]]
            frame = next((f for f in reversed(self.ex.stack.frames) if f.source == source
                          and f.spell_kind in ("ACTIVATED", "TRIGGERED")), None)
            if frame is None:
                raise PackError(f"no ability of {key.split(':', 1)[1]!r} is on the stack")
            return frame.handle
        return self.handles[key]

    def _resolve_word(self, word: str) -> str:
        """A word (or either side of a ``card@target`` composite) given as a
        PACK KEY resolves to the handle string the vocabulary carries; the
        seat literals ``p0``/``p1`` resolve to the player handles (an "any
        target" instant's vocabulary names players)."""
        if word in self.handles:
            return str(self.handles[word])
        if word in ("p0", "p1"):
            return str(self.seats[int(word[1])])
        card, sep, target = word.partition("@")
        if sep:
            target, x_sep, x = target.partition(":x")  # an X spell's window token
            return f"{self._resolve_word(card)}@{self._resolve_word(target)}{x_sep}{x}"
        return word

    def _act_window(self, step: dict) -> None:
        """The ``act`` op: the seat's priority decisions through the bench router until it
        passes (at most ``games.MAX_ACTS_PER_STEP`` actions), its asks answered by the step's
        words in order (the vocabulary above)."""
        from MTG_bot.bench.router import SeatRouter
        from MTG_bot.bench.view import OracleIndex, SeatLens
        from MTG_bot.core.executor.games import Game

        words = [self._row_word(w) for w in step["words"]]

        class Words:
            name = "pack"

            def decide(self, ask, obs) -> int:
                tokens = tuple(o.token for o in ask.options)
                if not words:
                    if ask.kind in ("act", "priority"):
                        return tokens.index("PASS")
                    raise PackError(f"act: no word left for the {ask.kind} ask {ask.site}; it offers {tokens}")
                word = words.pop(0)
                if word not in tokens:
                    raise PackError(f"act: the {ask.kind} ask {ask.site} does not offer {word!r}; it offers {tokens}")
                return tokens.index(word)

        set_code = str(self.pack.get("set", "M21"))
        oracle = _ORACLES.get(set_code) or _ORACLES.setdefault(set_code, OracleIndex.for_sets(set_code))
        game = Game(executor=self.ex, seed=0, pool_mode="all")
        router = SeatRouter(game, [Words(), Words()], [SeatLens(0, oracle), SeatLens(1, oracle)],
                            supply=self.supply)
        from MTG_bot.core.executor.games import MAX_ACTS_PER_STEP

        self.ex.decisions.provider = router.answer
        seat = self.seats[int(step.get("seat", 0))]
        try:
            for _ in range(MAX_ACTS_PER_STEP):
                if not router.take_priority(game, seat):
                    break
        finally:
            self.ex.decisions.provider = None
        if words:
            raise PackError(f"act: words no ask took: {words}")

    def _row_word(self, word: str) -> str:
        """An ``act`` word: a menu row's pack key resolved to its handle ("cast:pm:x3" ->
        "cast:card:0:x3"), or any other word as _resolve_word reads it."""
        head, sep, rest = word.partition(":")
        if sep and head in ("cast", "act", "land"):
            key, sep, tail = rest.partition(":")
            return f"{head}:{self._resolve_word(key)}{sep}{tail}"
        return self._resolve_word(word)

    def _combat(self, step: dict) -> None:
        """Run the whole COMBAT phase answering the engine's asks from the
        pack's answer maps ONLY. Site tags carry handles (attack:<card>:
        <turn>, may:<card>). ``block`` maps a blocker key to the attacker
        key it picks (or "NONE"); ``order`` maps an attacker key to the
        list of positional picks its ordering asks consume in slot order;
        ``trample`` maps an attacker key to the list of excess amounts its
        recipient asks consume in order (the player takes the rest);
        ``policy`` maps an attacker key to AS_BLOCKED/UNBLOCKED. An
        unspecified block defaults to NONE. An answer the vocabulary does
        not offer is never forced: the ask takes its first legal word and
        the miss fails the pack (self.unoffered).

        A caller that installed its own answerer before the step (the G1
        probe, which shows every ask) keeps it for the asks the step does
        not describe: no map, queue or script word claims them and they are
        not combat declarations (a trigger's target, a may-offer). Before,
        the combat answered those itself, unseen, with their first word: the
        probe showed Feline Sovereign's trigger destroying a target its
        controller was never shown to choose. A pack installs none, so its
        defaults are unchanged."""
        outer = self.ex.decisions.provider
        answers: dict[str, str] = {}
        queues: dict[str, list[str]] = {}
        for key, go in step.get("attack", {}).items():
            # A pack key names the planeswalker the creature attacks
            # (its handle is the ask word); true/false keep their meaning.
            if isinstance(go, str):
                word = str(self.handles[go])
            else:
                word = "ATTACK" if go else "DECLINE"
            answers[f"attack:{self.handles[key]}"] = word
        for key, go in step.get("may", {}).items():
            answers[f"may:{self.handles[key]}"] = "fire" if go else "skip"
        for key, go in step.get("block", {}).items():
            word = "NONE" if go is None else str(self.handles[go])
            answers[f"block:{self.handles[key]}"] = word
        for key, picks in step.get("order", {}).items():
            queues[f"order:{self.handles[key]}"] = [str(p) for p in picks]
        for key, amounts in step.get("trample", {}).items():
            queues[f"trample:{self.handles[key]}"] = [str(a) for a in amounts]
        for key, word in step.get("policy", {}).items():
            answers[f"policy:{self.handles[key]}"] = word
        # A combat step may also carry a generic ``decisions`` script: the
        # ordered words for asks the answer maps do not cover (a dies
        # trigger's TARGET designation). Popped ONLY for sites no map or
        # queue claims.
        script = list(step.get("decisions", ()))

        def answer(vocab, what):
            self.asks_seen.append((what, tuple(vocab)))
            # Handle strings carry a colon ("card:5"), so a site tag is
            # FOUR segments; match the answer keys as longest prefixes.
            got = next(
                (
                    v
                    for k, v in answers.items()
                    if what == k or what.startswith(k + ":")
                ),
                None,
            )
            if got is None:
                for k, q in queues.items():
                    if what == k or what.startswith(k + ":"):
                        got = q.pop(0) if q else vocab[0]
                        break
            if got is None and script:
                got = script.pop(0)
                if got in self.handles:
                    got = str(self.handles[got])
            if got == FIRST_LEGAL:
                got = vocab[0]
            if got is not None and got not in vocab:
                self.unoffered.append(f"{what}: pack word {got!r} not offered in {tuple(vocab)}")
            if got is None:
                if outer is not None and not what.startswith(COMBAT_DECLARATIONS):
                    return outer(vocab, what)
                if what.startswith("may:"):
                    got = "skip"
                elif what.startswith("block:"):
                    got = "NONE"
                elif what.startswith(("order:", "trample:")):
                    got = "0"
                else:
                    got = "DECLINE"
            return got if got in vocab else vocab[0]

        # "respond": {step: [steps]}: the combat stops when that step's players
        # have priority with an empty stack, and those steps run there (an
        # instant after blockers are declared), each ending with both players
        # passing; then the combat goes on.
        self.ex.decisions.provider = answer
        try:
            seat = self.seats[int(step.get("seat", 0))]
            self.ex.combat_attacks(seat)
            for name, responses in step.get("respond", {}).items():
                if self.ex.phase != name:
                    self.ex.pass_until(name)
                if self.ex.phase != name:
                    raise PackError(f"combat: the step {name} never came")
                for inner in responses:
                    self.ex.decisions.provider = None
                    try:
                        self.run_step(inner)
                    finally:
                        self.ex.decisions.provider = answer
            self.ex.combat_blocks(seat)
        finally:
            self.ex.decisions.provider = outer

    def check(self) -> list[str]:
        fails = []
        for seat, life in self.pack.get("expect", {}).get("life", {}).items():
            got = self.world.players[self.seats[int(seat)]].life
            if got != life:
                fails.append(f"life[{seat}]: expected {life}, got {got}")
        for key, zone in self.pack.get("expect", {}).get("zone", {}).items():
            # "ceased": a token that left the battlefield ceased to exist (CR 704.5d);
            # it is in no zone.
            handle = self.handles[key]
            got = self.world.zone_of(handle).kind if handle in self.world.cards else "ceased"
            if got != ZONE_OF_NAME.get(zone, zone):
                fails.append(f"zone[{key}]: expected {zone}, got {got}")
        # The executor's attachment table (aura or equipment -> host), the one
        # IS_ATTACHED_TO_SOURCE reads; null = attached to nothing.
        for key, host in self.pack.get("expect", {}).get("attached", {}).items():
            got_host = self.ex.attachments.get(self.handles[key])
            if got_host != (self.handles[host] if host is not None else None):
                fails.append(f"attached[{key}]: expected {host}, got {got_host}")
        # The executor's phased-out status (CR 702.26).
        for key, want in self.pack.get("expect", {}).get("phased_out", {}).items():
            got_phased = self.handles[key] in self.ex.phased_out
            if got_phased != bool(want):
                fails.append(f"phased_out[{key}]: expected {want}, got {got_phased}")
        # The seat index of the card's effective controller (CR 610.3c; the control
        # overlay included; off the battlefield, its owner).
        for key, want in self.pack.get("expect", {}).get("controller", {}).items():
            got_seat = self.seats.index(self.ex.controller_of(self.handles[key]))
            if got_seat != int(want):
                fails.append(f"controller[{key}]: expected {want}, got {got_seat}")
        # The seat index of every turn begun so far, in order (CR 500.7 extra turns), read
        # off the journal's UPKEEP markers (they carry the active player). The setup's
        # opening begin_turn is the first entry.
        if "turn_seats" in self.pack.get("expect", {}):
            got_seats = [
                self.seats.index(e.data[1])
                for e in self.ex.journal.events
                if e.kind == "TURN_PHASE" and e.data[0] == "UPKEEP"
            ]
            want_seats = list(self.pack["expect"]["turn_seats"])
            if got_seats != want_seats:
                fails.append(f"turn_seats: expected {want_seats}, got {got_seats}")
        want = {
            self.handles[k]: n
            for k, n in self.pack.get("expect", {}).get("damage", {}).items()
        }
        if self.ex.damage != want:
            got = {str(k): v for k, v in self.ex.damage.items()}
            exp = {
                k: n for k, n in self.pack.get("expect", {}).get("damage", {}).items()
            }
            fails.append(f"damage marks: expected {exp}, got {got}")
        expect = self.pack.get("expect", {})
        if "damage_received" in expect:
            received = {}
            for row in self.ex.journal.events:
                if (
                    row.kind == KIND_DAMAGE
                    and row.subject is not None
                    and row.subject.namespace == "card"
                ):
                    received[row.subject] = received.get(row.subject, 0) + row.amount
            for key, amount in expect["damage_received"].items():
                handle = self.handles[key]
                got_amount = received.get(handle, 0)
                if got_amount != amount:
                    fails.append(
                        f"damage_received[{key}]: expected {amount}, got {got_amount}"
                    )
        # The attack record is read from the JOURNAL (DECLARE_ATTACKERS
        # rows of the LAST declare group — journalled truth, not the
        # executor's post-clear memory).
        if "attackers" in expect:
            declares = [
                e for e in self.ex.journal.events if e.kind == "DECLARE_ATTACKERS"
            ]
            group = declares[-1].declare_group if declares else -1
            declared = {e.subject for e in declares if e.declare_group == group}
            by_handle = {h: k for k, h in self.handles.items()}
            got_set = {by_handle.get(h, str(h)) for h in declared}
            for key, on in expect["attackers"].items():
                if (key in got_set) != bool(on):
                    fails.append(
                        f"attackers[{key}]: expected {on}, got {key in got_set}"
                    )
        # The block record is read from the JOURNAL too — the
        # DECLARE_BLOCKERS rows of the LAST declare group (subject = the
        # blocker, data[0] = the attacker it blocked).
        if "blocked" in expect:
            rows = [e for e in self.ex.journal.events if e.kind == "DECLARE_BLOCKERS"]
            group = rows[-1].declare_blockers[1] if rows else -1
            pairs = [
                (e.subject, e.declare_blockers[0])
                for e in rows
                if e.declare_blockers[1] == group
            ]
            by_handle = {h: k for k, h in self.handles.items()}
            got_map: dict[str, list[str]] = {}
            for blocker, attacker in pairs:
                got_map.setdefault(by_handle.get(attacker, str(attacker)), []).append(
                    by_handle.get(blocker, str(blocker))
                )
            for key, want in expect["blocked"].items():
                want_list = sorted(want or [])
                got_list = sorted(got_map.get(key, []))
                if want_list != got_list:
                    fails.append(
                        f"blocked[{key}]: expected {want_list}, got {got_list}"
                    )
        for lane, prefix in (
            ("asks", "attack"),
            ("block_asks", "block"),  # per-blocker declaration asks
            ("policy_asks", "policy"),  # damage-assignment policies
        ):
            for key, vocab in expect.get(lane, {}).items():
                handle = self.handles[key]
                seen = [
                    v for w, v in self.asks_seen if w.startswith(f"{prefix}:{handle}:")
                ]
                if len(seen) != 1:
                    fails.append(
                        f"{lane}[{key}]: expected exactly 1 ask, got {len(seen)}"
                    )
                else:
                    # a vocabulary pin may name PACK KEYS in angle brackets
                    # ("<ogre>,NONE") - the engine's words are handles, and
                    # handles are deterministic per pack card order
                    want = vocab
                    for k, h in self.handles.items():
                        want = want.replace(f"<{k}>", str(h))
                    if ",".join(seen[0]) != want:
                        fails.append(
                            f"{lane}[{key}]: expected {want!r}, got {seen[0]!r}"
                        )
        for lane, prefix in (
            ("not_asked", "attack"),
            ("not_asked_to_block", "block"),
        ):
            for key in expect.get(lane, []):
                handle = self.handles[key]
                if any(w.startswith(f"{prefix}:{handle}:") for w, _ in self.asks_seen):
                    fails.append(f"{lane}[{key}]: the engine asked anyway")
        if "tokens" in expect:  # battlefield TOKEN records by name
            from collections import Counter

            got: Counter = Counter()
            for handle, card in self.world.cards.items():
                if self.world.zone_of(handle).kind != "battlefield":
                    continue
                # Token-ness is read from the IDENTITY first: the executor
                # only mints a handle_record for tokens that carry compiled
                # abilities (a bare 2/2 Knight has none).
                if card.identity.is_token:
                    got[card.identity.name] += 1
                    continue
                rec = self.ex.binder.handle_record.get(handle)
                if rec is not None and rec.is_token:
                    got[card.identity.name] += 1
            for name, n in expect["tokens"].items():
                if got.get(name, 0) != int(n):
                    fails.append(
                        f"tokens[{name}]: expected {n}, got {got.get(name, 0)}"
                    )
        for key, tapped in expect.get("tapped", {}).items():
            got = self.world.cards[self.handles[key]].tapped
            if got != bool(tapped):
                fails.append(f"tapped[{key}]: expected {tapped}, got {got}")
        for seat, size in expect.get("hand", {}).items():
            got = len(self.world.players[self.seats[int(seat)]].zone(ZONE_HAND).entries)
            if got != size:
                fails.append(f"hand[{seat}]: expected {size}, got {got}")
        for seat, want_lost in expect.get("lost", {}).items():
            got_lost = self.seats[int(seat)] in self.ex.lost_players
            if got_lost != bool(want_lost):
                fails.append(f"lost[{seat}]: expected {want_lost}, got {got_lost}")
        # The ADD_MANA totals on PlayerState.mana_pool. Zero-equivalence on
        # both sides: legality.pay_costs DELETES a spent colour from the
        # dict, so an absent key and an explicit 0 assert the same fact.
        for seat, colors in expect.get("mana_pool", {}).items():
            pool = self.world.players[self.seats[int(seat)]].mana_pool
            got_pool = {k: v for k, v in pool.items() if v}
            want_pool = {k: v for k, v in dict(colors).items() if v}
            if got_pool != want_pool:
                fails.append(f"mana_pool[{seat}]: expected {want_pool}, got {got_pool}")
        # The LAST CAST journal row per key: the 6-tuple WAS_KICKED consumes
        # (kicked flag + declared X). A key with no CAST row fails loudly
        # (never a silent False).
        for key, want in expect.get("kick_rows", {}).items():
            handle = self.handles[key]
            rows = [
                e
                for e in self.ex.journal.events
                if e.kind == KIND_CAST and e.subject == handle
            ]
            if not rows:
                fails.append(f"kick_rows[{key}]: no CAST row journalled")
                continue
            _caster, _ord, _kind, _from, got_x, got_kicked = rows[-1].cast
            if "kicked" in want and bool(got_kicked) != bool(want["kicked"]):
                fails.append(
                    f"kick_rows[{key}].kicked: expected {want['kicked']}, "
                    f"got {bool(got_kicked)}"
                )
            if "x" in want and got_x != want["x"]:
                fails.append(f"kick_rows[{key}].x: expected {want['x']}, got {got_x}")
        # kickback_asks: per SEAT, the ordered ANSWERS the pack gave to the
        # engine's pay: tags ("PASS"/"PAY"). Absent, the lane is unchecked; an
        # explicit [] pins "this seat was never asked".
        for seat, wants in expect.get("kickback_asks", {}).items():
            seat_str = str(self.seats[int(seat)])
            got_ans = [
                a
                for (w, _, a) in self.rung1_asks
                # tags are "pay:<seat handle>:<digest>" and the seat Handle
                # str itself carries a colon ("player:1")
                if w.startswith("pay:") and ":".join(w.split(":")[1:3]) == seat_str
            ]
            if got_ans != list(wants):
                fails.append(f"kickback_asks[{seat}]: expected {list(wants)!r}, got {got_ans!r}")
        for key, kinds in expect.get("counters", {}).items():
            got = dict(self.world.cards[self.handles[key]].counters)
            if got != dict(kinds):
                fails.append(f"counters[{key}]: expected {dict(kinds)}, got {got}")
        for lane in ("power", "toughness"):
            idx = 0 if lane == "power" else 1
            for key, want in expect.get(lane, {}).items():
                handle = self.handles[key]
                p, t = self.ex.ledger.effective_pt(
                    self.world.cards[handle].identity,
                    handle,
                    self.world.cards[handle].counters,
                )
                got_pt = (p, t)[idx]
                if got_pt != want:
                    fails.append(f"{lane}[{key}]: expected {want}, got {got_pt}")
        # Battlefield assertions addressed by NAME — creatures and
        # tokens that ARRIVED from an engine effect (a Knight token, a
        # searched land) have no pack key, but their name is printed.
        for lane in ("battlefield_pt", "battlefield_keywords"):
            for name, want in expect.get(lane, {}).items():
                found = [
                    h
                    for h, c in self.world.cards.items()
                    if c.identity.name == name
                    and self.world.zone_of(h).kind == ZONE_BATTLEFIELD
                ]
                if len(found) != 1:
                    fails.append(
                        f"{lane}[{name}]: expected 1 on battlefield, got {len(found)}"
                    )
                    continue
                handle = found[0]
                if lane == "battlefield_pt":
                    p, t = self.ex.ledger.effective_pt(
                        self.world.cards[handle].identity,
                        handle,
                        self.world.cards[handle].counters,
                    )
                    if [p, t] != list(want):
                        fails.append(
                            f"{lane}[{name}]: expected {list(want)}, got {[p, t]}"
                        )
                else:
                    got_kw = sorted(
                        k.name
                        for k in (
                            Keyword.FLYING,
                            Keyword.DEFENDER,
                            Keyword.VIGILANCE,
                            Keyword.HASTE,
                            Keyword.REACH,
                            Keyword.TRAMPLE,
                            Keyword.DEATHTOUCH,
                            Keyword.LIFELINK,
                            Keyword.FIRST_STRIKE,
                            Keyword.DOUBLE_STRIKE,
                            Keyword.INDESTRUCTIBLE,
                        )
                        if self.ex.layers.keyword_of(handle, k)
                    )
                    if got_kw != sorted(want):
                        fails.append(
                            f"{lane}[{name}]: expected {sorted(want)}, got {got_kw}"
                        )
        for lane, zk in (("library", ZONE_LIBRARY), ("graveyard", ZONE_GRAVEYARD)):
            for seat, names in expect.get(lane, {}).items():
                zone = self.world.players[self.seats[int(seat)]].zone(zk)
                order = [self.world.cards[h].identity.name for h in zone.entries]
                if lane == "library":
                    order = list(reversed(order))  # TOP first (draw pops last)
                    # A "*" entry matches ANY name at that position —
                    # the slot order a mandated shuffle leaves unknown
                    # (CR 701.21: the SET is still exactly asserted).
                    ok = len(order) == len(names) and all(
                        w == "*" or w == g for w, g in zip(names, order)
                    )
                    if not ok:
                        fails.append(f"library[{seat}]: expected {names}, got {order}")
                elif sorted(order) != sorted(names):
                    fails.append(
                        f"graveyard[{seat}]: expected {sorted(names)}, got {sorted(order)}"
                    )
        return fails


# A pack's eval_reclassification is a registered fail, never a silent exemption: it must
# carry a triage verdict and a reason (un-triaged reclassifications hide engine bugs).
RECLASS_VERDICTS = (
    "true-no-decision",
    "engine-semantics-gap",
    "null-degenerate-observable",
)


def _triage_check(pack: dict) -> list[str]:
    bad: list[str] = []
    decls = [("pack", pack.get("eval_reclassification"))]
    for i, step in enumerate(pack.get("steps", [])):
        decls.append((f"step {i}", step.get("eval_reclassification")))
    for where, decl in decls:
        if decl is None:
            continue
        if not isinstance(decl, dict):
            bad.append(
                f"{where}: eval_reclassification needs {{reason, verdict}} — "
                f"bare strings are un-triaged (verdicts: {RECLASS_VERDICTS})"
            )
            continue
        if decl.get("verdict") not in RECLASS_VERDICTS:
            bad.append(
                f"{where}: eval_reclassification verdict {decl.get('verdict')!r} "
                f"not in {RECLASS_VERDICTS}"
            )
        reasons = [decl.get("reason", ""), *decl.get("by_ask_kind", {}).values()]
        if not any(str(r).strip() for r in reasons):
            bad.append(f"{where}: eval_reclassification needs a non-empty reason")
    return bad


class _Lanes(dict):
    """A pack's expect block that records which lanes the runner reads. A lane it never reads
    is a typo or a check that does not exist, and the pack would pass without testing it."""

    def __init__(self, lanes: dict) -> None:
        super().__init__(lanes)
        self.read: set[str] = set()

    def __getitem__(self, key):
        self.read.add(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self.read.add(key)
        return super().get(key, default)

    def __contains__(self, key) -> bool:
        self.read.add(key)
        return super().__contains__(key)


def run_pack(path: Path, supply) -> list[str]:
    pack = json.loads(path.read_text())
    bad = _triage_check(pack)
    if bad:
        return bad
    lanes = pack["expect"] = _Lanes(pack.get("expect", {}))
    errors = _run_pack(pack, supply)
    unread = sorted(set(lanes) - lanes.read)
    return errors + ([f"expect lanes this runner never checks: {unread}"] if unread else [])


def _run_pack(pack: dict, supply) -> list[str]:
    try:
        runner = ScenarioRunner(pack, supply)
    except PackError as e:
        return [f"setup: {e}"]
    except Exception as e:  # noqa: BLE001
        # a pool/attach failure is that pack's result, not a crash of the whole sweep
        return [f"setup: {type(e).__name__}: {e}"]
    for step in pack["steps"]:
        want = step.get("expect_raise")
        try:
            runner.run_step(step)
        except GameOver:
            # A player lost at a state-based-action check (CR 704.5a/b): the
            # game is over, so no later step can happen. "lost" checks who.
            break
        except Exception as e:
            if want is None:
                return [f"step {step}: {type(e).__name__}: {e}"]
            # A step whose REFUSAL is the assertion —
            # an illegal activation must raise a CLEAN legality error
            # (refusal), not an engine crash. The substring names the
            # refusal class; the exception type is checked too.
            if want not in f"{type(e).__name__}: {e}":
                return [
                    f"step {step}: expected raise {want!r}, got {type(e).__name__}: {e}"
                ]
            continue
        if want is not None:
            return [f"step {step}: expected raise {want!r}, but it succeeded"]
    try:
        errors = runner.check()
    except Exception as e:  # noqa: BLE001 - one pack's check never aborts the sweep
        errors = [f"check: {type(e).__name__}: {e}"]
    return errors + runner.unoffered


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--dir", default=str(REPO / "tools" / "scenarios"))
    args = ap.parse_args(argv)
    packs = sorted(Path(args.dir).glob("*.json"))
    if not packs:
        print(f"error: no packs in {args.dir}", file=sys.stderr)
        return 2
    # A pack may name its own set with a top-level "set" key; the default
    # is M21. Supplies are compiled once per set.
    supplies: dict[str, object] = {}

    def supply_for(code: str):
        if code not in supplies:
            supplies[code] = get_supply("all", code)
        return supplies[code]

    failures = 0
    for path in packs:
        try:
            set_code = str(json.loads(path.read_text()).get("set", "M21"))
        except (OSError, ValueError):
            set_code = "M21"  # run_pack reports the malformed pack itself
        fails = run_pack(path, supply_for(set_code))
        if fails:
            failures += 1
            print(f"FAIL {path.name}")
            for line in fails:
                print(f"     {line}")
        else:
            print(f"PASS {path.name}")
    print(f"{len(packs) - failures}/{len(packs)} packs passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
