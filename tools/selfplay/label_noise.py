"""How reproducible are search labels? Run the search twice on the same positions with
different sampled worlds and count how often the two choices agree.

    .venv/bin/python -m tools.selfplay.label_noise --policy P.pt --value V.pt --games 10 --d 2 4

The networks run in this process (bf16, one request at a time). The probe seat plays the
network's greedy move after searching, so the positions are the network's own; the opponent is
the heuristic. Only main-phase asks where the network's top option is below --skip-p are probed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from typing import Any

import torch

from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import play_game
from tools.selfplay.search import Searcher


class LocalSlot:
    """Stands in for a worker slot: answers inference requests synchronously."""

    def __init__(self, nets: dict[str, torch.nn.Module]) -> None:
        self.nets = nets

    @torch.no_grad()
    def infer(self, req: tuple) -> Any:
        _gid, _seat, spec, _greedy, _record, feats = req[:6]
        want = req[6] if len(req) > 6 else 0
        b = M.collate([feats], "cuda")
        b = {k: (v.to(torch.bfloat16) if v.dtype == torch.float32 else v) for k, v in b.items()}
        logits, value = self.nets[spec](b)
        logits = logits.float()
        a = int(logits.argmax(-1)[0])
        if want == 0:
            return a
        if want == 1:
            return a, float(value.float()[0])
        k = feats["opts_i"].shape[0]
        probs = torch.softmax(logits, -1)[0, :k].tolist()
        return a, float(value.float()[0]), probs


class Probe:
    def __init__(self, slot: LocalSlot, table: FT.CardTable, ds: list[int], skip_p: float,
                 k: int, seed: int) -> None:
        self.slot = slot
        self.table = table
        self.ds = ds
        self.skip_p = skip_p
        self.k = k
        self.seed = seed
        self.rows: list[dict] = []
        self.name = "probe"

    def decide(self, ask: Any, obs: Any) -> int:
        n = len(ask.options)
        if n == 1:
            return 0
        if n > FT.MAX_OPTIONS or ask.kind == "name":
            return HeuristicAgent().decide(ask, obs)
        feats = FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx)
        a0, _, probs = self.slot.infer((0, ask.seat, "learner", True, False, feats, 2))
        if ask.kind == "act" and max(probs) < self.skip_p and obs.game is not None:
            row = {"n": n, "top_p": round(max(probs), 3)}
            for d in self.ds:
                picks = []
                for rep in (0, 1):
                    s = Searcher(self.slot, 0, "learner", self.table, k=self.k, d=d,
                                 skip_p=1.01, seed=self.seed * 1000 + len(self.rows) * 10 + rep,
                                 value="value")
                    picks.append(s.choose(ask, obs, feats))
                row[f"d{d}"] = picks
            row["net"] = int(a0)
            self.rows.append(row)
        return int(a0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", required=True)
    ap.add_argument("--value", required=True)
    ap.add_argument("--games", type=int, default=10)
    ap.add_argument("--d", type=int, nargs="+", default=[2, 4])
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--skip-p", type=float, default=0.95)
    ap.add_argument("--seed0", type=int, default=8_800_000)
    args = ap.parse_args(argv)
    pol, table, _ = M.load(args.policy, "cuda")
    val, _, _ = M.load(args.value, "cuda")
    slot = LocalSlot({"learner": pol.to(torch.bfloat16).eval(), "value": val.to(torch.bfloat16).eval()})
    rows: list[dict] = []
    for g in range(args.games):
        seat = g % 2
        probe = Probe(slot, table, args.d, args.skip_p, args.k, args.seed0 + g)
        agents: list[Any] = [None, None]
        agents[seat] = probe
        agents[1 - seat] = HeuristicAgent()
        play_game(args.seed0 + g, agents, deck_mode="stress" if g % 2 else "coherent")
        rows += probe.rows
    out: dict[str, Any] = {"decisions": len(rows), "k": args.k, "skip_p": args.skip_p}
    for d in args.d:
        same = sum(r[f"d{d}"][0] == r[f"d{d}"][1] for r in rows)
        changed = Counter(int(r[f"d{d}"][0] != r["net"]) + int(r[f"d{d}"][1] != r["net"])
                          for r in rows)
        out[f"d{d}"] = {"repeat_agreement": round(same / max(len(rows), 1), 3),
                        "changes_vs_net_per_run": round(
                            (changed[1] + 2 * changed[2]) / max(2 * len(rows), 1), 3)}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
