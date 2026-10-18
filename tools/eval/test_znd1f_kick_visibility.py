"""ZND-1f gates (/102 binding spec): the kicker decision is MODEL-VISIBLE.

Pins, in spec order:
* decision 1/3: the rig menu presents BOTH priced rows, base before
  kicked, tokens ``card:N`` / ``card:N+kick`` (the un-kicked dedupe
  regression dies here — before ZND-1f the kicked row vanished);
* decision 4: token -> row round-trip resolves the suffix to the row's
  ``kicked`` flag, and the cast lane journals the paid kick;
* decision 2 (§10 grounding): the kicked candidate's WORD SPAN differs
  from the base span and carries the kicker-cost words; the base span is
  byte-UNCHANGED (additive-only, §8);
* collector: candidate strings distinguish the pair and ``chosen_idx``
  stays consistent once the strings differ (recording flows automatically);
* data availability: a RandomPolicy episode on a rigged pool actually
  contains a kicked cast (the cast lane carries the chosen row's flag);
* determinism: the same rigged episode run twice records identically.
"""

from __future__ import annotations

import unittest

import pytest

from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import Game, RandomPolicy, get_supply, identity_of
from MTG_bot.core.executor.query import legal_casts
from MTG_bot.core.state import ZONE_HAND, GameWorld
from tools.eval.gameplay_eval_v2 import PolicyActDriver
from tools.training import bc_data_v2, collector
from tools.training.ab_duel import _cards_rows_of
from tools.training.bc_data_v2 import cand_words_v2
from tools.training.collector import AskContext, EpisodeCollector

SUPPLY = get_supply("engine", "ZNR")
ROOST = "Roost of Drakes"  # printed {U}, kicker {2}{U} (ZND-1e's pin card)


# ------------------------------------------------------------------ rigging
def _record_named(name: str):
    for oid, meta in SUPPLY.metas.items():
        if meta.name == name:
            return SUPPLY.pool.results[oid].card
    raise AssertionError(f"{name!r} not in the compiled pool")


def _rigged_game(seed: int = 3):
    """Bare world: Roost in p0's hand, 4U in pool (both totals payable),
    FIRST_MAIN of the active player."""
    world = GameWorld(num_players=2, start_life=20, master_seed=seed)
    executor = Executor(world)
    executor.attach_pool(SUPPLY.pool)
    p0, _p1 = world.player_order
    world.active_player = p0
    executor.turn_open = True
    executor.phase = "FIRST_MAIN"
    handle = world.add_card(identity_of(_record_named(ROOST)), p0, ZONE_HAND)
    world.players[p0].mana_pool.clear()
    world.players[p0].mana_pool["U"] = 4
    game = Game(executor=executor, seed=seed, pool_mode="engine")
    return game, p0, handle


def _restock(game: Game, seat, handle):
    game.world.add_card(identity_of(_record_named(ROOST)), seat, ZONE_HAND)
    game.world.players[seat].mana_pool.clear()
    game.world.players[seat].mana_pool["U"] = 4
    return handle


class Scripted:
    """Ask policy: answers the index of the token ``pick`` names."""

    def __init__(self, pick) -> None:
        self.pick = pick

    def decide(self, ctx: AskContext) -> int:
        return self.pick(list(ctx.candidates))


def _journal_kicked_casts(executor: Executor):
    return [e for e in executor.journal.events if e.kind == "CAST" and e.data[-1]]


@pytest.fixture()
def rig():
    return _rigged_game()


# ---------------------------------------------------- menu / round-trip lane
def test_menu_emits_both_rows_base_first(rig) -> None:
    game, p0, handle = rig
    driver = PolicyActDriver(1, {0: Scripted(lambda m: 0), 1: Scripted(lambda m: 0)})
    menu, rows = driver._menu(game, p0)
    base, kick = str(handle), str(handle) + bc_data_v2.KICK_SUFFIX
    assert base in menu and kick in menu, menu  # dedupe regression dies
    assert menu.index(base) < menu.index(kick)  # decision 3: base first
    # token -> row round-trip (decision 4): the suffix resolves to the row
    assert rows[base][1].kicked is False
    assert rows[kick][1].kicked is True
    assert rows[kick][1].handle == rows[base][1].handle


def test_unsupported_kicker_card_shows_no_kick_token(rig) -> None:
    # anti-phantom (decision 5): a row legality did NOT emit is never
    # synthesized — starve the pool so only the base total is payable.
    game, p0, handle = rig
    game.world.players[p0].mana_pool["U"] = 1
    driver = PolicyActDriver(1, {0: Scripted(lambda m: 0), 1: Scripted(lambda m: 0)})
    menu, _rows = driver._menu(game, p0)
    assert str(handle) in menu
    assert str(handle) + bc_data_v2.KICK_SUFFIX not in menu


# ----------------------------------------------------- span / grounding lane
def test_kicked_span_differs_and_grounds_the_cost(rig) -> None:
    game, p0, handle = rig
    driver = PolicyActDriver(1, {0: Scripted(lambda m: 0), 1: Scripted(lambda m: 0)})
    driver.game_ref = game
    menu, rows = driver._menu(game, p0)
    obs = driver._act_obs(game, rows)
    base, kick = str(handle), str(handle) + bc_data_v2.KICK_SUFFIX

    cost_words = bc_data_v2.kicker_cost_words(game.executor, handle)
    assert cost_words, "the compiled KickerAbility cost must be readable"
    assert obs["_kick"][kick] == cost_words  # inert grounding table shipped

    ground = bc_data_v2.ground_with(_cards_rows_of(obs), "act:main", menu)
    spans = {tok: cand_words_v2(tok, ground[i]) for i, tok in enumerate(menu)}
    assert spans[base] != spans[kick]
    # base span UNCHANGED vs HEAD: the same card-row ref grounding the rig
    # lane has always produced (_cards exists in snapshot_obs since v2).
    expect_base = cand_words_v2(
        base, [[str(handle), str(game.world.cards[handle].identity.name)]]
    )
    assert spans[base] == expect_base
    assert "kick" in spans[kick]
    assert set(cost_words) <= set(spans[kick])  # §10: the cost is VISIBLE


def test_card_row_lookup_recorder_lane(rig) -> None:
    game, _p0, handle = rig
    world = game.executor.world
    plain = bc_data_v2.card_row_lookup(world)
    tok = str(handle)
    base_row = plain(tok)
    cost_words = bc_data_v2.kicker_cost_words(game.executor, handle)

    def kick_words(handle_str: str) -> list[str]:
        return bc_data_v2.kicker_cost_words(
            game.executor, next(h for h in world.cards if str(h) == handle_str)
        )

    grounded = bc_data_v2.card_row_lookup(world, kick_words)
    kick_row = grounded(tok + bc_data_v2.KICK_SUFFIX)
    assert base_row is not None and kick_row is not None
    assert kick_row[: len(base_row)] == base_row  # referent kept
    assert kick_row[len(base_row)] == "kick"
    cost_words = bc_data_v2.kicker_cost_words(game.executor, handle)
    assert kick_row[len(base_row) + 1 :] == cost_words and cost_words
    # a suffixed token for an UNKNOWN handle stays ungroundable (no phantom)
    assert grounded("card:999999+kick") is None


# ----------------------------------------------------------- recording lanes
def _scripted_rig_episode(seed: int = 5):
    """One act: the scripted agent picks the +kick token; the recorder
    books the ask exactly as the rig's ``book`` does."""
    game, p0, handle = _rigged_game(seed)
    kick = str(handle) + bc_data_v2.KICK_SUFFIX
    driver = PolicyActDriver(
        seed,
        {
            0: Scripted(lambda m: m.index(kick) if kick in m else m.index("PASS")),
            1: Scripted(lambda m: m.index("PASS")),
        },
    )
    steps: list[tuple] = []
    driver.recorder = lambda seat, vocab, what, idx, obs: steps.append(
        (seat, list(vocab), what, idx)
    )
    driver.take_acts(game, p0)
    return game, driver, steps


def test_rig_episode_records_the_kick_candidate() -> None:
    game, _driver, steps = _scripted_rig_episode()
    acts = [s for s in steps if s[2] == "act:main"]
    assert acts, "the act:main ask must have been booked"
    _seat, cands, _what, idx = acts[0]
    kick = [t for t in cands if t.endswith(bc_data_v2.KICK_SUFFIX)]
    assert kick, f"+kick candidate never reached the recording: {cands}"
    assert len(cands) == len(set(cands))  # candidates distinguish the pair
    chosen = cands[idx]
    assert chosen.endswith(bc_data_v2.KICK_SUFFIX)
    # the cast lane resolved the suffix: the engine journaled a PAID kick
    kicked = _journal_kicked_casts(game.executor)
    assert len(kicked) == 1 and kicked[0].data[-1] is True
    assert chosen[: -len(bc_data_v2.KICK_SUFFIX)] == str(kicked[0].subject)


def test_rig_episode_is_deterministic() -> None:
    a, _da, sa = _scripted_rig_episode()
    b, _db, sb = _scripted_rig_episode()
    assert sa == sb
    assert a.executor.journal.dump() == b.executor.journal.dump()
    assert a.digest == b.digest


def test_collector_records_distinguishing_candidates(monkeypatch) -> None:
    # The provider lane records verbatim candidate strings; once the
    # presenter emits the +kick token, the two rows no longer collapse.
    vocab = ("card:17", "card:17+kick", "PASS")

    def fake_play(game, driver, order, turn_cap) -> None:
        # the real _play activates a seat before the first ask; mirror it
        game.world.active_player = game.world.player_order[0]
        assert driver.answer(vocab, "act:main") == "card:17"

    monkeypatch.setattr(collector, "_play", fake_play)
    col = EpisodeCollector(
        pool_mode="engine",
        turn_cap=3,
        policy="first",
        supply=get_supply("engine", "ZNR"),
    )
    ep = col.run_episode(11)
    step = ep["steps"][0]
    assert step["candidates"] == list(vocab)  # both strings survive, distinct
    assert step["candidates"][step["chosen_idx"]] == "card:17"


# ------------------------------------------------------- data availability
def test_random_policy_episode_contains_a_kick() -> None:
    # (d) on the map: the cast lane must carry the CHOSEN ROW's flag.
    # RandomPolicy picks among ROWS (base + kicked both enumerated),
    # play_cast casts with that row's flag -> a seeded rigged-pool
    # episode journals >=1 kicked cast.
    game, p0, handle = _rigged_game(21)
    policy = RandomPolicy(21)
    rows = legal_casts(game.world, game.executor, p0)
    assert [r.kicked for r in rows if not r.land] == [False, True]  # order
    for _ in range(40):
        _restock(game, p0, handle)
        policy.take_acts(game, p0)
        if _journal_kicked_casts(game.executor):
            return
    raise AssertionError("seeded RandomPolicy never produced a kicked cast")


def test_split_kick_edges() -> None:
    assert bc_data_v2.split_kick("card:17+kick") == ("card:17", True)
    assert bc_data_v2.split_kick("card:17") == ("card:17", False)
    assert bc_data_v2.split_kick("+kick") == ("+kick", False)  # bare suffix
    assert bc_data_v2.split_kick("PASS") == ("PASS", False)
    assert bc_data_v2.kick_token("card:17", False) == "card:17"
    assert bc_data_v2.kick_token("card:17", True) == "card:17+kick"


class TeacherTiebreakTest(unittest.TestCase):
    """Gate blocker pin (/102 gate): the teacher's act-menu preference must
    NOT over-kick. '+kick' sorts lexicographically ABOVE its base handle, so
    the pre-fix max((cmc, h)) key picked the kicked row on EVERY cmc tie —
    order-independently (adversarial probe). Post-fix preference: cmc, then
    UNKICKED, then handle."""

    def _teacher(self):
        from tools.eval.gameplay_eval_v2 import HeuristicTeacher

        return HeuristicTeacher()

    def _act_ctx(self, cands, cmc):
        from tools.training.collector import AskContext

        return AskContext(
            vocab="act:main",
            candidates=cands,
            world={"_cmc": cmc, "_lands": [], "_acts": []},
        )

    def test_tie_prefers_base_over_kicked(self):
        cands = ["PASS", "card:17+kick", "card:17"]  # kicked FIRST — hostile order
        idx = self._teacher().decide(
            self._act_ctx(cands, {"card:17": 3, "card:17+kick": 3})
        )
        self.assertEqual(cands[idx], "card:17")

    def test_cmc_priority_unchanged(self):
        cands = ["PASS", "card:17", "card:7"]
        idx = self._teacher().decide(self._act_ctx(cands, {"card:17": 3, "card:7": 5}))
        self.assertEqual(cands[idx], "card:7")

    def test_kicked_only_candidate_still_selectable(self):
        # base unaffordable but kicked legal (engine could in principle emit
        # only the kicked row — must not become unselectable):
        cands = ["PASS", "card:17+kick"]
        idx = self._teacher().decide(self._act_ctx(cands, {"card:17+kick": 3}))
        self.assertEqual(cands[idx], "card:17+kick")
