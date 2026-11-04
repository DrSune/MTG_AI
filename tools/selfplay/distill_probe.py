"""Does distillation generalise? Score networks on one generation of a run's saved search labels
(state.pkl), split by held-out vs trained games and by whether the search changed the move of
the network that generated the labels (--prior).

    .venv/bin/python -m tools.selfplay.distill_probe --state runs/selfplay/r13_exit/state.pkl \
        --prior runs/selfplay/r12_exit/last.pt --nets runs/selfplay/r13_exit/last.pt

Holdout is the learner's rule (gid % every == 0, every = int(1 / --holdout)). "changed" rows are
the informative labels: what the search added over the network's own greedy move, bucketed by the
search's score margin (recovered from the soft target, --tau = the run's --search-tau). A network
that generalises the search raises its accuracy on HELD-OUT changed rows, not only trained ones.
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
from collections import defaultdict

import torch

from tools.selfplay import model as M

MARGINS = (0.02, 0.1)  # bucket edges for the search's score margin over the network's move


def margin(soft: list, idx: int, a0: int, probs: list, tau: float) -> float | None:
    """The search's score margin (label minus the network's move a0), recovered from the soft
    target t ~ prior x exp(score / tau): tau * (ln(t_idx / t_a0) - ln(p_idx / p_a0))."""
    t = dict(soft)
    if idx not in t or a0 not in t or min(t[idx], t[a0], probs[idx], probs[a0]) <= 0:
        return None
    return tau * (math.log(t[idx] / t[a0]) - math.log(probs[idx] / probs[a0]))


@torch.no_grad()
def score(net: torch.nn.Module, rows: list, device: torch.device, bs: int = 256) -> list[tuple]:
    """(argmax, prob of the label, cross-entropy to the soft target or None, probs) per row."""
    order = sorted(range(len(rows)), key=lambda i: rows[i][0]["cards_i"].shape[0])
    out: list = [None] * len(rows)
    for s in range(0, len(order), bs):
        ch = order[s:s + bs]
        b = M.collate([rows[i][0] for i in ch], device)
        with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
            logits, _ = net(b)
        logp = torch.log_softmax(logits.float(), -1)
        top = logp.argmax(-1).tolist()
        for r, i in enumerate(ch):
            idx = rows[i][1]
            soft = rows[i][5] if len(rows[i]) > 5 else None
            ce = -sum(p * float(logp[r, j]) for j, p in soft) if soft else None
            k = rows[i][0]["opts_i"].shape[0]
            out[i] = (int(top[r]), float(logp[r, idx].exp()), ce, logp[r, :k].exp().tolist())
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--gen", type=int, default=-1, help="window index (-1: newest generation)")
    ap.add_argument("--prior", required=True, help="the network that generated the labels")
    ap.add_argument("--nets", nargs="+", required=True)
    ap.add_argument("--holdout", type=float, default=0.03)
    ap.add_argument("--tau", type=float, default=0.05, help="the run's --search-tau")
    ap.add_argument("--plain-max", type=int, default=20000,
                    help="unsearched rows scored (a subsample; they are the network's own moves)")
    args = ap.parse_args(argv)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    with open(args.state, "rb") as fh:
        st = pickle.load(fh)
    rows = st["window"][args.gen]
    every = max(2, int(1 / max(args.holdout, 1e-3)))
    searched = [r for r in rows if len(r) > 5 and r[5]]
    plain = [r for r in rows if not (len(r) > 5 and r[5])][: args.plain_max]
    data = searched + plain
    prior, _, _ = M.load(args.prior, device)
    pri = score(prior.eval(), data, device)
    del prior
    groups: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(data):
        split = "held" if r[3] % every == 0 else "train"
        if i >= len(searched):
            kind = "plain"
        elif pri[i][0] == r[1]:
            kind = "kept"
        else:
            m = margin(r[5], r[1], pri[i][0], pri[i][3], args.tau)
            kind = ("changed?" if m is None else
                    f"changed<{MARGINS[0]}" if m < MARGINS[0] else
                    f"changed<{MARGINS[1]}" if m < MARGINS[1] else f"changed>={MARGINS[1]}")
        groups[f"{split}/{kind}"].append(i)
    report: dict = {"state": args.state, "gen": args.gen, "rows": len(rows),
                    "searched": len(searched), "every": every,
                    "groups": {k: len(v) for k, v in sorted(groups.items())}}
    for path in [args.prior] + args.nets:
        if path == args.prior:
            res = pri
        else:
            net, _, _ = M.load(path, device)
            res = score(net.eval(), data, device)
            del net
        stats = {}
        for g, ids in sorted(groups.items()):
            acc = sum(res[i][0] == data[i][1] for i in ids) / max(len(ids), 1)
            p = sum(res[i][1] for i in ids) / max(len(ids), 1)
            ces = [res[i][2] for i in ids if res[i][2] is not None]
            stats[g] = {"acc": round(acc, 4), "p_label": round(p, 4),
                        "ce_soft": round(sum(ces) / len(ces), 4) if ces else None}
        report[path] = stats
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
