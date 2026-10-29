"""The deciding-seat hook on the decision channel (added 2026-10-24).

A provider used to receive only ``(vocab, what)``, which cannot name the decider. EachPlayer re-asks
the SAME ``may:<source>`` tag once per player (``executor/__init__.py:986-995``), so a per-seat
router reading tags would hand player 1's choice to player 0, and the eval rig's tag parser falls
back to the active player when it cannot tell (``tools/eval/gameplay_eval_v2.py:150-157``).
``DecisionStream.asking_seat`` carries the seat for the duration of the provider call only. It is
never logged, so no replay or fingerprint moves.
"""

from __future__ import annotations

import unittest
from collections import Counter

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    EachPlayer,
    OptionalEffect,
    QConst,
    Selector,
    SelectorMode,
    Verb,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.decisions import DecisionStream
from MTG_bot.core.executor.games import (
    RandomPolicy,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
    identity_of,
)
from MTG_bot.core.executor.legality import activate
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND, GameWorld
from MTG_bot.core.test_executor_binding import card_id, reset_oracle_ids

#: Tags whose second field IS the deciding player.
SEAT_IN_TAG = {"cw", "counter", "pay", "scry", "sacrifice", "discard"}
#: Combat tags whose object is the deciding player's creature.
CREATURE_IN_TAG = {"attack", "block", "order", "trample"}


def _tag_handle(what: str) -> Handle:
    parts = what.split(":")
    return Handle(parts[1], int(parts[2]))


class StreamHookTest(unittest.TestCase):
    def setUp(self) -> None:
        world = GameWorld(num_players=2, start_life=20, master_seed=1)
        self.p0, self.p1 = world.player_order
        self.stream = DecisionStream()

    def test_seat_is_visible_only_during_the_provider_call(self) -> None:
        seen: list[Handle | None] = []

        def provider(vocab: tuple[str, ...], _what: str) -> str:
            seen.append(self.stream.asking_seat)
            return vocab[0]

        self.stream.provider = provider
        self.assertEqual(self.stream.take(("a", "b"), "x", seat=self.p1), "a")
        self.assertEqual(seen, [self.p1])
        self.assertIsNone(self.stream.asking_seat)
        self.assertEqual(self.stream.ask_log, [("x", "a")])  # unchanged shape: no seat

    def test_seat_is_reset_when_the_provider_raises(self) -> None:
        def provider(_vocab: tuple[str, ...], _what: str) -> str:
            raise RuntimeError("agent died")

        self.stream.provider = provider
        with self.assertRaises(RuntimeError):
            self.stream.take(("a", "b"), "x", seat=self.p0)
        self.assertIsNone(self.stream.asking_seat)

    def test_nested_ask_restores_the_outer_seat(self) -> None:
        trail: list[Handle | None] = []

        def provider(vocab: tuple[str, ...], what: str) -> str:
            trail.append(self.stream.asking_seat)
            if what == "outer":
                self.stream.take(("y",) * 2, "inner", seat=self.p1)
                trail.append(self.stream.asking_seat)
            return vocab[0]

        self.stream.provider = provider
        self.stream.take(("a", "b"), "outer", seat=self.p0)
        self.assertEqual(trail, [self.p0, self.p1, self.p0])

    def test_primed_answers_never_reach_the_provider(self) -> None:
        self.stream.provider = lambda _vocab, _what: self.fail("provider called")
        self.stream.push(("a", "b"), "x", "b")
        self.assertEqual(self.stream.take(("a", "b"), "x", seat=self.p0), "b")
        self.assertIsNone(self.stream.asking_seat)


class EachPlayerSeatTest(unittest.TestCase):
    def test_identical_tags_carry_different_seats(self) -> None:
        # The case a tag parser cannot solve: one `may:` tag, two deciders.
        supply = get_supply("all")
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=5)
        executor = Executor(world)
        executor.attach_pool(supply.pool)
        p0, p1 = world.player_order
        anchor = world.add_card(card_id("Seat Anchor"), p0, ZONE_BATTLEFIELD)
        asks: list[tuple[str, Handle | None]] = []

        def provider(vocab: tuple[str, ...], what: str) -> str:
            asks.append((what, executor.decisions.asking_seat))
            return "fire" if "fire" in vocab else vocab[0]

        executor.decisions.provider = provider
        gain = Atom(
            verb=Verb.GAIN_LIFE,
            args=AtomArgs(pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)))),
        )
        executor.apply_effect(
            EachPlayer(ref=ControllerRef.ANY, effect=OptionalEffect(gain)),
            source=anchor,
            controller=p0,
        )
        self.assertEqual(len(asks), 2)
        self.assertEqual(asks[0][0], asks[1][0])  # the same tag twice
        self.assertEqual([seat for _, seat in asks], [p0, p1])  # ...asked of different seats
        self.assertEqual((world.players[p0].life, world.players[p1].life), (21, 21))


class _SeatRecordingPolicy(RandomPolicy):
    def __init__(self, seed: int, executor: Executor) -> None:
        super().__init__(seed)
        self.executor = executor
        self.asks: list[tuple[str, Handle | None]] = []

    def answer(self, vocab: tuple[str, ...], what: str) -> str:
        self.asks.append((what, self.executor.decisions.asking_seat))
        return super().answer(vocab, what)


class RandomGameRoutingTest(unittest.TestCase):
    def test_every_provider_ask_in_real_games_names_the_right_seat(self) -> None:
        supply = get_supply("all")
        kinds: Counter[str] = Counter()
        for seed in (3, 4, 5, 6):
            game = _setup_game(seed, supply, deal_decks(seed, 1409, supply))
            policy = _SeatRecordingPolicy(seed, game.executor)
            try:
                _play(game, policy, game.world.player_order, turn_cap=12)
            except Exception:  # noqa: BLE001 - a crash is a separate finding; asks so far still count
                pass
            for what, seat in policy.asks:
                kind = what.split(":", 1)[0]
                kinds[kind] += 1
                self.assertIsNotNone(seat, f"{what}: no deciding seat")
                assert seat is not None
                self.assertEqual(seat.namespace, "player", what)
                if kind in SEAT_IN_TAG:
                    self.assertEqual(str(_tag_handle(what)), str(seat), what)
                elif kind in CREATURE_IN_TAG:
                    self.assertEqual(game.executor.controller_of(_tag_handle(what)), seat, what)
        self.assertGreater(sum(kinds.values()), 0)
        self.assertIn("attack", kinds)


def test_no_engine_call_site_passes_seat_to_take_decision() -> None:
    # Four tools/training modules replace ExecCtx.take_decision process-wide at import with the
    # old (self, vocab, what) signature (BACKLOG B-35). A caller passing seat= then raises
    # TypeError, but only in processes that imported one of them. That is how a scry site
    # passing seat= went green in `pytest MTG_bot` and red in `pytest tools` (2026-10-24).
    # Static and import-free on purpose: importing those modules here would patch the engine for
    # every later test in this run.
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent
    offenders = []
    for path in sorted(root.rglob("*.py")):
        if path.name.startswith("test_"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "take_decision"
                and any(k.arg == "seat" for k in node.keywords)
            ):
                offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    assert offenders == [], offenders


# --------------------------------------------------------------------------------------------------
# V10 (2026-10-29): the player the rules say decides is the one asked, also when it is not the
# controller of the ability. Real M21 cards, a seat recorded per ask.
# --------------------------------------------------------------------------------------------------


class DeciderRoutingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.supply = get_supply("all")
        self.world = GameWorld(num_players=2, start_life=20, master_seed=11)
        self.ex = Executor(self.world)
        self.ex.attach_pool(self.supply.pool)
        self.p0, self.p1 = self.world.player_order
        self.asks: list[tuple[str, tuple[str, ...], Handle | None]] = []
        self.answers: dict[str, list[str]] = {}

    def real(self, name: str, seat: Handle, zone: str) -> Handle:
        for oid, meta in self.supply.metas.items():
            if meta.name == name:
                return self.world.add_card(identity_of(self.supply.pool.results[oid].card), seat, zone)
        raise KeyError(name)

    def synth(self, name: str, seat: Handle, zone: str) -> Handle:
        return self.world.add_card(card_id(name, "2", "2"), seat, zone)

    def answer_with(self, *handles: Handle) -> None:
        queue = [str(h) for h in handles]

        def provider(vocab: tuple[str, ...], what: str) -> str:
            self.asks.append((what, vocab, self.ex.decisions.asking_seat))
            pick = next((h for h in queue if h in vocab), vocab[0])
            if pick in queue:
                queue.remove(pick)
            return pick

        self.ex.decisions.provider = provider

    def zone(self, handle: Handle) -> str:
        return self.world.zone_of(handle).kind

    def test_each_opponent_sacrifices_asks_the_opponent(self) -> None:
        # Goremand: "When this creature enters, each opponent sacrifices a creature."
        self.ex.begin_turn(self.p0)
        self.real("Goremand", self.p0, ZONE_BATTLEFIELD)
        fodder = self.synth("Fodder", self.p0, ZONE_BATTLEFIELD)
        big = self.synth("Big", self.p1, ZONE_BATTLEFIELD)
        small = self.synth("Small", self.p1, ZONE_BATTLEFIELD)
        gore = self.real("Goremand", self.p0, ZONE_HAND)
        self.world.players[self.p0].mana_pool.update({"B": 6})
        self.answer_with(fodder, small)
        cast(self.ex, self.p0, gore)
        self.assertEqual(self.zone(small), ZONE_GRAVEYARD)
        self.assertEqual(self.zone(big), ZONE_BATTLEFIELD)
        edict = [(what, seat) for what, _v, seat in self.asks if what.startswith(f"sacrifice:{self.p1}:")]
        self.assertEqual(len(edict), 1, self.asks)
        self.assertEqual(edict[0][1], self.p1)

    def test_target_player_discards_asks_that_player(self) -> None:
        # Mind Rot: "Target player discards two cards." CR 701.9b.
        self.ex.begin_turn(self.p0)
        keep, toss1, toss2 = (self.synth(n, self.p1, ZONE_HAND) for n in ("Keep", "Toss1", "Toss2"))
        rot = self.real("Mind Rot", self.p0, ZONE_HAND)
        self.world.players[self.p0].mana_pool.update({"B": 3})
        self.answer_with(toss1, toss2)
        cast(self.ex, self.p0, rot)
        self.assertEqual([self.zone(h) for h in (keep, toss1, toss2)], [ZONE_HAND, ZONE_GRAVEYARD, ZONE_GRAVEYARD])
        self.assertEqual([seat for _w, _v, seat in self.asks], [self.p1, self.p1])
        self.assertTrue(all(w.startswith(f"discard:{self.p1}:") for w, _v, _s in self.asks), self.asks)
        self.assertEqual(self.asks[0][1], tuple(str(h) for h in sorted((keep, toss1, toss2))))

    def test_each_player_discards_in_apnap_order(self) -> None:
        # Liliana, Waker of the Dead +1 on player 1's turn: each player discards a card of their
        # choice, the active player first (CR 101.4); nobody who discarded loses life.
        self.ex.begin_turn(self.p1)
        lil = self.real("Liliana, Waker of the Dead", self.p1, ZONE_BATTLEFIELD)
        mine = [self.synth(n, self.p0, ZONE_HAND) for n in ("A0", "B0")]
        theirs = [self.synth(n, self.p1, ZONE_HAND) for n in ("A1", "B1")]
        self.answer_with(theirs[1], mine[1])
        activate(self.ex, lil, 0, seat=self.p1)
        self.assertEqual([seat for _w, _v, seat in self.asks], [self.p1, self.p0])
        self.assertEqual([self.zone(h) for h in mine + theirs], [ZONE_HAND, ZONE_GRAVEYARD, ZONE_HAND, ZONE_GRAVEYARD])
        self.assertEqual((self.world.players[self.p0].life, self.world.players[self.p1].life), (20, 20))

    def test_who_cant_reads_the_hand_before_the_discard(self) -> None:
        # "Each opponent who can't loses 3 life": an opponent who discards their last card can.
        self.ex.begin_turn(self.p0)
        lil = self.real("Liliana, Waker of the Dead", self.p0, ZONE_BATTLEFIELD)
        last = self.synth("Last", self.p1, ZONE_HAND)
        self.answer_with()
        activate(self.ex, lil, 0, seat=self.p0)
        self.assertEqual(self.zone(last), ZONE_GRAVEYARD)
        self.assertEqual(self.world.players[self.p1].life, 20)
        self.assertEqual(self.asks, [])  # one card each at most: nothing to choose

    def test_target_opponent_sacrifices_of_their_choice(self) -> None:
        # Run Afoul: the target opponent picks among their own fliers; the caster's flier is not
        # in the menu, and the player designation never stands in for a creature (B-53).
        self.ex.begin_turn(self.p0)
        from dataclasses import replace as _replace

        def flier(name: str, seat: Handle) -> Handle:
            identity = _replace(card_id(name, "2", "2"), keywords=("FLYING",))
            return self.world.add_card(identity, seat, ZONE_BATTLEFIELD)

        mine, big, small = flier("Mine", self.p0), flier("Big", self.p1), flier("Small", self.p1)
        afoul = self.real("Run Afoul", self.p0, ZONE_HAND)
        self.world.players[self.p0].mana_pool.update({"G": 1})
        self.answer_with(small)
        cast(self.ex, self.p0, afoul)
        self.assertEqual([self.zone(h) for h in (mine, big, small)], [ZONE_BATTLEFIELD, ZONE_BATTLEFIELD, ZONE_GRAVEYARD])
        self.assertEqual([(w.split(":")[0], s) for w, _v, s in self.asks], [("sacrifice", self.p1)])
        self.assertEqual(self.asks[0][1], tuple(str(h) for h in sorted((big, small))))

    def test_a_sacrifice_menu_without_an_owner_raises(self) -> None:
        # CR 701.21a: a menu over two players' creatures does not say who sacrifices.
        from MTG_bot.core.executor.legality import ctx_for
        from MTG_bot.core.executor.selectors import resolve_selector
        from MTG_bot.core.test_executor_binding import BF_ANY, CREATURE

        src = self.synth("Source", self.p0, ZONE_BATTLEFIELD)
        self.synth("Other", self.p1, ZONE_BATTLEFIELD)
        ctx = ctx_for(self.ex, source=src, controller=self.p0)
        sel = Selector(QConst(1), SelectorMode.CHOOSE, CREATURE, zones=(BF_ANY,))
        with self.assertRaises(ValueError):
            resolve_selector(sel, ctx, ask_choose=True, sacrifice=True)

    def test_take_decision_of_names_the_decider_and_restores_the_controller(self) -> None:
        from MTG_bot.core.executor.legality import ctx_for

        src = self.synth("Source", self.p0, ZONE_BATTLEFIELD)
        ctx = ctx_for(self.ex, source=src, controller=self.p0)
        seen: list[tuple[Handle | None, Handle]] = []

        def provider(vocab: tuple[str, ...], _what: str) -> str:
            seen.append((self.ex.decisions.asking_seat, ctx.controller))
            return vocab[1]

        self.ex.decisions.provider = provider
        self.assertEqual(ctx.take_decision_of(self.p1, ("a", "b"), "x"), "b")
        self.assertEqual(seen, [(self.p1, self.p1)])
        self.assertEqual(ctx.controller, self.p0)
        # The per-op pool still answers first, and the controller comes back even on a raise.
        ctx.decisions, ctx.decision_idx = ("a",), 0
        self.assertEqual(ctx.take_decision_of(self.p1, ("a", "b"), "y"), "a")
        self.ex.decisions.provider = None
        with self.assertRaises(ValueError):
            ctx.take_decision_of(self.p1, ("a", "b"), "z")
        self.assertEqual(ctx.controller, self.p0)

    def test_the_controllers_own_sacrifice_menu_asks_the_controller(self) -> None:
        # "Sacrifice a creature" as an effect: the controller's own menu, under the sacrifice kind.
        from MTG_bot.core.ability_tree import FAnd, FAtom, FAtomPred, Zone, ZoneKind

        src = self.real("Goremand", self.p1, ZONE_BATTLEFIELD)  # a card source the menu excludes
        a, b = self.synth("A", self.p0, ZONE_BATTLEFIELD), self.synth("B", self.p0, ZONE_BATTLEFIELD)
        menu = FAnd((FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                     FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)))

        sac = Atom(verb=Verb.SACRIFICE, args=AtomArgs(pairs=(("target", Selector(
            QConst(1), SelectorMode.CHOOSE, menu, zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),))),)))
        self.answer_with(b)
        self.ex.apply_effect(sac, source=src, controller=self.p0)
        self.assertEqual([self.zone(h) for h in (a, b)], [ZONE_BATTLEFIELD, ZONE_GRAVEYARD])
        self.assertEqual([(w.split(":")[:3], s) for w, _v, s in self.asks], [(["sacrifice", "player", "0"], self.p0)])

    def test_sacrifice_another_creature_is_the_controllers_choice(self) -> None:
        # Dire Fleet Warmonger: "you may sacrifice another creature". FNot(IS_SOURCE) is "another",
        # a real menu, not self-reference: the controller picks (it used to be the lowest handle).
        from MTG_bot.core.ability_tree import (
            FAnd,
            FAtom,
            FAtomPred,
            FNot,
            Zone,
            ZoneKind,
        )

        src = self.synth("Source", self.p0, ZONE_BATTLEFIELD)
        a, b = self.synth("A", self.p0, ZONE_BATTLEFIELD), self.synth("B", self.p0, ZONE_BATTLEFIELD)
        menu = FAnd((FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                     FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                     FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE))))
        sac = Atom(verb=Verb.SACRIFICE, args=AtomArgs(pairs=(("target", Selector(
            QConst(1), SelectorMode.CHOOSE, menu, zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),))),)))
        self.answer_with(b)
        self.ex.apply_effect(sac, source=src, controller=self.p0)
        self.assertEqual([self.zone(h) for h in (src, a, b)], [ZONE_BATTLEFIELD, ZONE_BATTLEFIELD, ZONE_GRAVEYARD])
        self.assertEqual(self.asks[0][1], tuple(str(h) for h in sorted((a, b))))
        self.assertEqual(self.asks[0][2], self.p0)
