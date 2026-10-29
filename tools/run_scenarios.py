#!/usr/bin/env python3
"""Round-16a validation-pack runner (BINDING plan §16a, R16-1).

A pack is a SMALL deterministic world-script: a handful of cards, one or
two scripted engine actions, and a post-condition block. It is the
executable form of "show me the rules interaction actually works" —
scenario packs prove the 16a behaviours end to end through the REAL
executor (compiled trigger IR included), not just the unit fixtures.

Usage:
    .venv/bin/python tools/run_scenarios.py [--dir tools/scenarios]

Exit code 0 = every pack passed. A failing expect prints the pack, the
key and observed-vs-expected — nothing else.

Pack vocabulary (all keys required as noted):
  world   : {"life": int, "seed": int}
  cards   : [{"key": str, "zone": "hand"|"battlefield"|"library"|"graveyard"
                    |"exile", "controller": 0|1,
              "real": "<pool card name>"  OR  "<compiled token name>"
                                            (r24a: a token golden — "Treasure"
                                            — addressed by name through the
                                            pool fallback; is_token records
                                            only), OR
              "name"/"power"/"toughness"/"type" (synthetic)}]
  mana    : {"0": {"G": 5}, ...}            optional, per seat index
  steps   : [{"op": "deal_damage"|"fight", "source": key, "target": key
              [, "amount": int]},
             {"op": "cast", "real": name, "x": int?, "targets": [key...],
              "decisions": [str...]},
             {"op": "end_turn"} | {"op": "advance_turn"},
             {"op": "enter", "key": k}      hand -> battlefield (journalled:
                                            the sickness clock sees it),
             {"op": "play", "key": k}       17a: the REAL land drop (CR
                                            305.1, legality + once-per-
                                            turn + EtBState entry hook),
             {"op": "enter"|"enchant"|"play", ...,
              "decisions": [str...]}         17a: ordered words the step's
                                            asks consume (scry, modes,
                                            may-offers); never forces a
                                            word the vocabulary lacks,
             {"op": "enchant", "aura": k, "host": k}   the 13c attach edge
                                            (16e: restores a battlefield-
                                             declared aura the setup CR
                                             704.5q sweep already buried,
                                             then attaches via the real
                                             API — journalled re-entry
                                             RE-REGISTERS its static),
             {"op": "loyalty", "key": k, "set": n}    seed the loyalty ledger,
             {"op": "activate", "key": k, "idx": i,   the folded ACTIVATE
              "seat": 0|1, "targets": [k...],         move (legality+pay+run),
              "decisions": [str...], "x": int?},      x: the announced X of an
                                            X-cost activation (CR 602.2b);
                                            absent, the X ask takes a word
             {"op": "combat", "seat": 0|1, "attack": {key: bool},
              "may": {key: bool},
              "block": {blockerKey: attackerKey|null}, 16c per-blocker pick
              "order": {attackerKey: [slot...]},        16c order asks
              "trample": {attackerKey: [amount...]},    16c excess asks
              "policy": {attackerKey: "UNBLOCKED"|
                                  "AS_BLOCKED"}}        16c Herald policy
                                            the whole COMBAT phase; the
                                            ask provider answers ONLY from
                                            these maps (C15 narrowing is
                                            the engine's, and recorded;
                                            an unspecified block is NONE)]
  expect  : {"life": {"0": int...}, "zone": {key: zone...},
              "damage": {key: int...},      — damage is the 16a mark ledger
              "damage_received": {key: int...}, — historical card DAMAGE rows
                                         summed (survives cleanup; subset lane)
              "attackers": {key: bool},     — the DECLARE_ATTACKERS rows,
             "blocked": {key: [blockerKey...]} — the DECLARE_BLOCKERS rows
                                        of the last group (16c),
             "asks": {key: "ATTACK,DECLINE"},  — vocab per attack site,
             "block_asks": {key: "a,b,NONE"},— vocab per 16c block site,
             "policy_asks": {key: "..."},    — vocab per policy ask,
             "not_asked": [key...],        — creatures never asked,
             "not_asked_to_block": [key],  — never offered a block ask,
             "tokens": {Name: n},          — battlefield token records
             "tapped": {key: bool},
             "attached": {key: hostKey|null},  B-49 follow-up #2: the attachment table
             "hand": {"0": int},
             "mana_pool": {"0": {"W": 1}},  r24a: the PlayerState.mana_pool
                                            totals (frozen _v_add_mana write;
                                            zero-equivalence both sides)
             "kick_rows": {key: {"kicked": bool, "x": int|null}},
                                        ZND-1g: the LAST CAST journal row of
                                        the key's card (the same 6-tuple
                                        WAS_KICKED reads: paid flag + the
                                        declared X). A never-cast key FAILS
                                        loudly — no row, no silent False.
             "counters": {key: {"KIND": n}},  17a: the counter table,
             "power": {key: int},             17a: ledger effective_pt,
             "toughness": {key: int},         17a: (base->timestamp fold),
             "library": {"0": [names...TOP-first]},   17a: exact order,
             "graveyard": {"0": [names...]},          17a: exact bag
             "turn_seats": [0, 0, 1]}  2026-10-29: the seat of every turn
                                        begun, in order (CR 500.7 extra turns)
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
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.events import KIND_CAST, KIND_DAMAGE
from MTG_bot.core.executor.games import get_supply, identity_of
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
    "library": ZONE_LIBRARY,  # 17a: search/tutor assertions
}
UNIV = FAnd(())


class PackError(Exception):
    pass


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


class ScenarioRunner:
    def __init__(self, pack: dict, supply, setup_provider=None):
        self.pack = pack
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
        for card in pack["cards"]:
            if "real" in card:
                record = None
                for oid, meta in supply.metas.items():
                    if meta.name == card["real"]:
                        record = supply.pool.results[oid].card
                        break
                if record is None:
                    # r24a TOKEN-GOLDEN LANE (treasure_token_activation):
                    # token identities are compiled golden rows, never dealt
                    # pool METAS (the keyless-mint law's other face —
                    # supply('all') filters is_token out of metas at
                    # games.compile_supply). A metas miss therefore falls
                    # back to the compiled TOKEN record by name. Only
                    # is_token records qualify: the lane never fakes or
                    # substitutes a printed identity, and the golden's REAL
                    # oracle_id is what binder.attach_pool files under
                    # ``records`` and what legality.spell_record reads — so
                    # the pack-keyed token carries the SAME compiled
                    # ActivatedAbility the engine's own mints carry.
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
                    # tools/cards probe board (2026-10-29): optional colour and printed keywords
                    # for synthetic cards; absent keys are the dataclass defaults (byte-identical).
                    colors=tuple(card.get("colors", ())),
                    keywords=tuple(card.get("keywords", ())),
                )
            zone = ZONE_OF_NAME[card.get("zone", "battlefield")]
            self.handles[card["key"]] = self.world.add_card(
                identity, self.seats[card["controller"]], zone
            )
            # tools/cards probe board: a permanent that starts tapped. Not "tapped": eight packs
            # carry a "tapped" key this runner never honoured (B-63), and honouring it changes them.
            if card.get("start_tapped"):
                self.world.cards[self.handles[card["key"]]].tapped = True
        # The real cards' triggers/abilities register from the compiled pool.
        self.registered = self.ex.attach_pool(supply.pool)
        for seat, colors in pack.get("mana", {}).items():
            for color, n in colors.items():
                self.world.players[self.seats[int(seat)]].mana_pool[color] = n
        # 16b: the clock opens for REAL (begin_turn: draw, markers,
        # ledger) — a faked turn desynced world.turn and the sickness
        # clock against advance_turn. The old fakes turn_open/phase
        # manually, which every combat pack now outgrows.
        # tools/cards probe (2026-10-29): a card pre-placed on the battlefield can trigger at this
        # first begin_turn (an upkeep or beginning-of-turn trigger) before any step installs an
        # answerer; a caller may pass one for setup. None keeps every pack byte-identical.
        self.ex.decisions.provider = setup_provider
        try:
            self.ex.begin_turn(self.p0)
        finally:
            self.ex.decisions.provider = None
        # 16b: the combat rig — asks the engine actually made, and
        # libraries deep enough for real begin_turn/advance_turn draws.
        self.asks_seen: list[tuple[str, tuple[str, ...]]] = []
        # Rung-1 (2026-10-05): every response-window / kickback ask the
        # engine made, as (tag, vocab, ANSWER) triples — the expect lanes
        # window_asks / kickback_asks / window_vocab read these.
        self.rung1_asks: list[tuple[str, tuple[str, ...], str]] = []
        # 2026-10-08 library-top knob: the filler below always lands ON TOP
        # of a pack's typed library cards, so library-peek/scry asks would
        # present opaque "Library N" strings as their candidates — the §10
        # BLINDNESS the T4 audit flags. A pack that sets
        # ``"world": {"library_top": true}`` re-raises its OWN library-zone
        # cards above the filler after the filler is dealt (relative order
        # preserved). Packs without the key are byte-identical.
        filler = []
        for seat_idx in (0, 1):
            for i in range(6):
                filler.append(
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
                )
        if pack.get("world", {}).get("library_top"):
            for key, handle in self.handles.items():
                if self.world.zone_of(handle).kind != ZONE_LIBRARY:
                    continue
                if handle in filler:  # cannot happen (keys only name pack cards)
                    continue
                pl = self.world.players[self.world.controller_of(handle)]
                entries = pl.zone(ZONE_LIBRARY).entries
                entries.remove(handle)
                entries.append(handle)

    def run_step(self, step: dict) -> None:
        if step.get("decisions") and step["op"] != "combat":
            # 17a: the decision channel — a non-combat step (an ETB that
            # scrys, a mode choice, a may-offer) carries the ordered words
            # its asks consume, IN ARRIVAL ORDER. A word the vocabulary
            # does not carry is never forced: the provider takes the
            # engine's own first legal word (C15 narrowing respected).
            queue = list(step["decisions"])

            def prov(vocab, what):
                self.asks_seen.append((what, tuple(vocab)))
                rung1 = what.startswith(("counter:", "pay:", "cw:"))
                # Rung-1: the queue is the step's DECLARATION lane. A
                # window/kickback ask whose word the queue does not reach
                # takes the disciplined default "PASS" (queue exhaustion
                # never crashes a window — the pack that wants another
                # answer says so with a word).
                got = queue.pop(0) if queue else ("PASS" if rung1 else vocab[0])
                if got in self.handles:
                    # 18b: a DESIGNATION answer may be given as a PACK KEY
                    # ("sheep", not "card:1") — resolved to the handle
                    # string the vocabulary actually carries. Pack-card
                    # order is deterministic, so the pin stays replay-exact
                    # and the pack says WHO, not an accident of numbering.
                    got = str(self.handles[got])
                answer = got if got in vocab else ("PASS" if rung1 else vocab[0])
                if rung1:
                    self.rung1_asks.append((what, tuple(vocab), answer))
                return answer

            self.ex.decisions.provider = prov
            try:
                self._dispatch(step)
            finally:
                self.ex.decisions.provider = None
            return
        if step["op"] != "combat":
            # Rung-1 quiet lane: a step WITHOUT a decisions queue still
            # answers response-window and kickback asks with PASS (the
            # window is not the pack's declaration lane). Every OTHER ask
            # raises the engine's OWN exhaustion message verbatim — the
            # 339 semantics (silence on unprimed asks) are byte-preserved.
            def quiet(vocab, what):
                self.asks_seen.append((what, tuple(vocab)))
                if what.startswith(("counter:", "pay:", "cw:")):
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
            targets = [self.handles[k] for k in step.get("targets", ())]
            # r22b: a cast step's "player:N" decision token is a PLAYER
            # designation for the spell's target slot. The ASK channel never
            # answers CAST-time multi-candidate targeting (that stays loud by
            # harness policy), so the token lifts straight into the explicit
            # target list — the pack says WHO, seat-indexed.
            for tok in step.get("decisions", ()):
                if isinstance(tok, str) and tok.startswith("player:"):
                    targets.append(self.seats[int(tok.split(":", 1)[1])])
            cast(
                self.ex,
                self.seats[step.get("controller", 0)],
                self.handles[spell_key],
                x=step.get("x"),
                kicked=bool(step.get("kicked", False)),
                targets=tuple(targets),
                decisions=tuple(step.get("decisions", ())),
            )
        elif op == "end_turn":
            self.ex.end_turn()
        elif op == "advance_turn":
            self.ex.advance_turn()
        elif op == "play":
            # 17a: the REAL land drop (CR 305.1) — legality re-check,
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
            self.ex.execute(
                _atom(
                    Verb.MOVE_ZONE,
                    cards=Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        UNIV,
                        zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),),
                    ),
                    destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                    tapped_on_enter=bool(step.get("tapped", False)),
                ),
                source=handle,
                controller=self.world.controller_of(handle),
                bindings={"cards": handle},
            )
        elif op == "enchant":
            # 16e: a pack that DECLARES an aura on the battlefield meets the
            # CR 704.5q unattached-aura SBA at setup (begin_turn's settle):
            # the sweep graves the aura and terminal-expires its static
            # layer, so the old raw-dict write attached a graveyard ghost.
            # Restore the aura through the world, journal the move so the
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
            # r19c (Capture Sphere): on_events only QUEUES; the aura's own
            # "When this Aura enters the battlefield, tap enchanted
            # creature" EtB sat pending forever. Drain like the activate op
            # — static-grant auras (the four green enchant packs) have no
            # EtB trigger and stay byte-unchanged; the attachment is
            # already in the table when the trigger RESOLVES, so the
            # "enchanted creature" selector reads the fresh host.
            self.ex.fire_triggers()
        elif op == "loyalty":
            # harness ledger write: seed the CR 606.3 loyalty counter so a
            # minus ability with a big cost (Herald's -7) is payable.
            handle = self.handles[step["key"]]
            self.world.cards[handle].counters["LOYALTY"] = int(step["set"])
        elif op == "life":
            # r20c (Speaker of the Heavens) harness ledger write (same
            # convention as the loyalty seed): set a seat's life directly.
            # The LIFE_LEAD_OVER_START_GE lane reads current life minus the
            # executor's starting-life snapshot, so this is the honest
            # setup for a "gained N since the start" scenario without
            # dragging a whole healing spell into the pack.
            seat = self.seats[int(step["seat"])]
            self.world.players[seat].life = int(step["set"])
        elif op == "activate":
            from MTG_bot.core.executor.legality import activate

            activate(
                self.ex,
                self.handles[step["key"]],
                int(step.get("idx", 0)),
                seat=self.seats[int(step.get("seat", 0))],
                targets=tuple(self.handles[k] for k in step.get("targets", ())),
                decisions=tuple(step.get("decisions", ())),
                # 2026-10-29 activation X lane (CR 602.2b -> 601.2b): an explicit
                # announcement; absent, X is asked through the decision channel.
                x=step.get("x"),
            )
            self.ex.fire_triggers()
        elif op == "combat":
            self._combat(step)
        else:
            raise PackError(f"unknown op {op!r}")

    def _resolve_word(self, word: str) -> str:
        """18b pack-key resolution, RUNG-2-extended: a word (or either
        side of a ``card@target`` composite) given as a PACK KEY resolves
        to the handle string the vocabulary actually carries; the seat
        literals ``p0``/``p1`` resolve to the player handles (a "any
        target" instant's vocabulary legitimately names players)."""
        if word in self.handles:
            return str(self.handles[word])
        if word in ("p0", "p1"):
            return str(self.seats[int(word[1])])
        card, sep, target = word.partition("@")
        if sep:
            return f"{self._resolve_word(card)}@{self._resolve_word(target)}"
        return word

    def _combat(self, step: dict) -> None:
        """Run the whole COMBAT phase answering the engine's asks from the
        pack's answer maps ONLY. Site tags carry handles (attack:<card>:
        <turn>, may:<card>); a DECLINE the engine does not offer (a C15
        narrowed mandate) is no answer at all — the provider then takes
        the first legal word, which is exactly ATTACK.
        16c lanes: ``block`` maps a blocker key to the attacker key it
        picks (or "NONE"); ``order`` maps an attacker key to the list of
        positional picks its ordering asks consume in slot order;
        ``trample`` maps an attacker key to the list of excess amounts its
        recipient asks consume in order (the player takes the rest);
        ``policy`` maps an attacker key to AS_BLOCKED/UNBLOCKED. An un-
        specified block defaults to NONE (the pre-16c combat packs stay
        byte-identical), and an answer the narrowed vocabulary does not
        carry is never forced."""
        answers: dict[str, str] = {}
        queues: dict[str, list[str]] = {}
        for key, go in step.get("attack", {}).items():
            answers[f"attack:{self.handles[key]}"] = "ATTACK" if go else "DECLINE"
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
        # r22a: a combat step may also carry a generic ``decisions``
        # script — the ordered words for asks the answer maps do not
        # cover (a dies-trigger's TARGET designation now asks, since the
        # own-dies fix). Popped ONLY for sites no map/queue claims, so
        # the pre-existing combat packs (no decisions field) stay
        # byte-identical.
        script = list(step.get("decisions", ()))

        def answer(vocab, what):
            self.asks_seen.append((what, tuple(vocab)))
            # RUNG-2 (2026-10-05): the combat instant window. Its tag
            # (cw:<seat>:<digest>) is claimed by NO answer map, so its
            # scripted words ride the r22a ``decisions`` script IN
            # ARRIVAL ORDER (window asks precede post-damage dies
            # asks); a pack key or a ``key@key`` composite resolves
            # through _resolve_word, and an unreached word defaults to
            # the disciplined "PASS" — queue exhaustion never crashes a
            # window, and the old combat packs (no cw: asks existed)
            # stay byte-identical. Answers are journalled for the
            # combat_window_asks / combat_window_vocab expect lanes.
            if what.startswith("cw:"):
                got = self._resolve_word(script.pop(0)) if script else "PASS"
                if got not in vocab:
                    got = "PASS"
                self.rung1_asks.append((what, tuple(vocab), got))
                return got
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
            if got is None:
                if what.startswith("may:"):
                    got = "skip"
                elif what.startswith("block:"):
                    got = "NONE"
                elif what.startswith(("order:", "trample:")):
                    got = "0"
                else:
                    got = "DECLINE"
            return got if got in vocab else vocab[0]

        self.ex.decisions.provider = answer
        try:
            self.ex.combat_step(self.seats[int(step.get("seat", 0))])
        finally:
            self.ex.decisions.provider = None

    def check(self) -> list[str]:
        fails = []
        for seat, life in self.pack.get("expect", {}).get("life", {}).items():
            got = self.world.players[self.seats[int(seat)]].life
            if got != life:
                fails.append(f"life[{seat}]: expected {life}, got {got}")
        for key, zone in self.pack.get("expect", {}).get("zone", {}).items():
            got = self.world.zone_of(self.handles[key]).kind
            if got != ZONE_OF_NAME[zone]:
                fails.append(f"zone[{key}]: expected {zone}, got {got}")
        # B-49 follow-up #2 ATTACHED LANE: the executor's attachment table (aura or equipment
        # -> host), the one IS_ATTACHED_TO_SOURCE reads; null = attached to nothing.
        for key, host in self.pack.get("expect", {}).get("attached", {}).items():
            got_host = self.ex.attachments.get(self.handles[key])
            if got_host != (self.handles[host] if host is not None else None):
                fails.append(f"attached[{key}]: expected {host}, got {got_host}")
        # 2026-10-29 TURN_SEATS LANE (CR 500.7 extra turns): the seat index of every turn
        # begun so far, in order, read off the journal's UPKEEP markers (they carry the
        # active player). The setup's opening begin_turn is the first entry.
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
        # 16b: the attack record is read from the JOURNAL (DECLARE_ATTACKERS
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
        # 16c: the block record is read from the JOURNAL too — the
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
            ("block_asks", "block"),  # 16c per-blocker declaration asks
            ("policy_asks", "policy"),  # 16c Herald assignment policies
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
        if "tokens" in expect:  # 16c: battlefield TOKEN records by name
            from collections import Counter

            got: Counter = Counter()
            for handle, card in self.world.cards.items():
                if self.world.zone_of(handle).kind != "battlefield":
                    continue
                # 17a: token-ness is read from the IDENTITY first — the
                # executor only mints a handle_record for tokens that
                # carry compiled abilities (a bare 2/2 Knight has none),
                # so the record-only read missed real tokens.
                if getattr(card.identity, "is_token", False):
                    got[card.identity.name] += 1
                    continue
                rec = self.ex.binder.handle_record.get(handle)
                if rec is not None and getattr(rec, "is_token", False):
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
        # r24a MANA-POOL LANE (treasure_token_activation; the gap documented
        # since chromatic_orrery's note): assert the ADD_MANA totals directly
        # on PlayerState.mana_pool — the frozen totals write _v_add_mana is,
        # not the 13b segment mirror. ZERO-EQUIVALENCE both sides: a spent
        # colour is DELETED from the dict by legality.pay_costs, so an
        # absent key and an explicit 0 assert the same fact.
        for seat, colors in expect.get("mana_pool", {}).items():
            pool = self.world.players[self.seats[int(seat)]].mana_pool
            got_pool = {k: v for k, v in pool.items() if v}
            want_pool = {k: v for k, v in dict(colors).items() if v}
            if got_pool != want_pool:
                fails.append(f"mana_pool[{seat}]: expected {want_pool}, got {got_pool}")
        # ZND-1g KICK_ROWS LANE: read the LAST CAST journal row per key — the
        # exact 6-tuple WAS_KICKED consumes (kicked flag + declared X). Proves
        # an X-kicker cast journalled BOTH the paid kick and its X
        # announcement, and an un-kicked cast journalled kicked=False. A key
        # with no CAST row fails loudly (never a silent False).
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
        # Rung-1 lanes (2026-10-05 response-window arc) ----------------------
        # window_asks / kickback_asks: per SEAT, the ordered ANSWERS the
        # pack gave to the engine's counter:/pay: tags (a pack key names
        # the counter spell; "PASS"/"PAY" are literals). window_vocab: the
        # ordered VOCABULARIES of the counter: asks. Absent lanes are
        # unchecked; an explicit [] pins "this seat was never asked".
        want_tag = {
            lane: prefix
            for lane, prefix in (
                ("window_asks", "counter:"),
                ("kickback_asks", "pay:"),
                # RUNG-2: the combat instant window's audit lanes — the
                # same shape, the cw: lane's own prefix.
                ("combat_window_asks", "cw:"),
            )
        }
        for lane, prefix in want_tag.items():
            for seat, wants in expect.get(lane, {}).items():
                seat_str = str(self.seats[int(seat)])
                got_ans = [
                    a
                    for (w, _, a) in self.rung1_asks
                    # tags are "<kind>:<seat handle>:<digest>" and the
                    # seat Handle str itself carries a colon ("player:1")
                    if w.startswith(prefix) and ":".join(w.split(":")[1:3]) == seat_str
                ]
                want_ans = [self._resolve_word(w) for w in wants]
                if got_ans != want_ans:
                    fails.append(
                        f"{lane}[{seat}]: expected {want_ans!r}, got {got_ans!r}"
                    )
        if "window_vocab" in expect:
            want_vocab = [
                [self._resolve_word(t) for t in vocab]
                for vocab in expect["window_vocab"]
            ]
            got_vocab = [
                list(v) for (w, v, _) in self.rung1_asks if w.startswith("counter:")
            ]
            if got_vocab != want_vocab:
                fails.append(
                    f"window_vocab: expected {want_vocab!r}, got {got_vocab!r}"
                )
        if "combat_window_vocab" in expect:
            # RUNG-2: ordered vocabularies of the cw: asks; every token
            # is a "card@target" composite, pack keys resolvable both
            # sides.
            want_vocab = [
                [self._resolve_word(t) for t in vocab]
                for vocab in expect["combat_window_vocab"]
            ]
            got_vocab = [
                list(v) for (w, v, _) in self.rung1_asks if w.startswith("cw:")
            ]
            if got_vocab != want_vocab:
                fails.append(
                    f"combat_window_vocab: expected {want_vocab!r}, got {got_vocab!r}"
                )
        # 17a lanes ------------------------------------------------------------
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
        # 17a: battlefield assertions addressed by NAME — creatures and
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
                            # r21a: INDESTRUCTIBLE added (Basri Ket +1 grant);
                            # no existing green pack asserts it, vocab is
                            # report-only so widening is additive.
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
                    # 17a: a "*" entry matches ANY name at that position —
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


# FAIL-REGISTERED convention (owner 2026-10-07): a reclassification is a
# REGISTERED FAIL, never a silent exemption — every eval_reclassification
# must carry a triage verdict plus evidence, and it stays counted in the
# puzzle_cert summary (fail_registered). Un-triaged reclassifications are
# how engine bugs hid (the 2026-10-07 feat_of_resistance false-premise audit).
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


def run_pack(path: Path, supply) -> list[str]:
    pack = json.loads(path.read_text())
    bad = _triage_check(pack)
    if bad:
        return bad
    try:
        runner = ScenarioRunner(pack, supply)
    except PackError as e:
        return [f"setup: {e}"]
    except Exception as e:  # noqa: BLE001 — r22a: audit-dir robustness
        # a pool/attach
        # failure is that pack's result, not a crash of the whole sweep.
        return [f"setup: {type(e).__name__}: {e}"]
    for step in pack["steps"]:
        want = step.get("expect_raise")
        try:
            runner.run_step(step)
        except Exception as e:
            if want is None:
                return [f"step {step}: {type(e).__name__}: {e}"]
            # C5 negative packs: a step whose REFUSAL is the assertion —
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
    return runner.check()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--dir", default=str(REPO / "tools" / "scenarios"))
    args = ap.parse_args(argv)
    packs = sorted(Path(args.dir).glob("*.json"))
    if not packs:
        print(f"error: no packs in {args.dir}", file=sys.stderr)
        return 2
    # ZND-1e: packs name their OWN set with a top-level "set" key
    # (ZNR kicker packs); the default stays the M21 supply every existing
    # pack ran on, byte-identically. Supplies are compiled once per set.
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
