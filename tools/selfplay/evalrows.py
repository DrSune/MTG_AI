"""One reading of evaluation rows and one name per player, for every tool that scores games
(the learner's summaries, paired.py, rate.py, ncurve.py).

An evaluation row (``<run>/eval_rows.jsonl``, written by learner.on_done) is one game of a deal
against one opponent, seen from the evaluated seat (``a_seat``). A deal is (opponent, set, pool,
seed, deck mode); its two games swap the seats. The rules:

- a game scores 1 for a win, 0 for a loss and 0.5 for any draw (``score``);
- a deal counts only with both of its games, neither void nor leaky, and its score is their mean
  (``deal_scores``): a void game drops its whole deal, because the other game alone is one seat's,
  and the seats are not equal;
- a row written again for the same (evaluation, deal, seat), by a re-run step or a resumed
  evaluation, replaces the earlier one (``read``).

A player (``settings``, ``member``) is everything that decides how one seat of an evaluation run
plays, read from its manifest's arguments: the network's checkpoint or a scripted player's name,
the search when the seat searches, the inference precision and name masking. Two runs whose
players differ in any of these are different players (KNOWLEDGE/2026-11-12/197: three separate
definitions had merged searches with other worlds, simulators or horizons into one).
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from tools.selfplay.actor import SEARCH_SUFFIX

SCRIPTED = ("heuristic", "random")
#: The search flags that change how a searching seat plays, by root, then for every root.
ROOT_FLAGS = {"topk": ("search_k", "search_d"), "gumbel": ("search_m", "search_n")}
SEARCH_FLAGS = ("search_horizon", "search_continuation", "search_kinds", "search_skip_p",
                "search_blocks", "search_worlds")


def score(r: dict) -> float:
    return 0.5 if r["outcome"] != "win" else float(r["winner"] == r["a_seat"])


def void(r: dict) -> bool:
    return r["outcome"].startswith("void") or bool(r.get("leaky"))


def deal_key(r: dict) -> tuple:
    """(opponent, set, pool, seed, deck mode). Rows written before the learner recorded set and
    pool hold None there, and pair only with each other."""
    return (r.get("opp"), r.get("set_code"), r.get("pool"), r["seed"], r.get("deck_mode"))


def by_deal(rows: Iterable[dict]) -> dict[tuple, dict[int, dict]]:
    """Rows by deal and seat, a later row replacing an earlier one."""
    out: dict[tuple, dict[int, dict]] = defaultdict(dict)
    for r in rows:
        out[deal_key(r)][r["a_seat"]] = r
    return out


def read(path: str | Path, tag: str | None = None, opp: str | None = None
         ) -> dict[tuple, dict[int, dict]]:
    """One evaluation's rows of an eval_rows.jsonl, by deal and seat (``by_deal``). A file
    holding more than one evaluation (a training run's does) needs its ``tag``: rows of two
    evaluations would otherwise replace each other."""
    rows, tags = [], set()
    with open(path) as fh:
        for line in fh:
            r = json.loads(line)
            tags.add(r.get("tag"))
            if (tag is None or r.get("tag") == tag) and (opp is None or r.get("opp") == opp):
                rows.append(r)
    if tag is None and len(tags) > 1:
        raise ValueError(f"{path} holds {len(tags)} evaluations: pass one's tag "
                         f"({', '.join(sorted(str(t) for t in tags))})")
    return by_deal(rows)


def valid(games: dict[tuple, dict[int, dict]]) -> dict[tuple, dict[int, dict]]:
    """The deals with both games, neither void nor leaky."""
    return {k: g for k, g in games.items()
            if set(g) == {0, 1} and not any(void(r) for r in g.values())}


def deal_scores(games: dict[tuple, dict[int, dict]]) -> dict[tuple, float]:
    """Each valid deal's score: the mean of its two games."""
    return {k: (score(g[0]) + score(g[1])) / 2 for k, g in valid(games).items()}


def settings(args: dict[str, Any], seat: str) -> dict[str, Any]:
    """Everything that decides how ``seat`` ("eval", "snap:opp", a scripted player, with
    actor.SEARCH_SUFFIX when it searches) of an evaluation run plays, from the run's arguments."""
    base = seat.removesuffix(SEARCH_SUFFIX)
    if base in SCRIPTED:
        return {"player": base}
    out: dict[str, Any] = {"player": {"eval": args.get("init"),
                                      "snap:opp": args.get("opp_ckpt")}.get(base, base)}
    if seat.endswith(SEARCH_SUFFIX):
        root = args.get("search_root", "topk")
        out["search_root"] = root
        for key in ROOT_FLAGS.get(root, ()) + SEARCH_FLAGS:
            out[key] = args.get(key)
        if args.get("search_worlds") == "sim":
            out["search_sim"] = args.get("search_sim")
    out["precision"] = "bf16" if args.get("infer_bf16") else "fp32"
    if args.get("mask_names"):
        out["mask_names"] = True
    return out


def member(args: dict[str, Any], seat: str) -> str:
    """A player's name: its checkpoint or scripted name, then each other setting as key=value."""
    st = settings(args, seat)
    return "+".join([str(st["player"])] + [f"{k.removeprefix('search_')}={v}"
                                          for k, v in st.items() if k != "player"])
