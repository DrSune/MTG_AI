"""One side of N1/N2's check on r28's v2 (KNOWLEDGE/2026-11-17/210 §8): what one code tree
computes with the checkpoint, read only, on the CPU in fp32.

    CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 nice -n 19 .venv/bin/python \
        reports/n1n2_2026-11-17/v2_side.py --code-root TREE --out SIDE.pkl

TREE holds the ``tools/`` package to run: the base commit's (``git archive 32e804ec tools``,
unpacked) for the old side, the repository root for the new one; ``MTG_bot`` (unchanged) is this
repository's. Two tables, each as the learner builds it from ``--init``:
- ``saved``: v2's own rows, as saved (cut at 128 tokens, names in);
- ``refreshed``: r28's and r29's flags (``--refresh-table --extend-sets M20 --mix-sets M20``):
  rows rebuilt from the current compile of M21 and M20, then M20's new cards added.
For each: every row's component vector (``card_table_emb``); v2's logits and value on the real
decisions of seeded heuristic games (encoded with that table); and seeded games that v2 plays
greedily (both seats, or against the heuristic), every decision of its seats recorded.
"""
from __future__ import annotations

import argparse
import pickle
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CKPT = "/home/sune/Desktop/MTG_AI/runs/r28_looks/r28_v2.pt"
#: (seed, set) of the heuristic games whose decisions are scored, and of the games v2 plays
RECORDED = [(900001, "M21"), (900002, "M21"), (900003, "M21"), (900004, "M21"),
            (900001, "M20"), (900002, "M20")]
PLAYED = [(900011, "M21", "self"), (900012, "M21", "heuristic"), (900013, "M21", "self"),
          (900014, "M21", "heuristic"), (900011, "M20", "self"), (900012, "M20", "heuristic")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code-root", required=True)
    ap.add_argument("--ckpt", default=CKPT)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    root = str(Path(a.code_root).resolve())
    sys.path[:0] = [root, str(REPO)]
    import numpy as np
    import torch

    from tools.selfplay import features as FT
    from tools.selfplay import model as M
    from tools.selfplay.actor import RecordingHeuristic
    from tools.selfplay.heuristic import HeuristicAgent
    from tools.selfplay.learner import table_records
    from tools.selfplay.rig import play_game

    assert FT.__file__.startswith(root), FT.__file__
    torch.set_num_threads(2)

    class Greedy:
        """v2 on one seat as actor.NetAgent plays it with a greedy slot (model.LocalSlot)."""

        name = "net"

        def __init__(self, net: torch.nn.Module, table: FT.CardTable, log: list) -> None:
            self.net, self.table, self.log = net, table, log
            self.fallback = HeuristicAgent()

        def decide(self, ask, obs) -> int:
            n = len(ask.options)
            if n == 1:
                return 0
            if n > FT.MAX_OPTIONS or ask.kind == "name":
                return self.fallback.decide(ask, obs)
            feats = FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx)
            with torch.no_grad():
                logits, value = self.net(M.collate([feats], "cpu"))
            k = feats["opts_i"].shape[0]
            choice = int(torch.softmax(logits[0, :k].float(), -1).argmax())
            self.log.append({"seat": ask.seat, "kind": ask.kind, "turn": obs.executor.world.turn,
                             "feats": feats, "logits": logits[0, :k].numpy().copy(),
                             "value": float(value[0]), "choice": choice})
            return choice

    out: dict = {"code_root": root}
    for config in ("saved", "refreshed"):
        t0 = time.time()
        net, table, _ = M.load(a.ckpt, "cpu")
        if config == "refreshed":  # learner.Learner.__init__ with r28's and r29's table flags
            table, ref = table.refresh(table_records(["M21", "M20"]))
            M.extend_cards(net, table)
            table, ext = table.extend(table_records(["M20"]), add_tokens=True)
            M.extend_cards(net, table)
            out[f"{config}_log"] = {"refresh": ref, "extend": {k: v for k, v in ext.items()}}
        net.eval()
        with torch.no_grad():
            emb = net.card_table_emb()
        side = {"oracle_ids": list(table.oracle_ids), "names": list(table.names),
                "ir_vocab": list(table.ir_vocab), "ir": [list(r) for r in table.ir],
                "card_vec": emb.numpy().copy(),
                "ir_emb": net.ir_emb.weight.detach().numpy().copy()}
        net.card_table_emb = lambda emb=emb: emb  # a constant at play time (linevalue.main)
        # 1. real decisions of heuristic games, scored by v2 in batches
        feats_all, where = [], []
        for seed, code in RECORDED:
            seats = [RecordingHeuristic(0, table), RecordingHeuristic(1, table)]
            play_game(seed, seats, deck_mode="coherent", pool_mode="verified", set_code=code)
            for s in seats:
                for f, _ in s.samples:
                    feats_all.append(f)
                    where.append((seed, code, s.seat))
        logits, values = [], []
        with torch.no_grad():
            for i in range(0, len(feats_all), 64):
                chunk = feats_all[i:i + 64]
                lg, v = net(M.collate(chunk, "cpu"))
                for j, f in enumerate(chunk):
                    logits.append(lg[j, :f["opts_i"].shape[0]].numpy().copy())
                values.append(v.numpy().copy())
        side["recorded"] = {"feats": feats_all, "where": where, "logits": logits,
                            "values": np.concatenate(values)}
        # 2. games v2 plays greedily
        games = []
        for seed, code, opp in PLAYED:
            log: list = []
            agents = [Greedy(net, table, log),
                      Greedy(net, table, log) if opp == "self" else HeuristicAgent()]
            res = play_game(seed, agents, deck_mode="coherent", pool_mode="verified", set_code=code)
            games.append({"seed": seed, "set": code, "opp": opp, "decisions": log,
                          "result": {k: res[k] for k in ("outcome", "winner", "turns", "lives",
                                                         "crash")}})
        side["played"] = games
        out[config] = side
        print(f"{config}: {len(table.oracle_ids)} rows, {len(table.ir_vocab)} tokens; "
              f"{len(feats_all)} recorded decisions; {sum(len(g['decisions']) for g in games)} "
              f"played decisions in {len(games)} games; {time.time() - t0:.0f}s", flush=True)
    Path(a.out).write_bytes(pickle.dumps(out))


if __name__ == "__main__":
    main()
