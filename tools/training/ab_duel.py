"""A/B duel runner: batched seat-swapped games between two policy specs.

Training batch (owner charges 1): measure the winrate of one policy against
another, WITH the time axis — the frozen-vs-updated curve answers *when* in
the gradient-update process the winrate gain appears (and decays), so
degrading / catastrophic forgetting against a stale frozen opponent is
visible as a curve, not a single number.

Policy specs (the duel vocabulary of this module):
  * ``random``      — uniform over the canonical vocabulary (the ELO anchor);
  * ``first``       — scripted floor, always index 0 (collector mirror);
  * ``pass-floor``  — the rig's disciplined floor (PASS when offered),
    accepted under the alias ``scripted``;
  * ``<path>.pt``   — a :class:`bc_model.PointerBC` checkpoint (``bc_s1.pt``
    family), run CLOSED-LOOP through :class:`BcAsk` below.

Laws this honors (KNOWLEDGE/2026-10-05/04-rulings-r17.md, standing gates):
  * **Seat-swap** every duel (E7: 0.530 seat bias) — ``--games N`` runs
    N/2 games with A in seat 0 and N/2 with A in seat 1 (odd N: seat 0 gets
    the extra game; the balance is asserted, ``seat_balance`` in the output);
  * **D9 disjoint seed banks** — a pair never sees a seed twice across
    duels; the registry lives at ``reports/monitoring/duel_seeds.json``;
  * determinism: one seed + one swap identifies the whole game (collector
    law) — a rerun with the same seeds reproduces the table exactly;
  * **D8/D10 honesty**: draws (STALL / turn-cap / other / crash) are
    counted and reported separately, never silently folded into a winrate;
    the BC adapter's observation schema gap is documented at
    :class:`BcAsk` (source-card rows are not visible at the provider lane).

Batching: multiprocessing(10) with the collector worker idiom — one supply
compile + one checkpoint load per worker, jobs are primitive dicts.

Run::

    .venv/bin/python -m tools.training.ab_duel --a random --b scripted --games 400
    .venv/bin/python -m tools.training.ab_duel --reference random \\
        --checkpoint-dir runs/s2 --games 200        # the WHEN curve
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from MTG_bot.core.executor.games import (
    TURN_CAP,
    RandomPolicy,
    Supply,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
)
from MTG_bot.core.state import ZONE_BATTLEFIELD
from tools.training import bc_data
from tools.training.collector import (
    AskContext,
    FirstAsk,
    PassFirstAsk,
    RandomAsk,
)

#: Default D9 seed-bank registry (never reused seeds per pair, ever).
SEED_BANK = REPO / "reports" / "monitoring" / "duel_seeds.json"

FLOOR_SPECS = {"random": RandomAsk, "first": FirstAsk, "pass-floor": PassFirstAsk}


# ------------------------------------------------------------------ specs
def normalize_spec(spec: str) -> str:
    """Canonical form of a policy spec: floors by name, checkpoints by
    resolved absolute path (the seed-bank key must be path-identical)."""
    if spec == "scripted":
        return "pass-floor"
    if spec in FLOOR_SPECS:
        return spec
    return str(Path(spec).resolve())


def is_checkpoint_spec(spec: str) -> bool:
    return normalize_spec(spec) not in FLOOR_SPECS


def pair_key(spec_a: str, spec_b: str) -> str:
    """Symmetric pair key — (a,b) and (b,a) share one seed bank (D9)."""
    return "|".join(sorted((normalize_spec(spec_a), normalize_spec(spec_b))))


# --------------------------------------------------------------- statistics
def wilson(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% interval for a binomial proportion (well-behaved at
    0 and n; empty n returns the vacuous [0,1])."""
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def classify_outcome(
    reason: str, winner_seat: str | None, seats: list[str], a_seat: int
) -> str:
    """One game -> 'a' / 'b' / 'draw-stall' / 'draw-cap' / 'draw-other' /
    'crash'. Stall and cap are counted SEPARATELY (the owner asked; they
    mean different things about the policy pair)."""
    if reason.startswith("crash:"):
        return "crash"
    if winner_seat is None:
        if "STALL" in reason:
            return "draw-stall"
        if "turn cap" in reason:
            return "draw-cap"
        return "draw-other"
    return "a" if seats.index(winner_seat) == a_seat else "b"


# ------------------------------------------------------------- seed bank
def load_bank(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"pairs": {}}


def allocate_seeds(
    bank: dict[str, Any], key: str, games: int, explicit: list[int] | None = None
) -> list[int]:
    """D9 allocation: fresh positive seeds, disjoint from every seed this
    pair has ever used. ``explicit`` seeds are honoured (deterministic
    reruns) but must still be unused — a reused seed raises."""
    entry = bank["pairs"].setdefault(key, {"used": []})
    used = set(entry["used"])
    if explicit is not None:
        clash = used.intersection(explicit)
        if clash:
            raise ValueError(
                f"D9: pair {key} reuses seeds {sorted(clash)[:8]} — "
                "reruns must target a fresh seed range or a fresh bank file"
            )
        new = list(explicit)
    else:
        new: list[int] = []
        nxt = max(used) + 1 if used else 1
        while len(new) < games:
            if nxt not in used:
                new.append(nxt)
            nxt += 1
    entry["used"].extend(new)
    return new


def save_bank(bank: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bank, sort_keys=True), encoding="utf-8")


def seat_swaps(games: int) -> list[bool]:
    """Alternating swap assignment; even N -> exactly N/2 each seat."""
    return [i % 2 == 1 for i in range(games)]


# ---------------------------------------------------------- BC adapter
_MODEL_CACHE: dict[tuple[str, str], Any] = {}


class BcAsk:
    """Closed-loop BC policy: the checkpoint scores each of ITS OWN seat's
    asks as a growing causal decision stream (episode = one seat's steps,
    design doc 09 §2) and takes the pointer argmax (deterministic; ties ->
    lowest index, torch argmax law).

    KNOWN SCHEMA GAP (documented, batch-1 honest null): the provider lane
    cannot see the asking card (``ExecCtx.source``), so the obs surface
    here lacks the training-time ``source`` row; every out-of-training word
    maps to ``<unk>`` through the saved vocab. This is exactly the
    generalization breakage batch 1 found — near-random play is the
    PREDICTED behaviour; a winrate above the random anchor must be
    investigated, not believed. The obs IS omniscient-v1 (both hands),
    identically for both duel seats (symmetric) — D10 masked ablation
    remains the disqualification gate for any claimed skill gain.

    Streams longer than the model's ``max_len`` keep BOS + the most recent
    window (training never saw >1024; any choice here is off-distribution)
    and bump ``truncations`` so the duel record says so honestly."""

    def __init__(self, model: Any, vocab: dict[str, int], max_len: int) -> None:
        self.model = model
        self.vocab = vocab
        self.max_len = max_len
        self.truncations = 0
        self.seq: list[int] = [vocab[bc_data.BOS]]

    @classmethod
    def fresh(cls, spec: str, device: str = "auto") -> BcAsk:
        """One model instance per (path, device) per process; per-seat
        instances share it read-only (inference only, eval mode)."""
        import torch

        key = (spec, device)
        if key not in _MODEL_CACHE:
            if device == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"
            blob = torch.load(spec, map_location=device, weights_only=False)
            from tools.training.bc_model import PointerBC

            model = PointerBC(**blob["config"])
            model.load_state_dict(blob["state"])
            model.to(device).eval()
            for p in model.parameters():
                p.requires_grad_(False)
            _MODEL_CACHE[key] = (model, blob["vocab"], device)
        model, vocab, _ = _MODEL_CACHE[key]
        return cls(model, vocab, model.max_len)

    def decide(self, ctx: AskContext) -> int:
        import torch  # lazy: floors never pay the torch import

        return self._decide(torch, ctx)

    def _decide(self, torch: Any, ctx: AskContext) -> int:

        vocab = self.vocab
        unk = vocab[bc_data.UNK]
        self.seq.append(vocab[bc_data.ASK])
        for w in bc_data.site_words(ctx.vocab) + bc_data.obs_words(ctx.world):
            self.seq.append(vocab.get(w, unk))
        self.seq.append(vocab[bc_data.SEP])
        if len(self.seq) > self.max_len:
            self.seq = [vocab[bc_data.BOS]] + self.seq[-(self.max_len - 1) :]
            self.truncations += 1
        sep = len(self.seq) - 1

        cands = ctx.candidates
        l_max = max(
            (len(bc_data.tokenize(c)) or 1 for c in cands),
            default=1,
        )
        cand_ids = torch.zeros(1, len(cands), l_max, dtype=torch.long)
        cand_mask = torch.zeros(1, len(cands), l_max, dtype=torch.bool)
        is_pass = torch.zeros(1, len(cands), dtype=torch.bool)
        for ci, cand in enumerate(cands):
            ids = [vocab.get(w, unk) for w in bc_data.tokenize(cand)] or [unk]
            cand_ids[0, ci, : len(ids)] = torch.tensor(ids, dtype=torch.long)
            cand_mask[0, ci, : len(ids)] = True
            is_pass[0, ci] = cand == "PASS"

        device = next(self.model.parameters()).device
        tokens = torch.tensor([self.seq], dtype=torch.long, device=device)
        with torch.no_grad():
            out = self.model.forward(
                tokens,
                torch.zeros_like(tokens, dtype=torch.bool),
                torch.zeros(1, dtype=torch.long, device=device),
                torch.tensor([sep], dtype=torch.long, device=device),
                cand_ids.to(device),
                cand_mask.to(device),
                is_pass.to(device),
            )
        return int(out.argmax(-1)[0])


# ------------------------------------------------------- duel game runner
def snapshot_obs(world: Any, a_handle: Any) -> dict[str, Any]:
    """Ask-moment observation, mirroring packrec._obs_snapshot (omniscient-v1
    schema: per-seat battlefield/hand rows, gy counts, mana pools) minus the
    ``source`` row the provider lane cannot see. Both duel seats get the
    SAME schema — symmetric, so no seat-side information asymmetry."""
    order = list(world.player_order)
    seats = {h: i for i, h in enumerate(order)}
    obs: dict[str, Any] = {
        "turn": 0,
        "lives": [],
        "active": None,
        "seat": None,
        "battlefield": [],
        "hand": [],
        "graveyard": [],
        "mana": [],
    }
    try:
        obs["turn"] = int(world.turn)
        obs["lives"] = [world.players[h].life for h in order]
        obs["active"] = seats.get(world.active_player)
        obs["seat"] = seats.get(world.active_player)

        def card_row(handle: Any) -> list[str]:
            state = world.cards[handle]
            row = [str(handle), str(state.identity.name)]
            if state.tapped:
                row.append("tapped")
            for k, v in sorted(state.counters.items()):
                row.append(f"{k}={v}")
            return row

        for h in order:
            player = world.players[h]
            bf = player.zones.get(ZONE_BATTLEFIELD)
            obs["battlefield"].append(
                [card_row(c) for c in sorted(bf.entries, key=str)]
                if bf is not None
                else []
            )
            hand = player.zones.get("hand")
            obs["hand"].append(
                [card_row(c) for c in sorted(hand.entries, key=str)]
                if hand is not None
                else []
            )
            gy = player.zones.get("graveyard")
            obs["graveyard"].append(len(gy.entries) if gy else 0)
            pool = getattr(player, "mana_pool", None)
            obs["mana"].append(dict(sorted(pool.items())) if pool else {})
    except Exception as exc:  # noqa: BLE001 - degrade, never derail a duel
        obs["obs_error"] = f"{type(exc).__name__}: {exc}"
    return obs


def make_policy(spec: str, seat_seed: int, device: str) -> Any:
    """Fresh per-game policy instance (fresh RNG / fresh BC stream)."""
    spec = normalize_spec(spec)
    if spec == "random":
        return RandomAsk(seed=seat_seed)
    if spec in FLOOR_SPECS:
        return FLOOR_SPECS[spec]()
    return BcAsk.fresh(spec, device)


def run_duel_game(
    seed: int,
    swap: bool,
    spec_a: str,
    spec_b: str,
    pool_mode: str = "all",
    deck_pairs_seed: int = 1409,
    turn_cap: int = TURN_CAP,
    device: str = "auto",
    supply: Supply | None = None,
) -> dict[str, Any]:
    """One seeded, seat-assigned duel -> the outcome record. Mirrors
    collector.run_episode's provider installation exactly (the games.py
    ``driver.answer`` masking), but routes each ask to the policy OWNING
    the active seat."""
    supply = supply if supply is not None else get_supply(pool_mode)
    decks = deal_decks(seed, deck_pairs_seed, supply)
    game = _setup_game(seed, supply, decks)
    world = game.world
    seats = [str(s) for s in world.player_order]
    a_seat = 1 if swap else 0
    specs = {a_seat: spec_a, 1 - a_seat: spec_b}
    policies = {
        seat: make_policy(specs[seat], seed * 2 + seat, device) for seat in (0, 1)
    }

    def provider(vocab: tuple[str, ...], what: str) -> str:
        seat = seats.index(str(world.active_player))
        ctx = AskContext(
            vocab=what,
            candidates=tuple(vocab),
            world=snapshot_obs(world, world.active_player),
        )
        idx = policies[seat].decide(ctx)
        if not 0 <= idx < len(vocab):
            raise ValueError(f"ab_duel: policy index {idx} out of {vocab}")
        return vocab[idx]

    driver = RandomPolicy(seed)  # act-side driver: plays the query surface
    driver.answer = provider  # type: ignore[method-assign]
    crash = ""
    try:
        _play(game, driver, list(world.player_order), turn_cap)
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
    return {
        "seed": seed,
        "swap": swap,
        "outcome": classify_outcome(reason, winner, seats, a_seat),
        "reason": reason,
        "turns": game.turns,
        "crash": crash or None,
        "trunc": {
            str(seat): getattr(p, "truncations", 0) for seat, p in policies.items()
        },
    }


# ------------------------------------------------- worker parallelism
_G: dict[str, Any] = {}


def _duel_init(pool_mode: str, spec_a: str, spec_b: str, device: str) -> None:
    """One supply compile + one checkpoint load per worker, before timing."""
    _G["supply"] = get_supply(pool_mode)
    _G["spec_a"], _G["spec_b"], _G["device"] = spec_a, spec_b, device
    for spec in (spec_a, spec_b):
        if is_checkpoint_spec(spec):
            BcAsk.fresh(normalize_spec(spec), device)  # warm the model cache


def _duel_worker(job: dict[str, Any]) -> dict[str, Any]:
    return run_duel_game(
        job["seed"],
        job["swap"],
        _G["spec_a"],
        _G["spec_b"],
        supply=_G["supply"],
        device=_G["device"],
    )


# --------------------------------------------------------- the duel batch
def summarize(
    records: list[dict[str, Any]], spec_a: str, spec_b: str
) -> dict[str, Any]:
    """Aggregate an outcome record list into the duel table: winrate +
    Wilson 95% CI PER SIDE, draws split stall/cap/other, crashes separate,
    seat balance checked (E7 law), games counted honestly."""
    n = len(records)
    wins_a = sum(1 for r in records if r["outcome"] == "a")
    wins_b = sum(1 for r in records if r["outcome"] == "b")
    draws = {
        kind.split("-", 1)[1]: sum(1 for r in records if r["outcome"] == kind)
        for kind in ("draw-stall", "draw-cap", "draw-other")
    }
    crashes = sum(1 for r in records if r["outcome"] == "crash")
    a_seat_0 = sum(1 for r in records if not r["swap"])
    seat_a = {
        "seat0": _wins_with_seat(records, "a", swap=False),
        "seat1": _wins_with_seat(records, "a", swap=True),
        "games_seat0": a_seat_0,
        "games_seat1": n - a_seat_0,
    }
    lo_a, hi_a = wilson(wins_a, n)
    lo_b, hi_b = wilson(wins_b, n)
    return {
        "spec_a": spec_a,
        "spec_b": spec_b,
        "games": n,
        "a": {
            "wins": wins_a,
            "winrate": round(wins_a / n, 4) if n else 0.0,
            "ci": [round(lo_a, 4), round(hi_a, 4)],
            "score": round((wins_a + 0.5 * sum(draws.values())) / n, 4) if n else 0.0,
        },
        "b": {
            "wins": wins_b,
            "winrate": round(wins_b / n, 4) if n else 0.0,
            "ci": [round(lo_b, 4), round(hi_b, 4)],
            "score": round((wins_b + 0.5 * sum(draws.values())) / n, 4) if n else 0.0,
        },
        "draws": draws,
        "crashes": crashes,
        "seat_balance_ok": abs(seat_a["games_seat0"] - seat_a["games_seat1"]) <= 1,
        "a_by_seat": seat_a,
        "games_per_sec": None,  # filled by run_duel
    }


def _wins_with_seat(records: list[dict[str, Any]], side: str, swap: bool) -> int:
    return sum(1 for r in records if r["outcome"] == side and r["swap"] is swap)


def run_duel(
    spec_a: str,
    spec_b: str,
    games: int,
    workers: int = 10,
    pool_mode: str = "all",
    deck_pairs_seed: int = 1409,
    turn_cap: int = TURN_CAP,
    seeds: list[int] | None = None,
    device: str = "auto",
    bank_path: Path = SEED_BANK,
    bank: dict[str, Any] | None = None,
    persist_bank: bool = True,
) -> dict[str, Any]:
    """One full seat-swapped duel batch with a fresh D9 seed bank slice.
    ``bank``/``persist_bank`` let elo.py amortize one registry read-write
    over a whole round-robin."""
    own_bank = bank is None
    bank = bank if bank is not None else load_bank(bank_path)
    key = pair_key(spec_a, spec_b)
    chosen = allocate_seeds(bank, key, games, explicit=seeds)
    swaps = seat_swaps(games)
    jobs = [{"seed": s, "swap": sw} for s, sw in zip(chosen, swaps, strict=True)]
    started = time.perf_counter()
    if workers <= 1:
        supply = get_supply(pool_mode)
        records = [
            run_duel_game(
                job["seed"],
                job["swap"],
                spec_a,
                spec_b,
                pool_mode=pool_mode,
                deck_pairs_seed=deck_pairs_seed,
                turn_cap=turn_cap,
                device=device,
                supply=supply,
            )
            for job in jobs
        ]
    else:
        ctx = multiprocessing.get_context("spawn")
        with ctx.Pool(
            workers,
            initializer=_duel_init,
            initargs=(pool_mode, spec_a, spec_b, device),
        ) as pool:
            records = pool.map(_duel_worker, jobs, chunksize=1)
    elapsed = time.perf_counter() - started
    records.sort(key=lambda r: r["seed"])
    summary = summarize(records, normalize_spec(spec_a), normalize_spec(spec_b))
    summary["games_per_sec"] = round(games / elapsed, 3) if elapsed else None
    summary["seeds"] = [chosen[0], chosen[-1]]
    summary["pair_key"] = key
    if own_bank and persist_bank:
        save_bank(bank, bank_path)
    return {"summary": summary, "records": records}


# ------------------------------------------------------------- WHEN curve
def discover_checkpoints(dir_path: Path, pattern: str = "*.pt") -> list[Path]:
    """Checkpoint-family cadence for the curve: sorted by the longest digit
    run in the name (step/epoch number), plain-name order as fallback."""
    paths = sorted(dir_path.glob(pattern))

    def step_of(p: Path) -> tuple[int, str]:
        digits = "".join(ch for ch in p.stem if ch.isdigit())
        return (int(digits) if digits else 0, p.name)

    return sorted(paths, key=step_of)


def run_curve(
    reference: str,
    checkpoints: list[str],
    games: int,
    workers: int = 10,
    device: str = "auto",
    bank_path: Path = SEED_BANK,
    **duel_kw: Any,
) -> list[dict[str, Any]]:
    """The WHEN-does-it-rise / WHEN-does-it-decay table: every checkpoint in
    gradient-update order plays the SAME frozen reference on a fresh,
    disjoint seed slice (D9). Each row is one duel summary minus the raw
    records — plot ``a.winrate``/``b.winrate`` against the row index."""
    rows: list[dict[str, Any]] = []
    bank = load_bank(bank_path)
    for i, ckpt in enumerate(checkpoints):
        result = run_duel(
            reference,
            ckpt,
            games,
            workers=workers,
            device=device,
            bank=bank,
            persist_bank=False,
            bank_path=bank_path,
            **duel_kw,
        )
        row = {"curve_index": i, "reference": normalize_spec(reference)}
        row.update(result["summary"])
        rows.append(row)
    save_bank(bank, bank_path)
    return rows


# ------------------------------------------------------------ metrics out
def _emit_metric(payload: dict[str, Any]) -> None:
    """Best-effort log_metric handoff (the sibling batch owns the stream
    API; degrade silently to nothing if it does not exist yet)."""
    try:
        from tools.training import log_metric  # type: ignore[import-not-found]

        for name in ("log", "record", "emit"):
            fn = getattr(log_metric, name, None)
            if callable(fn):
                fn("ab_duel", payload)
                return
    except Exception:  # noqa: BLE001, S110 - metrics never break a duel
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A/B duel runner.")
    parser.add_argument("--a", help="policy spec A (single-duel mode)")
    parser.add_argument("--b", help="policy spec B (single-duel mode)")
    parser.add_argument("--reference", help="frozen reference (curve mode)")
    parser.add_argument("--checkpoints", help="comma list, gradient-update order")
    parser.add_argument("--checkpoint-dir", help="checkpoint family directory")
    parser.add_argument("--pattern", default="*.pt")
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--pool", default="all", choices=("all", "engine", "castable"))
    parser.add_argument("--deck-pairs-seed", type=int, default=1409)
    parser.add_argument("--turn-cap", type=int, default=TURN_CAP)
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="*",
        default=None,
        help="explicit seeds (deterministic rerun; still D9-registered)",
    )
    parser.add_argument("--device", default="auto", choices=("auto", "cpu", "cuda"))
    parser.add_argument("--seed-file", type=Path, default=SEED_BANK)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="result JSON (default reports/monitoring/duels/<key>.json)",
    )
    args = parser.parse_args(argv)

    if args.reference:
        if args.checkpoints:
            cks = [c.strip() for c in args.checkpoints.split(",") if c.strip()]
        elif args.checkpoint_dir:
            cks = [
                str(p)
                for p in discover_checkpoints(Path(args.checkpoint_dir), args.pattern)
            ]
        else:
            parser.error("curve mode needs --checkpoints or --checkpoint-dir")
        if not cks:
            parser.error("no checkpoints found for the curve")
        table = run_curve(
            args.reference,
            cks,
            args.games,
            workers=args.workers,
            device=args.device,
            bank_path=args.seed_file,
            pool_mode=args.pool,
            deck_pairs_seed=args.deck_pairs_seed,
            turn_cap=args.turn_cap,
        )
        result: dict[str, Any] = {"mode": "curve", "rows": table}
    else:
        if not (args.a and args.b):
            parser.error("single-duel mode needs --a and --b (or use --reference)")
        result = run_duel(
            args.a,
            args.b,
            args.games,
            workers=args.workers,
            pool_mode=args.pool,
            deck_pairs_seed=args.deck_pairs_seed,
            turn_cap=args.turn_cap,
            seeds=args.seeds or None,
            device=args.device,
            bank_path=args.seed_file,
        )
        result = result["summary"]

    out = args.out
    if out is None:
        stamp = time.strftime("%Y%m%dT%H%M%S")
        name = result.get("pair_key", "curve") or "curve"
        out = REPO / "reports" / "monitoring" / "duels" / f"{name}-{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
    _emit_metric(result if result.get("mode") != "curve" else {"rows": result["rows"]})
    print(json.dumps(result, indent=1, sort_keys=True))
    print(f"# written {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
