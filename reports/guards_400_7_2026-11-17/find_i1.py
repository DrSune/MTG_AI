"""The seeds whose soak game (tools/cards/soak.py play_one, stress decks, verified pool) trips I1.

    find_i1.py <checkout> <set> <first seed> <last seed>
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "cards"))
sys.path.insert(0, str(ROOT / "tools" / "audit"))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
import soak  # noqa: E402

code, lo, hi = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
for seed in range(lo, hi + 1):
    r = soak.play_one((code, "verified", False, "stress", seed))
    i1 = [h["detail"] for h in r["hits"] if h["detector"] == "i1_tokens"]
    if i1 or r["crash"]:
        print(code, seed, i1, r["crash"], flush=True)
