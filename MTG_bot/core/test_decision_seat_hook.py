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
    Verb,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.decisions import DecisionStream
from MTG_bot.core.executor.games import RandomPolicy, _play, _setup_game, deal_decks, get_supply
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, GameWorld
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
