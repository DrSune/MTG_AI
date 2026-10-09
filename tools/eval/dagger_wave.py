"""DAgger wave 1 — full-agent BC-vs-teacher divergence harvesting (T5-G).

Reuses ``gameplay_eval_v2`` verbatim (seat attribution, ``PolicyActDriver``,
``HeuristicTeacher``, snapshot/grounding machinery) and adds ONE thing: at
every asked decision of every game the recorded teacher pick is compared
against the policy pick; every disagreement becomes a training row whose
label class is recorded honestly:

* ``pack``   — the site identifies a card (``may:card:N`` / ``mana:card:N``
  / ``attack:card:N:turn`` carry the source handle; scry sites carry only
  the PLAYER, so scry can never be pack-backed in game) whose (card,
  ask-kind) matches a UNIQUE gold in ``tools/audit/puzzle_corpus.json``.
  Transferable golds are CONTENT WORDS only (``fire``/``top``/``ATTACK``):
  handle/index golds (target/choose/one_of/sacrifice) refer to
  scenario-local objects and are excluded by shape, while ``mana``/``name``
  are excluded by KIND — their golds are real words but encode which card
  the SCENARIO happened to hold, a pool-content accident, not site
  knowledge. Ambiguous (card, kind) keys (conflicting golds across packs)
  are off: conflicting scenario knowledge is no knowledge.
  Pack rows are CERTIFIABLE only after a live re-falsification: the backing
  scenario is re-driven (``puzzle_cert._drive``) answering scripted gold up
  to the item and the null word (do-nothing pick) afterward; if the null
  pick still satisfies every expect lane the label is DEMOTED: the row
  falls back to the heuristic teacher's pick (also recorded), and if that
  equals the policy pick the row simply agrees and loses its label.
* ``heur``   — scripted greedy anchor (the v2 TEACHER-v2 probe).
* no label   — policy == teacher (agreement), or the ask card belongs to an
  eval family (``eval_split.json``: a gold derived from scenario puzzles
  whose packs are held out for evaluation is a LEAK, so the row is dropped
  and counted, never trained on).

Episode law (``dagger_rollout_v3`` precedent): the certifiable file
``episodes_dagger.jsonl`` = the ORIGINAL ``episodes_v2.jsonl`` lines verbatim
+ certified divergence episodes tagged ``source: "dagger"``; heuristic-label
episodes go to ``episodes_dagger_heuristic.jsonl`` and are never merged in.
Every asked decision (agreement included) stays in the per-seat history as
CONTEXT; episodes are contiguous seat streams chunked so the encoded form
fits the checkpoint ``max_len`` (oldest context trimmed); a chunk never
carries another class's gold rows. Gold ``obs`` are published WITHOUT the
private underscore tables, but their ``ground`` referent rows are recorded
at ask time exactly as the collector grounds.

Run::

    .venv/bin/python tools/eval/dagger_wave.py --games 60 --workers 4
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

from MTG_bot.core.executor.games import TURN_CAP, Supply, get_supply

from tools.eval import gameplay_eval_v2 as gv2
from tools.eval.gameplay_eval_v2 import site_kind
from tools.training import bc_data, bc_data_v2
from tools.training.ab_duel import (
    _cards_rows_of,
    classify_outcome,
    seat_swaps,
    snapshot_obs,
)
from tools.training.collector import AskContext

CORPUS = REPO / "tools" / "audit" / "puzzle_corpus.json"
SPLIT = REPO / "tools" / "audit" / "eval_split.json"
SCENARIO_DIR = REPO / "tools" / "scenarios"
EPISODES_V2 = REPO / "tools" / "training" / "episodes_v2.jsonl"
DEFAULT_STATS = Path(__file__).resolve().parent / "dagger_wave_v1.json"
DEFAULT_EPISODES = REPO / "tools" / "training" / "episodes_dagger.jsonl"
DEFAULT_HEURISTIC = REPO / "tools" / "training" / "episodes_dagger_heuristic.jsonl"

#: pack kinds whose gold is site knowledge, not a pool-content accident
#: (mana colours / named cards depend on WHICH cards the scenario held)
PACK_KINDS = frozenset({"may", "scry", "attack"})

#: episode keys internal to the wave machinery, stripped before writing
INTERNAL_EP_KEYS = ("gold_rows", "gold_meta")

COUNTER_KEYS = (
    "asks",
    "divergences",
    "div_pack",
    "div_heur",
    "pack_hit",
    "pack_miss",
    "pack_ambiguous",
    "pack_gold_illegal",
    "dropped_eval_family",
)


def _transferable(gold: str) -> bool:
    """Content word, not a handle token or a choose-index token."""
    return ":" not in gold and not gold.isdigit()


def build_pack_table(corpus: dict[str, Any]) -> dict[tuple[str, str], dict]:
    """(card, ask_kind) -> unique transferable gold + backing items.
    Conflicting golds for one key mark it AMBIGUOUS (the lane is off there);
    the corpus's own audit fields (reclassified / no_discrimination / null>0)
    exclude non-discriminating items from ever backing a label."""
    table: dict[tuple[str, str], dict[str, Any]] = {}
    for item in corpus["items"]:
        kind = item["ask_kind"]
        if kind not in PACK_KINDS or not _transferable(item["gold"]):
            continue
        key = (item["card"], kind)
        entry = table.setdefault(
            key, {"gold": item["gold"], "ambiguous": False, "backings": []}
        )
        if entry["gold"] != item["gold"]:
            entry["ambiguous"] = True
            entry["backings"] = []
            continue
        if item["null"] > 0.0 or item["reclassified"] or item["no_discrimination"]:
            continue  # not evidence: null passes, or the audit demoted it
        back = (item["pack"], item["step"], item["gold"])
        if back not in entry["backings"]:
            entry["backings"].append(back)
    return table


def load_eval_families() -> set[str]:
    return set(json.loads(SPLIT.read_text(encoding="utf-8"))["eval_families"])


# ------------------------------------------------------------------ pack lane
def pack_card_of(what: str, handle_words: set[str], names: dict[str, str]) -> str:
    """Card NAME owning a site tag: scan ``ns:idx`` tokens like resolve_seat,
    keep the first CARD handle (may/mana/name/attack carry the source)."""
    parts = what.split(":")
    for i in range(len(parts) - 1):
        token = f"{parts[i]}:{parts[i + 1]}"
        if token in handle_words and token.startswith("card:") and token in names:
            return names[token]
    return ""


def teacher_pick(
    vocab: tuple[str, ...],
    obs: dict,
    probe: Any,
    pack_table: dict[tuple[str, str], dict],
    kind: str,
    card_name: str,
    what: str,
    counters: dict[str, int],
) -> tuple[int, str, list, int]:
    """(teacher_idx, teacher_class, backings, heuristic_idx). The heuristic
    probe is evaluated on EVERY ask (it is the fallback label when a pack
    backing fails live certification)."""
    heur_idx = probe.decide(AskContext(vocab=what, candidates=tuple(vocab), world=obs))
    if not 0 <= heur_idx < len(vocab):
        heur_idx = 0  # probe contract guard
    if card_name and kind in PACK_KINDS:
        entry = pack_table.get((card_name, kind))
        if entry is None or not entry["backings"]:
            counters["pack_miss"] += 1
        elif entry["ambiguous"]:
            counters["pack_ambiguous"] += 1
        elif entry["gold"] not in vocab:
            counters["pack_gold_illegal"] += 1
        else:
            counters["pack_hit"] += 1
            return vocab.index(entry["gold"]), "pack", entry["backings"], heur_idx
    return heur_idx, "heur", [], heur_idx


# ------------------------------------------------------------- episode chunk
def row_tokens(what: str, obs: dict) -> int:
    """Exact stream cost of one ask under encode_episode_v2:
    ASK + site + obs + SEP (candidates are pointer-scored, never in seq)."""
    return 2 + len(bc_data.site_words(what)) + len(bc_data_v2.obs_words_v2(obs))


def chunk_seat(
    history: list[dict],
    golds: list[dict],
    max_len: int,
    seed: int,
    seat: int,
    cls: str,
    trunc: dict[str, int],
) -> list[dict]:
    """Gold rows (chronological) into episodes that ENCODE within max_len:
    consecutive golds share a chunk plus as much immediately-preceding
    context as fits (BOS inside the budget); a single gold row bigger than
    the budget is dropped and counted, never silently cut at its gold.
    The asks slice of a chunk EXCLUDES the other class's gold rows (file
    separation): only this chunk's golds and agreement-context rows ride.
    The budget charges EXACTLY the rows that ride (measured on the emitted
    row obs, which is what encode_episode_v2 serializes); excluded foreign
    gold rows are free, inter-gold context rows are NOT skipped."""
    if not golds:
        return []
    eps: list[dict] = []
    golds = sorted(golds, key=lambda g: g["row"])
    cost = [row_tokens(h["row"]["what"], h["row"]["obs"]) for h in history]

    def excluded(k: int, own_ij: set[int]) -> bool:
        # a labelled row that is not one of THIS chunk's golds never rides
        return history[k]["row"]["gold"] and k not in own_ij

    i, ci = 0, 0
    while i < len(golds):
        own_ij = {golds[i]["row"]}
        end = golds[i]["row"] + 1
        chunk_tokens = 1 + cost[golds[i]["row"]]
        if chunk_tokens > max_len:
            trunc["gold_row_overflow"] += 1
            i += 1
            continue
        j = i + 1
        while j < len(golds):
            nxt = golds[j]["row"]
            span = sum(
                cost[k] for k in range(end, nxt + 1) if not excluded(k, own_ij | {nxt})
            )
            if chunk_tokens + span > max_len:
                break
            chunk_tokens += span
            own_ij.add(nxt)
            end = nxt + 1
            j += 1
        start = golds[i]["row"]
        for k in range(start - 1, -1, -1):
            if excluded(k, own_ij):
                start = k
                continue  # never rides, never costs
            if chunk_tokens + cost[k] > max_len:
                break
            chunk_tokens += cost[k]
            start = k
        asks: list[dict] = []
        pos_of: dict[int, int] = {}
        for k in range(start, end):
            if excluded(k, own_ij):
                continue
            pos_of[k] = len(asks)
            asks.append(history[k]["row"])
        # exactness check: the budget IS the encoded stream size
        assert chunk_tokens == 1 + sum(row_tokens(r["what"], r["obs"]) for r in asks), (
            "chunk budget must equal the encode-visible size"
        )
        ep_id = f"daggerwave-g{seed}s{seat}{cls}c{ci}"
        eps.append(
            {
                "pack": ep_id,
                "card": ep_id,
                "source": "dagger",
                "label_class": cls,
                "backings": sorted(
                    {tuple(b) for g in golds[i:j] for b in g["backings"]}
                ),
                "n_tokens": chunk_tokens,
                "gold_meta": [
                    {
                        "pos": pos_of[g["row"]],
                        "kind": g["kind"],
                        "gold_idx": g["gold_idx"],
                        "heur_idx": g["heur_idx"],
                        "policy_idx": g["policy_idx"],
                    }
                    for g in golds[i:j]
                ],
                "asks": asks,
            }
        )
        ci += 1
        i = j
    return eps


def _renumber(eps: list[dict]) -> None:
    """Gold ordinal = position among the golds of THEIR episode (collector
    convention; context rows keep ordinal 0)."""
    for ep in eps:
        n = 0
        for row in ep["asks"]:
            if row["gold"]:
                row["ordinal"] = n
                n += 1


# ------------------------------------------------------------------ game run
def run_wave_game(
    seed: int,
    swap: bool,
    spec_a: str,
    spec_b: str,
    supply: Supply,
    pack_table: dict,
    eval_families: set[str],
    deck_pairs_seed: int = 1409,
    turn_cap: int = TURN_CAP,
    device: str = "cpu",
) -> dict[str, Any]:
    """Mirror of ``run_v2_game`` (same seats/agents/probe/driver, engine and
    rig layers both recorded) where ``book`` additionally harvests the
    divergence stream; the reused classes stay untouched."""
    bc_data_v2.install_choose_stash()
    decks = gv2.deal_decks(seed, deck_pairs_seed, supply)
    game = gv2._setup_game(seed, supply, decks)
    world = game.world
    seats = [str(s) for s in world.player_order]
    a_seat = 1 if swap else 0
    specs = {a_seat: spec_a, 1 - a_seat: spec_b}
    agents = {
        seat: (
            gv2.HeuristicTeacher()
            if specs[seat] == "teacher"
            else gv2.make_eval_policy(specs[seat], seed * 2 + seat, device)
        )
        for seat in (0, 1)
    }
    probe = gv2.HeuristicTeacher()
    counters: dict[str, int] = {
        **{k: 0 for k in COUNTER_KEYS},
        "model_errors": 0,
        "illegal_idx": 0,
    }
    kinds: dict[str, dict[str, int]] = {}
    per_seat: dict[int, dict[str, Any]] = {
        s: {"history": [], "pending": {"pack": [], "heur": []}} for s in (0, 1)
    }
    handle_words = {str(h) for h in world.cards} | {str(p) for p in world.player_order}
    names = {str(h): str(world.cards[h].identity.name) for h in world.cards}
    pt = {
        str(h): [world.cards[h].identity.power, world.cards[h].identity.toughness]
        for h in world.cards
    }
    driver = gv2.PolicyActDriver(seed, agents)

    def book(seat: int, vocab: tuple[str, ...], what: str, idx: int, obs: dict) -> None:
        kind = site_kind(what)
        kd = kinds.setdefault(kind, {"asks": 0, "div": 0, "pack_teacher": 0})
        kd["asks"] += 1
        card_name = pack_card_of(what, handle_words, names)
        t_idx, t_cls, backings, heur_idx = teacher_pick(
            vocab, obs, probe, pack_table, kind, card_name, what, counters
        )
        counters["asks"] += 1
        diverged = idx != t_idx
        labelled = diverged
        if diverged:
            kd["div"] += 1
            kd["pack_teacher"] += int(t_cls == "pack")
            counters["divergences"] += 1
            counters[f"div_{t_cls}"] += 1
            if card_name and card_name in eval_families:
                counters["dropped_eval_family"] += 1
                labelled = False  # leak guard: no scenario-derived eval gold
        st = per_seat[seat]
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
            "gold": labelled,
            "gold_idx": t_idx if labelled else None,
        }
        st["history"].append({"row": row, "_tokens": (what, obs)})
        if labelled:
            st["pending"][t_cls].append(
                {
                    "row": len(st["history"]) - 1,
                    "kind": kind,
                    "gold_idx": t_idx,
                    "heur_idx": heur_idx,
                    "policy_idx": idx,
                    "card": card_name,
                    "teacher": vocab[t_idx],
                    "backings": backings,
                }
            )

    def provider(vocab: tuple[str, ...], what: str) -> str:
        active = seats.index(str(world.active_player))
        seat = gv2.resolve_seat(what, game, seats, active, handle_words)
        obs = snapshot_obs(world, world.active_player)
        obs["_seat"] = seat
        obs["_pt"] = pt
        try:
            idx = agents[seat].decide(
                AskContext(vocab=what, candidates=tuple(vocab), world=obs)
            )
        except Exception:
            counters["model_errors"] += 1
            raise
        if not 0 <= idx < len(vocab):
            counters["illegal_idx"] += 1
            raise ValueError(f"dagger_wave: index {idx} out of {vocab}")
        book(seat, vocab, what, idx, obs)
        return vocab[idx]

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
    max_len = getattr(agents[a_seat], "max_len", 1024)
    trunc = {"gold_row_overflow": 0}
    episodes: dict[int, dict[str, list]] = {}
    for seat in (0, 1):
        episodes[seat] = {}
        for cls in ("pack", "heur"):
            eps = chunk_seat(
                per_seat[seat]["history"],
                per_seat[seat]["pending"][cls],
                max_len,
                seed,
                seat,
                cls,
                trunc,
            )
            _renumber(eps)
            episodes[seat][cls] = eps
    return {
        "seed": seed,
        "swap": swap,
        "outcome": classify_outcome(reason, winner, seats, a_seat),
        "reason": reason,
        "crash": crash or None,
        "counters": counters,
        "kinds": kinds,
        "trunc": trunc,
        "episodes": episodes,
    }


# ------------------------------------------------- live re-certification pass
def certify_backings(
    episodes: list[dict], supply: Any
) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Re-run the null falsification LIVE for every backing item a pack-class
    episode references (``puzzle_cert._drive`` answers scripted gold until
    the item's ordinal, the null word forever after): a backing whose null
    pick still satisfies the pack is NOT falsified. An episode certifies iff
    at least one backing falsifies; the rest DEMOTE to the heuristic lane —
    each gold row falls back to the recorded heuristic pick, and a row whose
    fallback equals the policy pick loses its label (silent agreement)."""
    from tools.audit import puzzle_cert as pcert

    needed = sorted({tuple(b) for ep in episodes for b in ep.get("backings", [])})
    packs: dict[str, dict] = {}
    specs: dict[str, list[dict]] = {}
    item_ok: dict[tuple, bool] = {}
    for pack_name, step, gold in needed:
        if pack_name not in packs:
            packs[pack_name] = json.loads(
                (SCENARIO_DIR / pack_name).read_text(encoding="utf-8")
            )
            specs[pack_name] = pcert.extract_items(packs[pack_name], supply)
        spec = next(
            (s for s in specs[pack_name] if s["step"] == step and s["gold"] == gold),
            None,
        )
        if spec is None:
            item_ok[(pack_name, step, gold)] = False  # drift: item no longer in pack
            continue
        null_ok = pcert._drive(
            packs[pack_name], supply, spec["ordinal"], pcert.null_word
        )[1]
        item_ok[(pack_name, step, gold)] = not null_ok  # falsified == null FAILS

    stats = {
        "backing_items": len(needed),
        "falsified": sum(item_ok.values()),
        "not_falsified": sum(not v for v in item_ok.values()),
        "episodes_demoted": 0,
        "gold_rows_demoted": 0,
        "gold_rows_dropped_agreed": 0,
        "episodes_dropped_empty": 0,
    }
    certified, demoted = [], []
    for ep in episodes:
        if any(item_ok.get(tuple(b), False) for b in ep["backings"]):
            certified.append(ep)
            continue
        stats["episodes_demoted"] += 1
        for meta in ep["gold_meta"]:
            stats["gold_rows_demoted"] += 1
            row = ep["asks"][meta["pos"]]
            if meta["heur_idx"] == meta["policy_idx"]:
                row["gold"] = False
                row["gold_idx"] = None
                stats["gold_rows_dropped_agreed"] += 1
            else:
                row["gold_idx"] = meta["heur_idx"]
        if not any(r["gold"] for r in ep["asks"]):
            stats["episodes_dropped_empty"] += 1
            continue
        ep["label_class"] = "heur"
        ep["pack"] = ep["card"] = ep["card"].replace("pack", "heurD")
        ep["backings"] = []
        _renumber([ep])
        demoted.append(ep)
    return certified, demoted, stats


# ------------------------------------------------------------------ batch
_G: dict[str, Any] = {}


def _init_worker(
    pool_mode: str,
    specs: tuple[str, ...],
    device: str,
    pack_table: dict,
    eval_families: set[str],
) -> None:
    import torch

    torch.set_num_threads(1)
    _G["supply"] = get_supply(pool_mode)
    _G["pack_table"] = pack_table
    _G["eval_families"] = eval_families
    for spec in specs:
        if spec.endswith(".pt"):
            from tools.training.ab_duel import BcAsk

            BcAsk.fresh(spec, device)


def _worker(job: dict[str, Any]) -> dict[str, Any]:
    return run_wave_game(
        job["seed"],
        job["swap"],
        job["spec_a"],
        job["spec_b"],
        supply=_G["supply"],
        pack_table=_G["pack_table"],
        eval_families=_G["eval_families"],
        deck_pairs_seed=job["deck_pairs_seed"],
        turn_cap=job["turn_cap"],
        device=job["device"],
    )


def _merge(dst: dict[str, int], src: dict[str, int]) -> None:
    for k, v in src.items():
        dst[k] = dst.get(k, 0) + v


def write_jsonl(path: Path, episodes: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for ep in episodes:
            clean = {k: v for k, v in ep.items() if k not in INTERNAL_EP_KEYS}
            fh.write(json.dumps(clean) + "\n")


def _gold_rows_of(episodes: list[dict]) -> int:
    return sum(sum(1 for row in ep["asks"] if row["gold"]) for ep in episodes)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DAgger wave 1 divergence harvest.")
    ap.add_argument("--policy-a", default=gv2.DEFAULT_POLICY_A)
    ap.add_argument("--policy-b", default=gv2.DEFAULT_POLICY_B)
    ap.add_argument("--games", type=int, default=60, help="full-agent games")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--pool", default="engine", choices=("all", "engine", "castable"))
    ap.add_argument("--deck-pairs-seed", type=int, default=1409)
    ap.add_argument("--turn-cap", type=int, default=TURN_CAP)
    ap.add_argument("--seed-base", type=int, default=700000)
    ap.add_argument("--device", default="cpu", choices=("auto", "cpu", "cuda"))
    ap.add_argument("--out", type=Path, default=DEFAULT_STATS)
    ap.add_argument("--episodes-out", type=Path, default=DEFAULT_EPISODES)
    ap.add_argument("--heuristic-out", type=Path, default=DEFAULT_HEURISTIC)
    ap.add_argument(
        "--base-episodes",
        type=Path,
        default=EPISODES_V2,
        help="original lines prepended to the certifiable file ('' = none)",
    )
    args = ap.parse_args(argv)

    policy_a = str(Path(args.policy_a).resolve())
    policy_b = str(Path(args.policy_b).resolve())
    dev = args.device
    if dev == "auto":
        import torch

        dev = "cuda" if torch.cuda.is_available() else "cpu"

    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    pack_table = build_pack_table(corpus)
    eval_families = load_eval_families()

    seeds = list(range(args.seed_base + 1, args.seed_base + 1 + args.games))
    swaps = seat_swaps(args.games)
    jobs = [
        {
            "seed": s,
            "swap": sw,
            "spec_a": policy_a,
            "spec_b": policy_b,
            "deck_pairs_seed": args.deck_pairs_seed,
            "turn_cap": args.turn_cap,
            "device": dev,
        }
        for s, sw in zip(seeds, swaps, strict=True)
    ]
    specs = (policy_a, policy_b)
    started = time.perf_counter()
    if args.workers <= 1:
        _init_worker(args.pool, specs, dev, pack_table, eval_families)
        records = [_worker(j) for j in jobs]
    else:
        ctx = multiprocessing.get_context("spawn")
        with ctx.Pool(
            args.workers,
            initializer=_init_worker,
            initargs=(args.pool, specs, dev, pack_table, eval_families),
        ) as pool:
            records = pool.map(_worker, jobs, chunksize=1)
    elapsed = time.perf_counter() - started

    # ---- parent: merge counters, certify pack backings LIVE, write files
    totals: dict[str, int] = {k: 0 for k in COUNTER_KEYS}
    kinds_tot: dict[str, dict[str, int]] = {}
    trunc_tot = {"gold_row_overflow": 0}
    pack_eps, heur_eps = [], []
    for rec in records:
        _merge(totals, rec["counters"])
        _merge(trunc_tot, rec["trunc"])
        for kind, kd in rec["kinds"].items():
            _merge(
                kinds_tot.setdefault(kind, {"asks": 0, "div": 0, "pack_teacher": 0}), kd
            )
        for seat_eps in rec["episodes"].values():
            pack_eps.extend(seat_eps.get("pack", []))
            heur_eps.extend(seat_eps.get("heur", []))
    pack_eps.sort(key=lambda e: e["pack"])
    heur_eps.sort(key=lambda e: e["pack"])

    cert_stats = {
        "backing_items": 0,
        "falsified": 0,
        "not_falsified": 0,
        "episodes_demoted": 0,
        "gold_rows_demoted": 0,
        "gold_rows_dropped_agreed": 0,
        "episodes_dropped_empty": 0,
    }
    if pack_eps:
        # packs may name cards outside the game pool — certify on pcert's pool
        cert_supply = get_supply("all")
        pack_eps, demoted, cert_stats = certify_backings(pack_eps, cert_supply)
        heur_eps = sorted(heur_eps + demoted, key=lambda e: e["pack"])

    base_lines: list[dict] = []
    if args.base_episodes and args.base_episodes.name not in ("", "."):
        base_lines = [
            json.loads(line)
            for line in args.base_episodes.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    write_jsonl(args.episodes_out, base_lines + pack_eps)
    write_jsonl(args.heuristic_out, heur_eps)

    biggest = max(
        kinds_tot.items(), key=lambda kv: kv[1].get("div", 0), default=("", {})
    )
    out: dict[str, Any] = {
        "meta": {
            "date": time.strftime("%Y-%m-%d %H:%M"),
            "version": "dagger-wave-v1",
            "policy_a": policy_a,
            "policy_b": policy_b,
            "pool_mode": args.pool,
            "turn_cap": args.turn_cap,
            "games": args.games,
            "seats_policy_both": True,
            "seeds": [seeds[0], seeds[-1]] if seeds else [],
            "deck_pairs_seed": args.deck_pairs_seed,
            "device": dev,
            "workers": args.workers,
            "seconds": round(elapsed, 1),
            "teacher_lanes": (
                "pack lane = unique content-word gold for (card-from-site-tag, "
                "ask-kind) in puzzle_corpus, kinds may/scry/attack only, "
                "ambiguous keys off, live null re-falsification required "
                "(fallback = heuristic pick); otherwise the v2 heuristic "
                "probe. Scry sites carry no source card in-game, so scry "
                "labels are heuristic-only by tag law. Eval-family diver-"
                "gences are dropped as leak (counted), never labelled."
            ),
        },
        "totals": totals,
        "divergence_rate": (
            round(totals["divergences"] / totals["asks"], 4) if totals["asks"] else 0.0
        ),
        "per_kind": {
            k: {
                **kd,
                "div_rate": round(kd.get("div", 0) / kd["asks"], 4)
                if kd["asks"]
                else 0.0,
            }
            for k, kd in sorted(kinds_tot.items())
        },
        "biggest_disagreement": {"kind": biggest[0], **biggest[1]},
        "certification": cert_stats,
        "truncation": trunc_tot,
        "crashes": [r["seed"] for r in records if r["crash"]],
        "outcomes": {
            o: sum(1 for r in records if r["outcome"] == o)
            for o in sorted({str(r["outcome"]) for r in records})
        },
        "files": {
            "episodes_dagger": {
                "path": str(args.episodes_out),
                "episodes": len(base_lines) + len(pack_eps),
                "original_base_lines": len(base_lines),
                "certified_dagger_episodes": len(pack_eps),
                "certified_gold_rows": _gold_rows_of(pack_eps),
            },
            "episodes_dagger_heuristic": {
                "path": str(args.heuristic_out),
                "episodes": len(heur_eps),
                "heuristic_gold_rows": _gold_rows_of(heur_eps),
            },
        },
        "records": [
            {
                **{k: v for k, v in r.items() if k != "episodes"},
                "episodes_pack": sum(
                    len(v.get("pack", [])) for v in r["episodes"].values()
                ),
                "episodes_heur": sum(
                    len(v.get("heur", [])) for v in r["episodes"].values()
                ),
            }
            for r in records
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(
        f"games={args.games} asks={totals['asks']} div={totals['divergences']} "
        f"({out['divergence_rate']:.1%}) pack_teacher={totals['pack_hit']} "
        f"certified_eps={len(pack_eps)} heur_eps={len(heur_eps)} "
        f"demoted={cert_stats['episodes_demoted']} {elapsed:.0f}s -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
