"""Blind G2 packets for the card backlog's first verification wave (PLAN_CARD_ONBOARDING,
docs/MAPPER_GUIDE.md "Verifier workflow").

    PYTHONPATH=. .venv/bin/python reports/verify_wave1_2026-11-12/packets.py OUT KEYS SEED [BATCHES.json]

BATCHES.json ({batch: {set: [card, ...]}}, plants drawn from the first set of each batch)
replaces wave 1's list below, for a later wave.

Writes one packet per card under review, and per batch two planted packets: G3 mutants of cards that
are already verified and appear nowhere else in the batch (so a plant cannot be found by diffing
two packets of one card). Packet ids are shuffled per batch. KEYS gets the answer key (the real
cards and the plants); it is the orchestrator's and never the verifier's.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from MTG_bot.core.executor.games import get_supply

out, keys, seed = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
BATCHES = {
    "A": {"M21": ["Runed Halo", "Garruk, Savage Herald", "Rookie Mistake", "Drowsing Tyrannodon",
                  "Teferi, Timeless Voyager", "Transmogrify", "Hooded Blightfang",
                  "Basri, Devoted Paladin", "Feline Sovereign", "Mangara, the Diplomat", "Basri Ket",
                  "Tide Skimmer", "Archfiend's Vessel", "See the Truth", "Teferi's Ageless Insight",
                  "Tolarian Kraken", "Unsubstantiate"],
          "FDN": ["Ancestor Dragon"]},
    "B": {"M20": ["Anticipate", "Battalion Foot Soldier", "Blightbeetle", "Cavalier of Flame",
                  "Cavalier of Gales", "Goblin Ringleader", "Gods Willing", "Mu Yanling, Sky Dancer",
                  "Sanitarium Skeleton", "Sorin, Imperious Bloodlord", "Tale's End"]},
}
PLANT_SET = {"A": "M21", "B": "M20"}
if len(sys.argv) > 4:  # a later wave's batches; each batch's plants come from its first set
    BATCHES = json.loads(Path(sys.argv[4]).read_text())
    PLANT_SET = {b: next(iter(sets)) for b, sets in BATCHES.items()}
TOOL = [sys.executable, "tools/cards/cardtool.py"]
rng = np.random.default_rng(seed)
key: dict = {}
for batch, sets in BATCHES.items():
    real = [(s, c) for s, cards in sets.items() for c in cards]
    named = {c for _, c in real}
    sup = get_supply("verified", PLANT_SET[batch])
    decoys = [sup.metas[c].name for c in sup.deckable if not sup.metas[c].is_land]
    decoys = [d for d in sorted(set(decoys)) if d not in named]
    plants = []  # the first two decoys that have an observable critical mutant to plant
    for d in rng.permutation(decoys)[:40]:
        trial = subprocess.run([*TOOL, "packet", PLANT_SET[batch], str(d), "--out", str(keys / "trial"),
                                "--id", "trial", "--plant", str(seed + 1 + len(plants)),
                                "--key", str(keys / "trial")], capture_output=True, text=True, check=False)
        if trial.returncode == 0:
            plants.append(str(d))
        if len(plants) == 2:
            break
    items = [(s, c, None) for s, c in real] + [(PLANT_SET[batch], d, 1 + i) for i, d in enumerate(plants)]
    ids = [f"{batch}{i:02d}" for i in rng.permutation(len(items))]
    d_out = out / batch
    planted_ok = 0
    for (s, c, plant), pid in zip(items, ids, strict=True):
        cmd = [*TOOL, "packet", s, c, "--out", str(d_out), "--id", pid]
        if plant is not None:
            cmd += ["--plant", str(seed + plant), "--key", str(keys / "plants")]
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        ok = r.returncode == 0
        planted_ok += ok and plant is not None
        key[pid] = {"set": s, "card": c, "planted": plant is not None, "made": ok,
                    "note": (r.stdout + r.stderr).strip().splitlines()[-1:] if not ok else []}
        print(pid, s, c, "PLANTED" if plant is not None else "", "" if ok else f"FAILED: {r.stdout}{r.stderr}"[:200], flush=True)
    print(f"batch {batch}: {len(real)} cards, {planted_ok} plants made")
keys.mkdir(parents=True, exist_ok=True)
(keys / "key.json").write_text(json.dumps(key, indent=1) + "\n")
