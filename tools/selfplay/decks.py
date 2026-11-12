"""The drafter v0 (docs/PLAN_DRAFTER.md): the decks of recorded games, rebuilt.

Self-play deals both decks from the seed: ``deal_decks(seed, 1409, get_supply(pool, set), mode)``
(rig.py:159), deck i to seat i. So a game's row rebuilds them, but only with the code that built
the run's pool: a later pool rebuilds other decks that still look legal (PLAN_DRAFTER §3). So
``rebuild`` extracts that commit's MTG_bot under runs/code/ and runs this file as a worker against
it. The worker imports only the standard library, numpy and that MTG_bot.

Output (``.npz``): per deal its seed, deck mode and set, and both decks as sparse counts (``off``
into ``idx``/``cnt``, two entries per deal, seat 0 first) over the cards met (``card``: oracle ids,
with name, basic, land, mana value, creature, colour identity and rarity).

    .venv/bin/python -m tools.selfplay.decks rebuild COMMIT OUT.npz ROWS.jsonl... [--pool verified]
    .venv/bin/python -m tools.selfplay.decks check-capture COMMIT CAPTURE_DIR [--pool verified]
    .venv/bin/python -m tools.selfplay.decks fit OUT.json --source RUN ROWS.jsonl DECKS.npz ...

``fit`` is the critic of PLAN_DRAFTER §4: a value per card from the games' results, scored against
a baseline of the colour pair, the seat, the pilots and 12 deck summaries by held-out log-loss
(G1), and ``swap`` is §5's construction on it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
CODE = REPO / "runs" / "code"
DEAL_SEED = 1409  # rig.play_game's deck_pairs_seed
MODES = ("coherent", "stress")


def extract(commit: str) -> Path:
    """MTG_bot at ``commit``, extracted once under runs/code/<full sha>/."""
    sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", f"{commit}^{{commit}}"],
                         check=True, capture_output=True, text=True).stdout.strip()
    tree = CODE / sha
    if not (tree / ".extracted").exists():
        tree.mkdir(parents=True, exist_ok=True)
        archive = subprocess.run(["git", "-C", str(REPO), "archive", sha, "MTG_bot"], check=True,
                                 capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(tree)], input=archive, check=True)
        (tree / ".extracted").write_text(sha + "\n")
    return tree


def run_worker(commit: str, *args: str) -> None:
    """This file as a worker on ``commit``'s engine (-P: the script's folder is not on the path)."""
    tree = extract(commit)
    subprocess.run([sys.executable, "-P", str(Path(__file__).resolve()), "_worker", str(tree),
                    *args], check=True, cwd=tree, env={**os.environ, "PYTHONPATH": str(tree)})


def deals_in(rows_paths: list[str]) -> list[tuple[int, str, str]]:
    """The distinct deals (seed, deck mode, set) of rows files, in a fixed order."""
    out = set()
    for p in rows_paths:
        with open(p) as fh:
            for line in fh:
                r = json.loads(line)
                if r.get("deck_mode") in MODES and r.get("seed") is not None:
                    out.add((int(r["seed"]), r["deck_mode"], r.get("set_code") or "M21"))
    return sorted(out)


def _rarities(set_code: str) -> dict[str, str]:
    from MTG_bot import __file__ as root
    data = json.loads((Path(root).parent / "data" / f"{set_code}.json").read_text())
    return {c["identifiers"]["scryfallOracleId"]: c["rarity"]
            for c in data.get("data", data)["cards"]
            if c.get("identifiers", {}).get("scryfallOracleId")}


def _rebuild_here(out: str, pool: str, commit: str, rows_paths: list[str]) -> None:
    from MTG_bot.core.executor.games import deal_decks, get_supply

    deals = deals_in(rows_paths)
    supplies, rarity, cards, meta = {}, {}, {}, []
    off, idx, cnt = [0], [], []
    for seed, mode, set_code in deals:
        if set_code not in supplies:
            supplies[set_code] = get_supply(pool, set_code)
            rarity.update(_rarities(set_code))
        sup = supplies[set_code]
        for deck in deal_decks(seed, DEAL_SEED, sup, mode):
            for oid, n in sorted(Counter(deck).items()):
                if oid not in cards:
                    cards[oid] = len(cards)
                    m = sup.metas[oid]
                    meta.append((m.name, m.is_basic, m.is_land, m.mana_value,
                                 "Creature" in m.type_line,
                                 "".join(sorted(sup.pool.results[oid].card.color_identity)),
                                 rarity.get(oid, "")))
                idx.append(cards[oid])
                cnt.append(n)
            off.append(len(idx))
    cols = list(zip(*meta, strict=True)) if meta else [()] * 7
    np.savez_compressed(
        out, seed=np.array([d[0] for d in deals], np.int64), mode=np.array([d[1] for d in deals]),
        set=np.array([d[2] for d in deals]), off=np.array(off, np.int64),
        idx=np.array(idx, np.int16), cnt=np.array(cnt, np.int8), card=np.array(list(cards)),
        name=np.array(cols[0]), basic=np.array(cols[1], bool), land=np.array(cols[2], bool),
        mv=np.array(cols[3], np.int16), creature=np.array(cols[4], bool), ci=np.array(cols[5]),
        rarity=np.array(cols[6]), pool=np.array(pool), commit=np.array(commit))
    print(json.dumps({"deals": len(deals), "cards": len(cards), "out": out}))


def _check_capture_here(cap: str, pool: str) -> None:
    """Every capture position's opponent: hidden cards (true hand and library) plus its public
    cards must equal the rebuilt deck of that seat. The capture deals coherent decks."""
    from MTG_bot.core.executor.games import deal_decks, get_supply

    oids = json.loads((Path(cap) / "table.json").read_text())["oracle_ids"]
    supplies, decks = {}, {}
    n = bad = 0
    for vf in sorted(Path(cap).glob("views_*.npz"), key=lambda p: int(p.stem.split("_")[1])):
        v, t = np.load(vf), np.load(vf.with_name("truth" + vf.name[5:]))
        if not np.array_equal(v["seed"], t["seed"]):
            raise ValueError(f"{vf}: views and truth are not the same positions")
        for i in range(len(v["seed"])):
            key = (int(v["seed"][i]), str(v["set"][i]))
            if key not in decks:
                if key[1] not in supplies:
                    supplies[key[1]] = get_supply(pool, key[1])
                decks[key] = [Counter(d) for d in
                              deal_decks(key[0], DEAL_SEED, supplies[key[1]], "coherent")]
            rows = np.concatenate([t["hand"][t["hand_off"][i]:t["hand_off"][i + 1]],
                                   t["lib"][t["lib_off"][i]:t["lib_off"][i + 1]],
                                   v["public"][v["public_off"][i]:v["public_off"][i + 1]]])
            n += 1
            bad += Counter(oids[r] for r in rows) != decks[key][1 - int(v["seat"][i])]
    print(json.dumps({"positions": n, "games": len(decks), "mismatches": int(bad)}))


def _worker(tree: str, mode: str, *args: str) -> None:
    import MTG_bot

    if not Path(MTG_bot.__file__).resolve().is_relative_to(Path(tree).resolve()):
        raise SystemExit(f"the worker imported MTG_bot from {MTG_bot.__file__}, not {tree}")
    if mode == "rows":
        _rebuild_here(args[0], args[1], (Path(tree) / ".extracted").read_text().strip(),
                      list(args[2:]))
    elif mode == "capture":
        _check_capture_here(args[0], args[1])
    else:
        raise SystemExit(f"unknown worker mode {mode!r}")


# ----------------------------------------------------- the critic (PLAN_DRAFTER §4), main side

NON_NETWORK = ("heuristic", "random")
RARITIES = ("common", "uncommon", "rare", "mythic")
MV_BUCKETS = 7  # spells of mana value 0, 1, ..., 5, 6 or more


def pilot(run: str, r: dict, seat: int) -> str:
    """Who played a seat: a frozen version by name, the network under evaluation or training by
    when (its gate's tag, or its update in blocks of 25), always within its run."""
    spec = r["seats"][seat]
    if spec in ("learner", "eval", "eval+search"):
        when = r.get("tag") or f"it{int(r.get('it', 0)) // 25 * 25}"
        return f"{run}:{spec}@{when}"
    return f"{run}:{spec}"


def games(rows: str, decks: dict, run: str, modes: tuple[str, ...] = ("coherent",)) -> list:
    """The decided games of a rows file between two networks: (deal index in ``decks``, seat 0
    won, seat 0's pilot, seat 1's pilot, seed)."""
    at = {(int(s), str(m), str(t)): i
          for i, (s, m, t) in enumerate(zip(decks["seed"], decks["mode"], decks["set"],
                                            strict=True))}
    out = []
    with open(rows) as fh:
        for line in fh:
            r = json.loads(line)
            if (r.get("deck_mode") not in modes or r.get("outcome") != "win"
                    or r.get("winner") not in (0, 1) or any(s in NON_NETWORK for s in r["seats"])):
                continue
            key = (int(r["seed"]), r["deck_mode"], r.get("set_code") or "M21")
            if key not in at:
                raise ValueError(f"{rows}: deal {key} is not among the rebuilt decks")
            out.append((at[key], int(r["winner"] == 0), pilot(run, r, 0), pilot(run, r, 1),
                        key[0]))
    return out


def design(sources: list[tuple[dict, list]], cards: bool) -> tuple:
    """X, y and the seeds of the games of every (decks, games) source, over one vocabulary.

    Columns: per card (or, when ``cards`` is false, the 12 deck summaries plus the basics, which
    carry the colour pair) the difference seat 0 minus seat 1, then per pilot +1 for seat 0 and -1
    for seat 1. The summaries are linear in the counts, so the card model nests the baseline."""
    vocab = sorted({str(c) for d, _ in sources for c in d["card"]})
    col = {c: i for i, c in enumerate(vocab)}
    meta = {}
    for d, _ in sources:
        for j, c in enumerate(d["card"]):
            meta[str(c)] = {k: d[k][j] for k in ("basic", "land", "mv", "creature", "rarity")}
    if cards:
        feat = np.eye(len(vocab), dtype=np.float32)
    else:
        basics = [c for c in vocab if meta[c]["basic"]]
        feat = np.zeros((len(vocab), MV_BUCKETS + 1 + len(RARITIES) + len(basics)), np.float32)
        for i, c in enumerate(vocab):
            m = meta[c]
            if m["basic"]:
                feat[i, MV_BUCKETS + 1 + len(RARITIES) + basics.index(c)] = 1
            elif not m["land"]:
                feat[i, min(int(m["mv"]), MV_BUCKETS - 1)] = 1
                feat[i, MV_BUCKETS] = float(m["creature"])
                if m["rarity"] in RARITIES:
                    feat[i, MV_BUCKETS + 1 + RARITIES.index(m["rarity"])] = 1
    pilots = sorted({p for _, g in sources for x in g for p in x[2:4]})
    pc = {p: i for i, p in enumerate(pilots)}
    n = sum(len(g) for _, g in sources)
    counts = np.zeros((n, len(vocab)), np.float32)
    pil = np.zeros((n, len(pilots)), np.float32)
    y = np.zeros(n, np.float32)
    seeds = np.zeros(n, np.int64)
    row = 0
    for d, g in sources:
        to = np.array([col[str(c)] for c in d["card"]])
        off, idx, cnt = d["off"], d["idx"], d["cnt"]
        for k, won, p0, p1, seed in g:
            for s, sign in ((0, 1.0), (1, -1.0)):
                a, b = off[2 * k + s], off[2 * k + s + 1]
                np.add.at(counts[row], to[idx[a:b]], sign * cnt[a:b])
            pil[row, pc[p0]] += 1
            pil[row, pc[p1]] -= 1
            y[row], seeds[row] = won, seed
            row += 1
    return np.concatenate([counts @ feat, pil], 1), y, seeds, vocab, feat, len(pilots)


def fit(x: np.ndarray, y: np.ndarray, lam: float) -> tuple[np.ndarray, float]:
    """L2-penalised logistic regression (full-batch L-BFGS): the weights and the intercept,
    which is seat 0's edge (it is on the play)."""
    import torch

    xt, yt = torch.from_numpy(x).double(), torch.from_numpy(y).double()
    w = torch.zeros(x.shape[1], dtype=torch.float64, requires_grad=True)
    b = torch.zeros(1, dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([w, b], max_iter=500, tolerance_grad=1e-9,
                            line_search_fn="strong_wolfe")

    def closure():
        opt.zero_grad()
        loss = torch.nn.functional.binary_cross_entropy_with_logits(xt @ w + b, yt) + lam * (w @ w)
        loss.backward()
        return loss

    opt.step(closure)
    return w.detach().numpy(), float(b.detach())


def logloss(x: np.ndarray, y: np.ndarray, w: np.ndarray, b: float) -> np.ndarray:
    z = x @ w + b
    return np.logaddexp(0, z) - y * z


def cross_validate(x: np.ndarray, y: np.ndarray, seeds: np.ndarray, lams: tuple[float, ...],
                   folds: int = 5) -> dict:
    """Held-out log-loss by folds of deals (seed % folds): every game of a deal in one fold. The
    penalty is the grid's best by mean held-out loss; the per-game held-out losses and
    probabilities come with it."""
    fold = seeds % folds
    best: dict = {}
    for lam in lams:
        loss, prob = np.zeros(len(y)), np.zeros(len(y))
        for f in range(folds):
            w, b = fit(x[fold != f], y[fold != f], lam)
            loss[fold == f] = logloss(x[fold == f], y[fold == f], w, b)
            prob[fold == f] = 1 / (1 + np.exp(-(x[fold == f] @ w + b)))
        if not best or loss.mean() < best["loss"].mean():
            best = {"lam": lam, "loss": loss, "p": prob}
    return best


def swap(deck: Counter, value: dict[str, float], spells: list[str], k: int,
         ok: Callable[[Counter], bool] | None = None) -> Counter:
    """k swaps on a deck (PLAN_DRAFTER §5): each removes the least valuable spell copy and adds
    the most valuable spell of ``spells`` with a copy free, the best gain first among the pairs
    that keep ``ok(deck)``; it stops early when no swap gains. Deterministic: ties go to the
    oracle id that sorts first."""
    deck = Counter(deck)
    for _ in range(k):
        have = sorted((c for c in deck if c in value and deck[c] > 0 and c in spells),
                      key=lambda c: (value[c], c))
        free = sorted((c for c in spells if deck[c] < 4), key=lambda c: (-value[c], c))
        moves = sorted(((value[i] - value[o], o, i) for o in have for i in free
                        if i != o and value[i] > value[o]), key=lambda m: (-m[0], m[1], m[2]))
        for _gain, o, i in moves:
            nxt = deck.copy()
            nxt[o] -= 1
            nxt[i] += 1
            if ok is None or ok(+nxt):
                deck = +nxt
                break
        else:
            break
    return deck


def calibration(p: np.ndarray, y: np.ndarray, bins: int = 15) -> tuple[float, float]:
    """Expected and largest calibration error over equal-mass bins."""
    errs = [(len(b), abs(float(p[b].mean() - y[b].mean())))
            for b in np.array_split(np.argsort(p), bins) if len(b)]
    return sum(n * e for n, e in errs) / len(p), max(e for _, e in errs)


def fit_critic(out: str, sources: list[list[str]], lams: tuple[float, ...]) -> dict:
    """G1 on the sources' games (both models cross-validated over ``lams``), then the card model
    on every game, written to ``out`` with its hash."""
    loaded = []
    for run, rows, path in sources:
        z = np.load(path)
        d = {k: z[k] for k in z.files}
        loaded.append((d, games(rows, d, run)))
    report: dict = {"games": sum(len(g) for _, g in loaded)}
    res = {}
    for name, cards in (("baseline", False), ("cards", True)):
        x, y, seeds, vocab, feat, n_pil = design(loaded, cards)
        res[name] = cross_validate(x, y, seeds, lams)
        report[name] = {"lam": res[name]["lam"],
                        "logloss": round(float(res[name]["loss"].mean()), 5)}
    per_deal = Counter()
    for s, dl in zip(seeds, res["cards"]["loss"] - res["baseline"]["loss"], strict=True):
        per_deal[int(s)] += float(dl)
    dv = np.array(list(per_deal.values())) / (len(seeds) / len(per_deal))
    report["gain"] = {"mean": round(float(-dv.mean()), 5),
                      "se": round(float(dv.std(ddof=1) / np.sqrt(len(dv))), 5), "deals": len(dv)}
    for name in res:
        report[name]["calibration"] = [round(v, 5) for v in calibration(res[name]["p"], y)]
    w, b = fit(x, y, res["cards"]["lam"])
    value = {c: round(float(v), 6) for c, v in zip(vocab, w[:len(vocab)], strict=True)}
    names = {}
    for d, _ in loaded:
        names.update({str(c): str(nm) for c, nm in zip(d["card"], d["name"], strict=True)})
    critic = {"value": value, "name": names, "seat0": b, "lam": res["cards"]["lam"],
              "sources": sources, "report": report}
    blob = json.dumps(critic, sort_keys=True).encode()
    critic["sha256"] = hashlib.sha256(blob).hexdigest()
    Path(out).write_text(json.dumps(critic, indent=1, sort_keys=True) + "\n")
    report["sha256"] = critic["sha256"]
    return report


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "_worker":
        _worker(*argv[1:])
        return 0
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    rb = sub.add_parser("rebuild")
    rb.add_argument("commit")
    rb.add_argument("out")
    rb.add_argument("rows", nargs="+")
    rb.add_argument("--pool", default="verified")
    cc = sub.add_parser("check-capture")
    cc.add_argument("commit")
    cc.add_argument("capture")
    cc.add_argument("--pool", default="verified")
    ft = sub.add_parser("fit")
    ft.add_argument("out")
    ft.add_argument("--source", nargs=3, action="append", required=True,
                    metavar=("RUN", "ROWS", "DECKS"))
    ft.add_argument("--lams", default="1e-4,1e-3,3e-3,1e-2,3e-2,1e-1")
    a = ap.parse_args(argv)
    if a.cmd == "rebuild":
        run_worker(a.commit, "rows", str(Path(a.out).resolve()), a.pool,
                   *[str(Path(r).resolve()) for r in a.rows])
    elif a.cmd == "check-capture":
        run_worker(a.commit, "capture", str(Path(a.capture).resolve()), a.pool)
    else:
        print(json.dumps(fit_critic(a.out, a.source, tuple(map(float, a.lams.split(","))))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
