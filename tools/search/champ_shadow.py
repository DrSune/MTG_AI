"""CHAMP-shadow generator — data from the CHAMPION's own distribution.

KNOWLEDGE/2026-10-13/75 Option A: bc9_S3_s1 (bc9-era champion, 0.3927 vs
teacher) plays seat 0 under the CURRENT engine/rig; EVERY seat-0 asked
decision becomes a gold row labelled with the CHAMPION's own pick
(``source: "champ"``). The hypothesis under test: the era regression is
behaviour drift caused by moved gold priors / tokenization mismatch, so
generating on-policy states from the policy that still wins gives the
next BC wave a distribution the champion is competent on.

Mechanical reuse, no forks: the game loop, seat attribution and act layer
are ``gameplay_eval_v2`` verbatim (mirrored the way ``dagger_wave``
mirrors it); the chunking/encode-exactness discipline is
``dagger_wave.chunk_seat`` + ``_renumber`` imported AS-IS — budget ==
encoder-visible size (assert inside), BOS inside the budget, a gold row
bigger than the budget is dropped and counted, never silently cut. This
file only changes the LABEL (teacher -> champion pick, every seat-0 ask)
and the opponent policy.

Opponents cycle per game by seed parity (``seed % 3``): seat 1 is
teacher, random, or a mirror copy of the champion itself; results are
reported per opponent.

Run::

    .venv/bin/python tools/search/champ_shadow.py --smoke
    .venv/bin/python tools/search/champ_shadow.py --games 48 --workers 12
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sys
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from MTG_bot.core.executor.games import TURN_CAP, Supply, get_supply
from tools.eval import gameplay_eval_v2 as gv2
from tools.eval.dagger_wave import _renumber, chunk_seat
from tools.eval.gameplay_eval_v2 import KIND_DECLINE_WORD, V2_REFUSE, site_kind
from tools.training import bc_data, bc_data_v2
from tools.training.ab_duel import (
    _cards_rows_of,
    classify_outcome,
    snapshot_obs,
)
from tools.training.collector import AskContext

DEFAULT_CKPT = str(REPO / "tools" / "training" / "bc9_S3_s1_best.pt")
OUT_EPISODES = REPO / "tools" / "training" / "episodes_champ.jsonl"
OUT_STATS = Path(__file__).resolve().parent / "champ_stats_v1.json"
BUDGET_MIN_DEFAULT = 90.0
GRACE_MIN = 3.0  # an in-flight game may land after the deadline
DECK_PAIRS_SEED = 7700  # /75 rig deck-pair base

#: seat-1 opponent cycle, indexed by ``seed % 3``
OPPONENTS = ("teacher", "random", "champ")


def opponent_for_seed(seed: int) -> str:
    """Deterministic per-game opponent cycling (seed parity over the cycle)."""
    return OPPONENTS[seed % len(OPPONENTS)]


# ----------------------------------------------------------------- UNK audit
def stream_words(what: str, obs: dict) -> list[str]:
    """The encode-visible stream words of one ask row (site + v2 obs):
    exactly what ``encode_episode_v2`` serializes between ASK and SEP."""
    return bc_data.site_words(what) + bc_data_v2.obs_words_v2(obs)


def unk_audit(episodes: list[dict], vocab: dict[str, int]) -> dict[str, Any]:
    """UNK-rate of the EMITTED rows under the checkpoint's own vocab, plus
    the top OOV strings (the strings that hash to UNK — first tokens of
    their rows)."""
    unk = vocab[bc_data.UNK]
    tokens = misses = 0
    gold_tokens = gold_misses = 0
    oov: Counter = Counter()
    for ep in episodes:
        for row in ep["asks"]:
            words = stream_words(row["what"], row["obs"])
            m = sum(1 for w in words if vocab.get(w, unk) == unk)
            tokens += len(words)
            misses += m
            for w in words:
                if vocab.get(w, unk) == unk:
                    oov[w] += 1
            if row["gold"]:
                ground = row.get("ground", ())
                for ci, cand in enumerate(row["candidates"]):
                    g = ground[ci] if ci < len(ground) else []
                    cw = bc_data_v2.cand_words_v2(cand, g)
                    gm = sum(1 for w in cw if vocab.get(w, unk) == unk)
                    gold_tokens += len(cw)
                    gold_misses += gm
    return {
        "stream_tokens": tokens,
        "stream_unk": misses,
        "stream_unk_rate": round(misses / max(1, tokens), 4),
        "cand_tokens": gold_tokens,
        "cand_unk": gold_misses,
        "cand_unk_rate": round(gold_misses / max(1, gold_tokens), 4),
        "top_oov": oov.most_common(10),
    }


def verify_episodes(episodes: list[dict], vocab: dict[str, int], max_len: int) -> None:
    """Encode-exactness over emitted episodes (the dagger_wave discipline,
    re-checked on the FINAL rows): the chunk budget equals the encoded
    stream length, the stream fits the checkpoint, every gold index is a
    legal menu index."""
    for ep in episodes:
        enc = bc_data_v2.encode_episode_v2(ep, vocab)
        assert len(enc["seq"]) == ep["n_tokens"], (
            f"{ep['pack']}: encoder len {len(enc['seq'])} != n_tokens {ep['n_tokens']}"
        )
        assert ep["n_tokens"] <= max_len, f"{ep['pack']}: over budget"
        golds = [r for r in ep["asks"] if r["gold"]]
        assert len(enc["gold"]) == len(golds)
        for g, row in zip(enc["gold"], golds):
            assert 0 <= row["gold_idx"] < len(row["candidates"])
            assert g["gold_idx"] == row["gold_idx"]


# ------------------------------------------------------------------ game run
def run_champ_game(
    seed: int,
    supply: Supply,
    ckpt_spec: str = DEFAULT_CKPT,
    opponent: str | None = None,
    deck_pairs_seed: int = DECK_PAIRS_SEED,
    turn_cap: int = TURN_CAP,
    device: str = "cpu",
    agent_hook: Callable[[int, Any], None] | None = None,
) -> dict[str, Any]:
    """One game, champion fixed at seat 0 (no swap). ``book`` records every
    seat-0 ask (engine lane AND rig act layer) as a gold row with the
    champion's pick; seat-1 asks are counted but never labelled.
    ``agent_hook(seat, agent)`` (if given) sees each policy right after
    construction — this is what tools/search/drift_probe.py uses to
    instrument ``BcAsk._decide`` without touching eval code."""
    bc_data_v2.install_choose_stash()
    opp = opponent if opponent is not None else opponent_for_seed(seed)
    decks = gv2.deal_decks(seed, deck_pairs_seed, supply)
    game = gv2._setup_game(seed, supply, decks)
    world = game.world
    seats = [str(s) for s in world.player_order]
    opp_spec = ckpt_spec if opp == "champ" else opp
    agents = {
        0: gv2.make_eval_policy(ckpt_spec, seed * 2, device),
        1: gv2.make_eval_policy(opp_spec, seed * 2 + 1, device),
    }
    for seat, agent in agents.items():
        if agent_hook is not None:
            agent_hook(seat, agent)
    vocab0 = getattr(agents[0], "vocab", None)

    counters = {"seat0_asks": 0, "seat1_asks": 0, "model_errors": 0, "illegal_idx": 0}
    kinds: dict[str, dict[str, int]] = {}
    history: list[dict] = []

    def book(seat: int, vocab: tuple[str, ...], what: str, idx: int, obs: dict) -> None:
        kind = site_kind(what)
        kd = kinds.setdefault(kind, {"asks": 0, "v0": 0, "declines": 0})
        kd["asks"] += 1
        kd["v0"] += int(idx == 0)
        decline_word = KIND_DECLINE_WORD.get(kind)
        declined = (
            vocab[idx] == decline_word if decline_word else vocab[idx] in V2_REFUSE
        )
        kd["declines"] += int(declined)
        counters[f"seat{seat}_asks"] += 1
        if seat != 0:
            return  # opponent asks are context for the opponent, not our data
        row = {
            "ordinal": 0,
            "what": what,
            "candidates": list(vocab),
            "kind": kind,
            "obs": {k: v for k, v in obs.items() if not k.startswith("_")},
            "ground": [
                list(g)
                for g in bc_data_v2.ground_with(_cards_rows_of(obs), what, list(vocab))
            ],
            "gold": True,
            "gold_idx": idx,
        }
        history.append({"row": row, "_tokens": (what, obs)})

    def provider(vocab: tuple[str, ...], what: str) -> str:
        active = seats.index(str(world.active_player))
        s = gv2.resolve_seat(what, game, seats, active, handle_words)
        obs = snapshot_obs(world, world.active_player)
        obs["_seat"] = s
        obs["_pt"] = pt
        try:
            idx = agents[s].decide(
                AskContext(vocab=what, candidates=tuple(vocab), world=obs)
            )
        except Exception:
            counters["model_errors"] += 1
            raise
        if not 0 <= idx < len(vocab):
            counters["illegal_idx"] += 1
            raise ValueError(f"champ_shadow: index {idx} out of {vocab}")
        book(s, vocab, what, idx, obs)
        return vocab[idx]

    handle_words = {str(h) for h in world.cards} | {str(p) for p in world.player_order}
    pt = {
        str(h): [world.cards[h].identity.power, world.cards[h].identity.toughness]
        for h in world.cards
    }
    driver = gv2.PolicyActDriver(seed, agents)
    driver.answer = provider  # type: ignore[method-assign]
    driver.recorder = book
    crash = ""
    try:
        gv2._play(game, driver, list(world.player_order), turn_cap)
        reason = game.reason
    except BaseException as error:  # noqa: BLE001 - recorded, never hidden
        reason = f"crash:{type(error).__name__}: {error}"
        crash = type(error).__name__
    losers = [
        s for s, h in zip(seats, world.player_order, strict=True) if game.is_loser(h)
    ]
    winner = (
        next((s for s in seats if s not in losers), None) if len(losers) == 1 else None
    )
    outcome = classify_outcome(reason, winner, seats, 0)

    # champion episodes: seat 0 only, single label class, EVERY row gold.
    max_len = getattr(agents[0], "max_len", 1024)
    trunc = {"gold_row_overflow": 0}
    golds = [
        {
            "row": i,
            "kind": h["row"]["kind"],
            "gold_idx": h["row"]["gold_idx"],
            "heur_idx": h["row"]["gold_idx"],  # no second teacher: label == pick
            "policy_idx": h["row"]["gold_idx"],
            "backings": [],
        }
        for i, h in enumerate(history)
    ]
    episodes = chunk_seat(history, golds, max_len, seed, 0, "champ", trunc)
    for ci, ep in enumerate(episodes):
        ep_id = f"champshadow-g{seed}s0c{ci}"
        ep["pack"] = ep_id
        ep["card"] = ep_id
        ep["source"] = "champ"
        ep["game_seed"] = seed
        ep["opponent"] = opp
        ep["outcome"] = outcome
    _renumber(episodes)
    if episodes and vocab0 is not None:
        verify_episodes(episodes, vocab0, max_len)

    unk = (
        unk_audit(episodes, vocab0)
        if episodes and vocab0 is not None
        else {"stream_tokens": 0, "stream_unk": 0, "top_oov": []}
    )
    return {
        "seed": seed,
        "opponent": opp,
        "outcome": outcome,
        "reason": reason,
        "turns": game.turns,
        "crash": crash or None,
        "counters": counters,
        "kinds": kinds,
        "trunc": trunc,
        "unk": unk,
        "episodes": episodes,
    }


# ------------------------------------------------------------------ batch
_G: dict[str, Any] = {}


def _init_worker(pool: str, ckpt_spec: str, device: str) -> None:
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    import torch

    torch.set_num_threads(1)
    _G["supply"] = get_supply(pool)
    from tools.training.ab_duel import BcAsk

    BcAsk.fresh(ckpt_spec, device)  # one model per worker process


def _worker(job: dict[str, Any]) -> dict[str, Any]:
    t0 = time.time()
    g = run_champ_game(
        job["seed"],
        supply=_G["supply"],
        ckpt_spec=job["ckpt"],
        opponent=job.get("opponent"),
        deck_pairs_seed=job["deck_pairs_seed"],
        turn_cap=job["turn_cap"],
        device=job["device"],
    )
    g["seconds"] = round(time.time() - t0, 1)
    return g


def _flush(episodes_path: Path, games: list[dict]) -> int:
    n = 0
    with episodes_path.open("w") as fh:
        for g in games:
            g["ep_tokens"] = [e["n_tokens"] for e in g["episodes"]]
            for ep in g.pop("episodes", []):
                fh.write(json.dumps(ep) + "\n")
                n += 1
    return n


def _aggregate(games: list[dict], wall: float, n_eps: int, ckpt: str) -> dict:
    n = len(games)
    asks = sum(g["counters"]["seat0_asks"] for g in games)
    kinds: dict[str, dict[str, int]] = {}
    for g in games:
        for k, v in g["kinds"].items():
            kd = kinds.setdefault(k, {"asks": 0, "v0": 0, "declines": 0})
            for key, val in v.items():
                kd[key] += val
    per_opp: dict[str, dict[str, Any]] = {}
    for opp in OPPONENTS:
        sub = [g for g in games if g["opponent"] == opp]
        if not sub:
            continue
        per_opp[opp] = {
            "games": len(sub),
            "results": dict(Counter(g["outcome"] for g in sub)),
            "crashes": [g["seed"] for g in sub if g["crash"]],
        }
    st_tok = sum(g["unk"]["stream_tokens"] for g in games)
    st_unk = sum(g["unk"]["stream_unk"] for g in games)
    cd_tok = sum(g["unk"].get("cand_tokens", 0) for g in games)
    cd_unk = sum(g["unk"].get("cand_unk", 0) for g in games)
    oov: Counter = Counter()
    for g in games:
        oov.update(dict(g["unk"]["top_oov"]))
    ntoks = [t for g in games for t in g.get("ep_tokens", [])]
    return {
        "ckpt": ckpt,
        "wall_seconds": round(wall, 1),
        "games": n,
        "asks_captured": asks,
        "asks_per_game": round(asks / max(1, n), 1),
        "episodes": n_eps,
        "ep_tokens_max": max(ntoks, default=0),
        "ep_tokens_mean": round(sum(ntoks) / len(ntoks), 1) if ntoks else 0,
        "results": dict(Counter(g["outcome"] for g in games)),
        "per_opponent": per_opp,
        "crashes": [g["seed"] for g in games if g["crash"]],
        "model_errors": sum(g["counters"]["model_errors"] for g in games),
        "illegal_idx": sum(g["counters"]["illegal_idx"] for g in games),
        "gold_row_overflow": sum(g["trunc"]["gold_row_overflow"] for g in games),
        "unk_rows": {
            "stream_tokens": st_tok,
            "stream_unk": st_unk,
            "stream_unk_rate": round(st_unk / max(1, st_tok), 4),
            "cand_tokens": cd_tok,
            "cand_unk": cd_unk,
            "cand_unk_rate": round(cd_unk / max(1, cd_tok), 4),
            "top_oov": oov.most_common(10),
        },
        "by_kind": {k: dict(v) for k, v in sorted(kinds.items())},
        "seconds_per_game": {
            "min": round(min((g.get("seconds", 0) for g in games), default=0), 1),
            "max": round(max((g.get("seconds", 0) for g in games), default=0), 1),
        },
    }


def main(argv: list[str] | None = None) -> int:
    # torch stays un-imported in the parent until workers pin their threads
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=48)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--smoke", action="store_true", help="2 serial games, no write")
    ap.add_argument("--budget-min", type=float, default=BUDGET_MIN_DEFAULT)
    ap.add_argument("--seeds", type=int, default=7700, help="first game seed")
    ap.add_argument("--ckpt", default=DEFAULT_CKPT)
    ap.add_argument("--pool", default="engine", choices=("all", "engine", "castable"))
    ap.add_argument("--deck-pairs-seed", type=int, default=DECK_PAIRS_SEED)
    ap.add_argument("--cap", type=int, default=TURN_CAP)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--out-episodes", type=Path, default=OUT_EPISODES)
    ap.add_argument("--out-stats", type=Path, default=OUT_STATS)
    ap.add_argument(
        "--opponent",
        choices=OPPONENTS,
        default=None,
        help="force one opponent for every game (default: seed-parity cycle)",
    )
    args = ap.parse_args(argv)
    t0 = time.time()

    if args.smoke:
        supply = get_supply(args.pool)
        for seed in (args.seeds, args.seeds + 1):
            g = run_champ_game(
                seed,
                supply=supply,
                ckpt_spec=args.ckpt,
                opponent=args.opponent,
                deck_pairs_seed=args.deck_pairs_seed,
                turn_cap=args.cap,
                device=args.device,
            )
            n_eps = len(g["episodes"])
            assert g["crash"] is None, f"smoke crash {seed}: {g['reason']}"
            assert g["counters"]["illegal_idx"] == 0, f"smoke illegal {seed}"
            assert g["counters"]["seat0_asks"] >= 3, f"smoke degenerate {seed}"
            assert n_eps >= 1 and all(e["n_tokens"] <= 1024 for e in g["episodes"]), (
                f"smoke no episodes {seed}"
            )
            print(
                f"smoke seed={seed} opp={g['opponent']} {g['outcome']} "
                f"asks={g['counters']['seat0_asks']} eps={n_eps} "
                f"unk_rate={g['unk']['stream_unk_rate']} "
                f"overflow={g['trunc']['gold_row_overflow']}"
            )
        print("SMOKE OK")
        return 0

    import multiprocessing as mp

    deadline = t0 + args.budget_min * 60.0
    seeds = list(range(args.seeds, args.seeds + args.games))
    jobs = [
        {
            "seed": s,
            "ckpt": args.ckpt,
            "opponent": args.opponent,
            "deck_pairs_seed": args.deck_pairs_seed,
            "turn_cap": args.cap,
            "device": args.device,
        }
        for s in seeds
    ]
    done: list[dict] = []
    ctx = mp.get_context("fork")
    with cf.ProcessPoolExecutor(
        max_workers=args.workers,
        mp_context=ctx,
        initializer=_init_worker,
        initargs=(args.pool, args.ckpt, args.device),
    ) as pool:
        futs = {pool.submit(_worker, j): j["seed"] for j in jobs}
        pending = set(futs)
        try:
            # cf.wait, NOT as_completed: the budget must fire even when ZERO
            # games finish (gen_games law).
            while pending:
                left = deadline + GRACE_MIN * 60.0 - time.time()
                if left <= 0:
                    print(
                        f"BUDGET exceeded; cutting pool at {len(done)}/{len(seeds)}",
                        flush=True,
                    )
                    break
                fin, pending = cf.wait(pending, timeout=min(30.0, max(1.0, left)))
                for fut in fin:
                    pending.discard(fut)
                    try:
                        g = fut.result()
                        done.append(g)
                        print(
                            f"[{time.strftime('%H:%M:%S')}] game seed={g['seed']} "
                            f"opp={g['opponent']} {g['outcome']} "
                            f"asks={g['counters']['seat0_asks']} eps={len(g['episodes'])} "
                            f"done={len(done)}/{len(seeds)}",
                            flush=True,
                        )
                    except BaseException as e:  # noqa: BLE001
                        print(
                            f"worker died seed={futs[fut]}: {type(e).__name__}: {e}",
                            flush=True,
                        )
        finally:
            for p in list(pool._processes.values()):
                p.terminate()
            pool.shutdown(wait=False, cancel_futures=True)

    n_eps = _flush(args.out_episodes, done)
    agg = _aggregate(done, time.time() - t0, n_eps, args.ckpt)
    args.out_stats.write_text(json.dumps(agg, indent=1))
    print(
        json.dumps(
            {
                k: agg[k]
                for k in ("games", "asks_captured", "episodes", "results", "crashes")
            },
            indent=1,
        )
    )
    print(
        f"wrote {n_eps} episodes -> {args.out_episodes.name}; stats -> {args.out_stats.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
