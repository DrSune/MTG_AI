"""The soak games (play_one: stress decks, verified pools) that trip I1 on one checkout copy, in
parallel.

    find_i1_par.py <root> <first seed> <last seed> [sets...]
"""
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = sys.argv[1]
for p in (ROOT, ROOT + "/tools/cards", ROOT + "/tools/audit"):
    sys.path.insert(0, p)


def run(job):
    import MTG_bot
    import soak

    assert MTG_bot.__file__.startswith(ROOT), MTG_bot.__file__
    code, seed = job
    r = soak.play_one((code, "verified", False, "stress", seed))
    return code, seed, r["crash"], [h["detail"] for h in r["hits"] if h["detector"] == "i1_tokens"]


if __name__ == "__main__":
    lo, hi = int(sys.argv[2]), int(sys.argv[3])
    sets = sys.argv[4:] or ["M21", "M20", "FDN"]
    jobs = [(c, s) for c in sets for s in range(lo, hi + 1)]
    with ProcessPoolExecutor(6) as pool:
        for code, seed, crash, i1 in pool.map(run, jobs, chunksize=4):
            if crash or i1:
                print(code, seed, (crash or {}).get("error", "")[:100], i1, flush=True)
    print("games", len(jobs))
