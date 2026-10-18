"""Gameplay eval v2 — FULL-AGENT seats (T5-G v2, fixes v1's leverage null).

MECHANISM FINDING (investigated first, file:symbol truth):

1. THE ENGINE DOES ASK THE ACT-SIDE COMBAT DECISIONS — through the very
   same provider lane v1 billed as "ask-only":
     * declare attackers : Executor._declare_attackers (executor/__init__.py:1452)
       site ``attack:<card>:<turn>``, vocab (ATTACK, DECLINE) per legal creature;
     * declare blockers  : Executor._declare_blockers (:1514)
       site ``block:<card>:<turn>``, vocab = legal attacker HANDLE tokens + NONE;
     * damage assignment : Executor._assign_damage (:1730)
       sites ``policy:``/``order:``/``trample:``;
     * combat instants   : stack.open_combat_window (stack.py:652, RUNG-2)
       site ``cw:<seat>:<digest>``, vocab PASS + ``card@target`` tokens.
   v1 therefore already ANSWERED these — but with a SEAT-ATTRIBUTION BUG:
   the v1 provider routed EVERY ask by ``world.active_player``
   (gameplay_eval.py:139). During combat the active player is the ATTACKER,
   so all defender-side asks (blocks, defender cw instants, defender
   damage splits) were answered by the OPPONENT'S policy. The defender
   never played its own defense — one concrete cause of v1's zero leverage.

2. THE REAL SCRIPTED LAYER IS THE RIG, NOT THE ENGINE: the main-phase act
   batch — play which land, cast which spell, activate what, pass — is
   chosen by ``RandomPolicy.take_acts`` / ``pick_spell`` /
   ``select_targets`` (games.py:586/490/442) with the driver's own ``rng``.
   The engine has NO ask site there (no main-phase priority window; the
   query surface ``legal_casts``/``legal_activations`` is only consulted
   by the rig). NAMED ENGINE GAP: ``MTG_bot.core.executor.query.legal_casts
   has no ask-site producer`` — the fix is rig-side (the query surface IS a
   declarative enumeration, so a policy act layer is honest here):
   :class:`PolicyActDriver` below replaces the rng picks with per-seat
   policy asks (handle-token menus the v2 grounding binds to card rows).
   Residual driver heuristics, reported not hidden: mana is auto-tapped
   in full before the menu (no ask for tap AMOUNT), and multi-slot target
   rows keep the parent rng (``select_targets`` fallback).

Seats are full agents on BOTH layers: BC checkpoints via ``BcAsk`` (the
checkpoint vocab already contains site:attack/site:block — packs record
combat asks), and TEACHER-v2 = :class:`HeuristicTeacher`, a deterministic
coded greedy-legal heuristic (attacks unless a pure-loss blocker exists;
blocks by P/T + damage-ratio rules; casts highest-CMC payable; plays a
land every turn; first non-refuse on generic sites) — no oracle, no RNG.

Metrics add to v1: per-ask-KIND profiles BY SEAT (decline rate, v0 rate,
agreement with the heuristic anchor) and a LEVERAGE PROXY: per-turn life
trace -> cumulative damage-differential by round (does skill show as
out-damage BEFORE kills? lead-rate at rounds 4/7/10 + its association
with the eventual winner).

Run::

    .venv/bin/python tools/eval/gameplay_eval_v2.py --games 200 --workers 4
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from MTG_bot.core.executor.games import (
    SET_CODE,
    TURN_CAP,
    RandomPolicy,
    Supply,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
    legal_activations,
    legal_casts,
)
from tools.eval.gameplay_eval import REFUSE_TOKENS, make_eval_policy
from tools.training import bc_data_v2
from tools.training.ab_duel import (
    classify_outcome,
    seat_swaps,
    snapshot_obs,
    wilson,
)
from tools.training.collector import AskContext

DEFAULT_POLICY_A = str(REPO / "tools" / "training" / "bc7_S3_s1_best.pt")
DEFAULT_POLICY_B = str(REPO / "tools" / "training" / "bc7_S3_s3_best.pt")
DEFAULT_OUT = Path(__file__).resolve().parent / "gameplay_eval_v2.json"

V2_REFUSE = REFUSE_TOKENS | {"DECLINE", "NONE"}
#: rounds at which the cumulative damage-differential is sampled
LEAD_ROUNDS = (4, 7, 10)

KIND_DECLINE_WORD = {
    "attack": "DECLINE",
    "block": "NONE",
    "cw": "PASS",
    "act": "PASS",
}


# ----------------------------------------------------- seat attribution
def site_kind(what: str) -> str:
    kind = what.split(":", 1)[0]
    return (
        kind
        if kind in ("attack", "block", "cw", "act", "target")
        else (
            kind
            if kind in ("order", "trample", "policy", "may", "scry", "choose")
            else "other"
        )
    )


def resolve_seat(
    what: str,
    game: Any,
    seats: list[str],
    default_seat: int,
    handle_words: set[str],
) -> int:
    """Which SEAT owns this ask: parse the handle embedded in the engine's
    site tag (``attack:card:0:12`` -> card:0 -> its controller;
    ``cw:player:1:<digest>`` -> the asked seat) and map through the
    16e-effective ``controller_of``. No handle (generic may/scry/choose
    sites) -> the active player, the v1 semantics (correct there)."""
    parts = what.split(":")
    for i in range(len(parts) - 1):
        token = f"{parts[i]}:{parts[i + 1]}"
        if token in handle_words:
            if token.startswith("player:"):
                return seats.index(token)
            try:
                return seats.index(str(game.executor.controller_of(_as_handle(token))))
            except Exception:  # noqa: BLE001 - untraceable controller -> active
                return default_seat
    return default_seat


def _as_handle(token: str) -> Any:
    from MTG_bot.core.identity import Handle

    ns, _, idx = token.partition(":")
    return Handle(ns, int(idx))


# ------------------------------------------------- TEACHER-v2 heuristic
class HeuristicTeacher:
    """Deterministic greedy-legal full-agent (the skill anchor). Reads the
    SAME omniscient snapshot both seats get; codes rule-of-thumb play:
      * attack: unless some untapped enemy creature purely out-trades the
        attacker (toughness > my power AND power >= my toughness) -> ATTACK;
      * block: free kill (I survive, it dies) > block the biggest threat
        when unblocked damage would be lethal > survive-and-prevent;
        never suicide-block -> NONE;
      * act menu: play a land, else cast the highest-CMC payable spell,
        else first activation, else PASS;
      * trample/number surfaces: minimum to blockers (max to the face);
        cw window: cast the first non-PASS option; generic sites: first
        non-refuse word (v1's golden-script lane).
    Evasion/reach/protection and blocker-legality nuances are NOT modelled
    (the vocab is already legality-narrowed by the engine; only the PREFERENCE
    is heuristic)."""

    def __init__(self) -> None:
        self.truncations = 0  # interface parity with BcAsk

    def decide(self, ctx: AskContext) -> int:
        kind = site_kind(ctx.vocab)
        cands = ctx.candidates
        w = ctx.world
        me = w.get("_seat", w.get("active") or 0)
        foe = 1 - me
        pt = w.get("_pt", {})

        def power(h: str) -> int:
            return int(pt.get(h, [0, 0])[0] or 0)

        def tough(h: str) -> int:
            return int(pt.get(h, [0, 0])[1] or 0)

        if kind == "attack" and "ATTACK" in cands and "DECLINE" in cands:
            mine = ctx.vocab.split(":")[1:3]
            me_h = f"{mine[0]}:{mine[1]}" if len(mine) > 1 else ""
            p, t = power(me_h), tough(me_h)
            board = w["battlefield"][foe] if "battlefield" in w else []
            for row in board:
                h = row[0]
                if "tapped" in row:
                    continue
                if tough(h) > p and power(h) >= t:
                    return cands.index("DECLINE")
            return cands.index("ATTACK")
        if kind == "block" and "NONE" in cands:
            parts = ctx.vocab.split(":")
            me_h = f"{parts[1]}:{parts[2]}"
            p, t = power(me_h), tough(me_h)
            my_life = w["lives"][me] if "lives" in w else 20
            attackers = [c for c in cands if c != "NONE"]
            lethal = any(power(a) >= my_life for a in attackers)
            free = [a for a in attackers if t > power(a) and p >= tough(a)]
            if free:
                best = max(free, key=lambda a: (tough(a), a))
                return cands.index(best)
            if lethal:
                best = max(attackers, key=lambda a: (t > power(a), power(a), a))
                return cands.index(best)
            survive = [a for a in attackers if t > power(a)]
            if survive:
                best = max(survive, key=lambda a: (power(a), a))
                return cands.index(best)
            return cands.index("NONE")
        if kind == "act":
            cmc = w.get("_cmc", {})
            lands = w.get("_lands", [])
            acts = w.get("_acts", [])
            casts = [c for c in cands if c not in ("PASS", *lands, *acts)]
            if lands:
                return cands.index(lands[0])
            if casts:
                # ZND-1f gate: base-before-kicked in TIE-BREAK too — "+kick"
                # sorts lexicographically ABOVE the base handle, so the bare
                # (cmc, h) key made the teacher always over-kick (gate probe:
                # order-independent). Preference order: cmc, UNKICKED, handle.
                return cands.index(
                    max(
                        casts,
                        key=lambda h: (
                            cmc.get(h, 0),
                            not bc_data_v2.split_kick(h)[1],
                            h,
                        ),
                    )
                )
            if acts:
                return cands.index(acts[0])
            return cands.index("PASS")
        if kind == "cw":
            for i, c in enumerate(cands):
                if c != "PASS":
                    return i
            return 0
        if cands and all(c.lstrip("-").isdigit() for c in cands):
            return min(range(len(cands)), key=lambda i: int(cands[i]))
        for i, cand in enumerate(cands):
            if cand not in V2_REFUSE:
                return i
        return 0


# ------------------------------------------------- policy-driven act layer
class PolicyActDriver(RandomPolicy):
    """The rig-side act-layer upgrade: instead of rng picks, ONE per-seat
    ask per act over the declarative query surface
    ``["PASS"] + land handles + payable-cast handles + activation handles``
    (handle tokens ground to card rows for the v2 model; PASS is the
    trained refuse word). Mana is auto-tapped in full first; single-slot
    targets are asked by handle too; multi-slot rows keep the parent rng.
    Records a per-turn life trace for the leverage proxies."""

    MAX_MANA_TAPS_PER_ACT = 20

    def __init__(self, seed: int, agents: dict[int, Any]) -> None:
        super().__init__(seed)
        self.agents = agents  # seat index -> policy (BcAsk / HeuristicTeacher)
        self.life_trace: list[tuple[int, int, tuple[int, ...]]] = []
        self.game_ref: Any = None
        self.recorder: Any = None  # run_v2_game.book(seat, vocab, what, idx, obs)

    # -- instrumentation hook used by the provider closure
    def ask(self, seat: int, what: str, cands: tuple[str, ...], world_obs: dict) -> int:
        return self.agents[seat].decide(
            AskContext(vocab=what, candidates=cands, world=world_obs)
        )

    def take_acts(self, game: Any, seat: Any) -> None:
        self.game_ref = game
        world = game.executor.world
        seats = [str(s) for s in world.player_order]
        self.life_trace.append(
            (
                world.turn,
                seats.index(str(seat)),
                tuple(world.players[s].life for s in world.player_order),
            )
        )
        self.turn = world.turn
        self.seat_index = world.player_order.index(seat)
        if game.trace is not None:
            game.trace.record_turn(seat)
        for _ in range(self.max_acts):
            if game.over_reason() is not None:
                return
            self._tap_all_mana(game, seat)
            menu, rows = self._menu(game, seat)
            if len(menu) <= 1:  # PASS only
                break
            obs = self._act_obs(game, rows)
            idx = self.agents[self.seat_index].decide(
                AskContext(vocab="act:main", candidates=tuple(menu), world=obs)
            )
            if self.recorder is not None:
                self.recorder(self.seat_index, tuple(menu), "act:main", idx, obs)
            choice = menu[idx]
            if choice == "PASS":
                break
            kind, row = rows[choice]
            if kind == "land":
                self.play_land(game, seat, row)
            elif kind == "cast":
                self.play_cast(game, seat, row)
            else:
                self.play_activation(game, seat, row)
        game.digest.append(f"T{self.turn}.end")

    def _tap_all_mana(self, game: Any, seat: Any) -> None:
        """Heuristic (RESIDUAL GAP, reported): the tap AMOUNT is never an
        engine ask, so the driver fills the pool from every tap-for-mana
        activation before the menu; the pool makes the cast menu honest."""
        executor = game.executor
        world = executor.world
        for _ in range(self.MAX_MANA_TAPS_PER_ACT):
            options = [
                o
                for o in legal_activations(world, executor, seat)
                if (o.source, o.ability_idx) not in game.unsupported_rows
            ]
            taps = self.mana_activations(options)
            if not taps:
                return
            self.play_activation(game, seat, min(taps, key=lambda o: str(o.source)))

    def _menu(
        self, game: Any, seat: Any
    ) -> tuple[list[str], dict[str, tuple[str, Any]]]:
        executor = game.executor
        world = executor.world
        rows = legal_casts(world, executor, seat)
        lands = [r for r in rows if r.land and (r.handle,) not in game.unsupported_rows]
        spells = [
            r for r in rows if not r.land and (r.handle,) not in game.unsupported_rows
        ]
        options = [
            o
            for o in legal_activations(world, executor, seat)
            if (o.source, o.ability_idx) not in game.unsupported_rows
        ]
        others = self.other_activations(options)
        menu = ["PASS"]
        picked: dict[str, tuple[str, Any]] = {}
        for kind, group in (("land", lands), ("cast", spells)):
            for r in group:
                # ZND-1f (/102): both priced rows are presented. The kicked
                # row's token carries the +kick suffix; legality already
                # sorted base-before-kicked (CastOption.order_key), the
                # dedupe below can no longer collapse the pair because the
                # tokens differ. Anti-phantom: rows come from legal_casts
                # only — a kick row is never synthesized here (decision 5).
                tok = bc_data_v2.kick_token(str(r.handle), kind == "cast" and r.kicked)
                if tok not in picked:
                    picked[tok] = (kind, r)
                    menu.append(tok)
        for o in others:
            tok = str(o.source)
            if tok not in picked:
                picked[tok] = ("act", o)
                menu.append(tok)
        return menu, picked

    def _act_obs(self, game: Any, rows: dict[str, tuple[str, Any]]) -> dict[str, Any]:
        """Snapshot for the menu ask: the shared omniscient obs plus the
        private inert keys (underscore-prefixed, never serialized into the
        BC stream — the ``_cards`` precedent) the heuristic reads."""
        world = game.executor.world
        obs = snapshot_obs(world, world.active_player)
        obs["_seat"] = self.seat_index
        obs["_cmc"] = {
            tok: (world.cards[r.handle].identity.cmc or 0)
            if kind != "act" and getattr(r, "handle", None) is not None
            else 0
            for tok, (kind, r) in rows.items()
        }
        obs["_lands"] = [t for t, (k, _) in rows.items() if k == "land"]
        obs["_acts"] = [t for t, (k, _) in rows.items() if k == "act"]
        # ZND-1f (/102 decision 2): static kicker-cost grounding for the
        # +kick tokens in this menu (same static-tree name-bag vocabulary
        # as the option-set rows). Underscore-inert: obs_words never
        # serializes it, so base candidate spans are byte-unchanged.
        # Gate hardening: a presented +kick row with EMPTY grounding words
        # would be exactly the §10 blindness /102 forbids — impossible on
        # every probed pool, so make it loud, never silently under-grounded.
        kick_grounding: dict[str, list[str]] = {}
        for tok, (kind, r) in rows.items():
            if kind == "cast" and r.kicked:
                words = bc_data_v2.kicker_cost_words(game.executor, r.handle)
                if not words:
                    raise AssertionError(
                        f"ZND-1f: +kick candidate {tok} has no kicker-cost "
                        "grounding (would present an ungrounded decision)"
                    )
                kick_grounding[tok] = words
        obs["_kick"] = kick_grounding
        return obs

    # -- single-slot target designation by policy; parent rng fallback
    def select_targets(self, slots: list[Any]) -> Any:
        if (
            len(slots) == 1
            and slots[0].candidates
            and slots[0].min_count <= 1
            and len(slots[0].candidates) <= 8
        ):
            cands = sorted(str(c) for c in slots[0].candidates)
            obs = snapshot_obs(
                self.game_ref.executor.world, self.game_ref.executor.world.active_player
            )
            obs["_seat"] = self.seat_index
            idx = self.agents[self.seat_index].decide(
                AskContext(vocab="target:select", candidates=tuple(cands), world=obs)
            )
            if self.recorder is not None:
                self.recorder(self.seat_index, tuple(cands), "target:select", idx, obs)
            from MTG_bot.core.executor.query import validate_target_selection

            handle = next(c for c in slots[0].candidates if str(c) == cands[idx])
            if validate_target_selection(slots[0], [handle]) is None:
                return (handle,)
        return super().select_targets(slots)


# ------------------------------------------------------------- game runner
def run_v2_game(
    seed: int,
    swap: bool,
    spec_a: str,
    spec_b: str,
    supply: Supply,
    deck_pairs_seed: int = 1409,
    turn_cap: int = TURN_CAP,
    device: str = "cpu",
) -> dict[str, Any]:
    decks = deal_decks(seed, deck_pairs_seed, supply)
    game = _setup_game(seed, supply, decks)
    world = game.world
    seats = [str(s) for s in world.player_order]
    a_seat = 1 if swap else 0
    specs = {a_seat: spec_a, 1 - a_seat: spec_b}
    agents = {
        seat: (
            HeuristicTeacher()
            if specs[seat] == "teacher"
            else make_eval_policy(specs[seat], seed * 2 + seat, device)
        )
        for seat in (0, 1)
    }
    probe = HeuristicTeacher()  # the agreement anchor, evaluated per ask
    stats: dict[str, dict[str, Any]] = {}
    for seat in (0, 1):
        kinds: dict[str, Any] = {}
        stats[str(seat)] = {
            "asks": 0,
            "v0": 0,
            "declines": 0,
            "illegal": 0,
            "model_errors": 0,
            "kinds": kinds,
        }
    handle_words = {str(h) for h in world.cards} | {str(p) for p in world.player_order}
    pt = {
        str(h): [
            world.cards[h].identity.power,
            world.cards[h].identity.toughness,
        ]
        for h in world.cards
    }
    driver = PolicyActDriver(seed, agents)

    def book(seat: int, vocab: tuple[str, ...], what: str, idx: int, obs: dict) -> None:
        """One ask of ANY layer (engine provider lane or the rig act layer)
        into the per-seat per-kind profile, incl. agreement with the probe."""
        st = stats[str(seat)]
        agree = probe.decide(AskContext(vocab=what, candidates=tuple(vocab), world=obs))
        kind = site_kind(what)
        kd = st["kinds"].setdefault(
            kind, {"asks": 0, "v0": 0, "declines": 0, "agree": 0}
        )
        kd["asks"] += 1
        kd["v0"] += int(idx == 0)
        kd["agree"] += int(idx == agree)
        decline_word = KIND_DECLINE_WORD.get(kind)
        declined = (
            vocab[idx] == decline_word if decline_word else vocab[idx] in V2_REFUSE
        )
        kd["declines"] += int(declined)
        st["asks"] += 1
        st["v0"] += int(idx == 0)
        st["declines"] += int(declined)

    def provider(vocab: tuple[str, ...], what: str) -> str:
        active = seats.index(str(world.active_player))
        seat = resolve_seat(what, game, seats, active, handle_words)
        st = stats[str(seat)]
        obs = snapshot_obs(world, world.active_player)
        obs["_seat"] = seat
        obs["_pt"] = pt
        try:
            idx = agents[seat].decide(
                AskContext(vocab=what, candidates=tuple(vocab), world=obs)
            )
        except Exception:
            st["model_errors"] += 1
            raise
        if not 0 <= idx < len(vocab):
            st["illegal"] += 1
            raise ValueError(f"gameplay_eval_v2: index {idx} out of {vocab}")
        book(seat, vocab, what, idx, obs)
        return vocab[idx]

    driver.answer = provider  # type: ignore[method-assign]
    driver.recorder = book
    crash = ""
    crash_tb = ""
    lives_end: tuple[int, ...] = ()
    try:
        _play(game, driver, list(world.player_order), turn_cap)
        reason = game.reason
    except BaseException as error:  # noqa: BLE001 - recorded, never hidden
        import traceback

        frames = traceback.format_exception(error)
        reason = f"crash:{type(error).__name__}: {error}"
        crash = type(error).__name__
        crash_tb = "".join(frames[-4:])  # the tail: failing frames only
    try:
        lives_end = tuple(world.players[s].life for s in world.player_order)
    except Exception:  # noqa: BLE001 - crashed worlds may not read
        lives_end = ()

    stream = game.executor.decisions
    losers = [
        s for s, h in zip(seats, world.player_order, strict=True) if game.is_loser(h)
    ]
    winner = (
        next((s for s in seats if s not in losers), None) if len(losers) == 1 else None
    )
    journal_total, asked_total = len(stream.journal), len(stream.ask_log)
    return {
        "seed": seed,
        "swap": swap,
        "outcome": classify_outcome(reason, winner, seats, a_seat),
        "reason": reason,
        "turns": game.turns,
        "crash": crash or None,
        "crash_tb": crash_tb,
        "illegal": sum(s["illegal"] for s in stats.values()),
        "journal_total": journal_total,
        "ask_log_total": asked_total,
        "auto_resolved": journal_total - asked_total,
        "lives_end": list(lives_end),
        "life_trace": driver.life_trace,
        "seat_stats": {
            str(seat): {
                **{k: v for k, v in stats[str(seat)].items() if k != "kinds"},
                "kinds": stats[str(seat)]["kinds"],
                "trunc": getattr(agents[seat], "truncations", 0),
                # v4: which budget stage actually fired for this seat
                "ctx": dict(getattr(agents[seat], "ctx_stats", {}) or {}),
            }
            for seat in (0, 1)
        },
    }


# ---------------------------------------------------------------- batch
_G: dict[str, Any] = {}


def _init_worker(
    pool_mode: str, set_code: str, specs: tuple[str, ...], device: str
) -> None:
    import torch

    torch.set_num_threads(1)
    _G["supply"] = get_supply(pool_mode, set_code)
    for spec in specs:
        if spec.endswith(".pt"):
            from tools.training.ab_duel import BcAsk

            BcAsk.fresh(spec, device)


def _worker(job: dict[str, Any]) -> dict[str, Any]:
    return run_v2_game(
        job["seed"],
        job["swap"],
        job["spec_a"],
        job["spec_b"],
        supply=_G["supply"],
        deck_pairs_seed=job["deck_pairs_seed"],
        turn_cap=job["turn_cap"],
        device=job["device"],
    )


# ------------------------------------------------------------ leverage
def _cum_damage(trace: list, seat: int, n_players: int = 2) -> dict[int, int]:
    """cumulative damage the seat HAS DEALLED by the start of each of ITS
    OWN turns: 20 minus the opponent's life observed just before the seat's
    next act batch (the opponent's life can only fall on the seat's own
    acts+combat or the opponent's own self-inflicted costs — an accepted
    proxy, effect-life-loss included)."""
    own = [rec for rec in trace if rec[1] == seat]
    opp_idx = 1 - seat
    out: dict[int, int] = {}
    for r, rec in enumerate(own, start=1):
        out[r] = max(0, 20 - rec[2][opp_idx])
    return out


def _side_view(records: list[dict], side: str) -> dict[str, Any]:
    agg: dict[str, Any] = {
        "asks": 0,
        "v0": 0,
        "declines": 0,
        "illegal": 0,
        "model_errors": 0,
        "trunc": 0,
    }
    kinds: dict[str, dict[str, float]] = {}
    for r in records:
        for seat in ("0", "1"):
            is_a = (r["swap"] and seat == "1") or (not r["swap"] and seat == "0")
            if ("a" if is_a else "b") != side:
                continue
            st = r["seat_stats"][seat]
            for k in ("asks", "v0", "declines", "illegal", "model_errors", "trunc"):
                agg[k] += st[k]
            for kind, kd in st["kinds"].items():
                kd_agg = kinds.setdefault(
                    kind, {"asks": 0, "v0": 0, "declines": 0, "agree": 0}
                )
                for k in kd_agg:
                    kd_agg[k] += kd[k]
    n = agg["asks"]
    agg["v0_rate"] = round(agg["v0"] / n, 4) if n else 0.0
    agg["decline_rate"] = round(agg["declines"] / n, 4) if n else 0.0
    for kd in kinds.values():
        k = kd["asks"]
        kd["v0_rate"] = round(kd["v0"] / k, 4) if k else 0.0
        kd["decline_rate"] = round(kd["declines"] / k, 4) if k else 0.0
        kd["agree_heur_rate"] = round(kd["agree"] / k, 4) if k else 0.0
        del kd["agree"], kd["v0"], kd["declines"]
    agg["per_kind"] = kinds
    return agg


def _leverage(records: list[dict]) -> dict[str, Any]:
    """Does skill show BEFORE kills? Per-round damage differential and the
    association between mid-game out-damage and the eventual winner."""
    played = [r for r in records if r["outcome"] != "crash" and r["life_trace"]]
    out: dict[str, Any] = {"rounds": {}}
    leads: dict[int, list[int]] = {r: [] for r in LEAD_ROUNDS}
    win_when_lead: dict[int, list[int]] = {r: [] for r in LEAD_ROUNDS}
    final_diff = []
    for r in played:
        trace = r["life_trace"]
        dmg_a_by, dmg_b_by = (_cum_damage(trace, 0), _cum_damage(trace, 1))
        if r["swap"]:
            dmg_a_by, dmg_b_by = dmg_b_by, dmg_a_by
        for rd in LEAD_ROUNDS:
            da = max((dmg_a_by.get(k, 0) for k in range(1, rd + 1)), default=0)
            db = max((dmg_b_by.get(k, 0) for k in range(1, rd + 1)), default=0)
            leads[rd].append(int(da > db))
            if r["outcome"] in ("a", "b"):
                win_when_lead[rd].append(int((da > db) == (r["outcome"] == "a")))
        if len(r["lives_end"]) == 2:
            # damage dealt by side a = 20 - life of the seat that is NOT a
            a_seat = 1 if r["swap"] else 0
            opp_seat = 1 - a_seat
            da_f = max(0, 20 - r["lives_end"][opp_seat])
            db_f = max(0, 20 - r["lives_end"][a_seat])
            final_diff.append(da_f - db_f)
    for rd in LEAD_ROUNDS:
        n = len(leads[rd]) or 1
        ww = win_when_lead[rd]
        out["rounds"][str(rd)] = {
            "policy_lead_rate": round(sum(leads[rd]) / n, 4),
            "lead_predicts_win_rate": round(sum(ww) / len(ww), 4) if ww else None,
            "n_decisive": len(ww),
        }
    if final_diff:
        out["final_dmg_diff_mean"] = round(sum(final_diff) / len(final_diff), 2)
        out["n"] = len(final_diff)
    return out


def summarize_matchup(records: list[dict], spec_a: str, spec_b: str) -> dict:
    n = len(records)
    wins = sum(1 for r in records if r["outcome"] == "a")
    losses = sum(1 for r in records if r["outcome"] == "b")
    draws = {
        kind.split("-", 1)[1]: sum(1 for r in records if r["outcome"] == kind)
        for kind in ("draw-stall", "draw-cap", "draw-other")
    }
    crashes = sum(1 for r in records if r["outcome"] == "crash")
    decisive = wins + losses
    played = [r for r in records if r["outcome"] != "crash"]
    lo, hi = wilson(wins, decisive) if decisive else (0.0, 1.0)
    return {
        "games": n,
        "policy": spec_a,
        "baseline": spec_b,
        "policy_wins": wins,
        "policy_losses": losses,
        "draws": draws,
        "crashes": crashes,
        "decisive_rate": round(decisive / n, 4) if n else 0.0,
        "winrate_decisive": round(wins / decisive, 4) if decisive else 0.0,
        "wilson_decisive": [round(lo, 4), round(hi, 4)],
        "avg_turns_played": round(sum(r["turns"] for r in played) / len(played), 2)
        if played
        else 0.0,
        "illegal_action_attempts": sum(r["illegal"] for r in records),
        "engine_exceptions": crashes,
        "exception_types": sorted({r["crash"] for r in records if r["crash"]}),
        "model_errors": sum(
            s["model_errors"] for r in records for s in r["seat_stats"].values()
        ),
        "asks_presented": sum(r["journal_total"] for r in records),
        "asks_answered": sum(r["ask_log_total"] for r in records),
        "asks_auto_resolved": sum(r["auto_resolved"] for r in records),
        "seat_swap_games": sum(1 for r in records if r["swap"]),
        "policy_asks": _side_view(records, "a"),
        "baseline_asks": _side_view(records, "b"),
        "leverage": _leverage(records),
    }


def _print_table(out: dict) -> None:
    head = (
        f"{'matchup':<22}{'G':>4}{'W':>4}{'D':>4}{'L':>4}{'X':>3}"
        f"{'wr':>7}{'ci95':>16}{'turns':>7}{'ill':>5}{'dmgdiff':>8}"
        f"{'lead@7':>7}{'pred':>6}"
    )
    print(head)
    print("-" * len(head))
    for name, m in out["matchups"].items():
        draws = sum(m["draws"].values())
        ci = f"[{m['wilson_decisive'][0]:.3f},{m['wilson_decisive'][1]:.3f}]"
        lev = m["leverage"]
        lead7 = lev["rounds"]["7"]["policy_lead_rate"]
        pred = lev["rounds"]["7"]["lead_predicts_win_rate"]
        print(
            f"{name:<22}{m['games']:>4}{m['policy_wins']:>4}{draws:>4}"
            f"{m['policy_losses']:>4}{m['crashes']:>3}"
            f"{m['winrate_decisive']:>7.3f}{ci:>16}"
            f"{m['avg_turns_played']:>7.1f}{m['illegal_action_attempts']:>5}"
            f"{lev.get('final_dmg_diff_mean', 0.0):>8.2f}{lead7:>7.3f}"
            f"{pred if pred is not None else float('nan'):>6.3f}"
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Full-agent gameplay eval v2.")
    ap.add_argument("--policy-a", default=DEFAULT_POLICY_A)
    ap.add_argument("--policy-b", default=DEFAULT_POLICY_B)
    ap.add_argument(
        "--matchups",
        default="mirror,teacher",
        help="comma list: mirror (a vs b), teacher (a vs heuristic), random",
    )
    ap.add_argument("--games", type=int, default=200, help="games PER matchup")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--pool", default="engine", choices=("all", "engine", "castable"))
    ap.add_argument(
        "--set",
        dest="set_code",
        default=SET_CODE,
        help="card pool set (default M21; ZNR once compiled — empty pool fails loudly)",
    )
    ap.add_argument("--deck-pairs-seed", type=int, default=1409)
    ap.add_argument("--turn-cap", type=int, default=TURN_CAP)
    ap.add_argument("--seed-base", type=int, default=0)
    ap.add_argument("--device", default="cpu", choices=("auto", "cpu", "cuda"))
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    policy_a = str(Path(args.policy_a).resolve())
    policy_b = str(Path(args.policy_b).resolve())
    wanted = [m.strip() for m in args.matchups.split(",") if m.strip()]
    pair = {"mirror": policy_b, "teacher": "teacher", "random": "random"}
    baselines = []
    for m in wanted:
        if m not in pair:
            raise SystemExit(f"unknown matchup lane {m!r}")
        baselines.append((m, pair[m]))

    seeds = list(range(args.seed_base + 1, args.seed_base + 1 + args.games))
    swaps = seat_swaps(args.games)
    supply = get_supply(args.pool, args.set_code)
    dev = args.device
    if dev == "auto":
        import torch

        dev = "cuda" if torch.cuda.is_available() else "cpu"

    jobs = [
        {
            "seed": s,
            "swap": sw,
            "spec_a": policy_a,
            "spec_b": base,
            "deck_pairs_seed": args.deck_pairs_seed,
            "turn_cap": args.turn_cap,
            "device": dev,
        }
        for _, base in baselines
        for s, sw in zip(seeds, swaps, strict=True)
    ]
    started = time.perf_counter()
    specs = tuple({policy_a, *{b for _, b in baselines if b.endswith(".pt")}})
    if args.workers <= 1:
        _init_worker(args.pool, args.set_code, specs, dev)
        records = [_worker(j) for j in jobs]
    else:
        ctx = multiprocessing.get_context("spawn")
        with ctx.Pool(
            args.workers, initializer=_init_worker, initargs=(args.pool, specs, dev)
        ) as pool:
            records = pool.map(_worker, jobs, chunksize=1)
    elapsed = time.perf_counter() - started

    matchups: dict[str, Any] = {}
    for i, (lane, base) in enumerate(baselines):
        recs = sorted(
            records[i * args.games : (i + 1) * args.games], key=lambda r: r["seed"]
        )
        label = f"{lane}:{Path(policy_a).name[:12]}_vs_" + (
            Path(base).name[:12] if base.endswith(".pt") else base
        )
        matchups[label] = summarize_matchup(recs, Path(policy_a).name, base)
    out: dict[str, Any] = {
        "meta": {
            "date": time.strftime("%Y-%m-%d %H:%M"),
            "version": "v2-full-agent",
            "policy_a": policy_a,
            "pool_mode": args.pool,
            "pool_cards": len(supply.metas),
            "turn_cap": args.turn_cap,
            "games_per_matchup": args.games,
            "seeds": [seeds[0], seeds[-1]] if seeds else [],
            "deck_pairs_seed": args.deck_pairs_seed,
            "device": dev,
            "workers": args.workers,
            "seconds": round(elapsed, 1),
            "full_agent_layers": (
                "provider asks (may/scry/choose/PASS/attack/block/cw/order/"
                "trample/policy, seat-attributed by the site-tag handle -> "
                "controller_of) + rig act layer (PolicyActDriver: PASS/land/"
                "cast/activation menu per act, single-slot targets asked). "
                "Residual driver heuristics: auto-tap-all mana (no tap-amount "
                "ask exists), multi-slot target rows keep rng. ENGINE GAP: "
                "no main-phase priority/cast ask-site exists in "
                "MTG_bot/core/executor (query.legal_casts has no producer "
                "ask) — the act menu is rig-side over the declarative query "
                "surface."
            ),
        },
        "matchups": matchups,
        "records": {
            lane: records[i * args.games : (i + 1) * args.games]
            for i, (lane, _) in enumerate(baselines)
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
    _print_table(out)
    print(
        f"\npolicy={Path(policy_a).name} pool={args.pool} "
        f"games={args.games}/matchup {elapsed:.0f}s -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
