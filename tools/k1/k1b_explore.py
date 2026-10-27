"""K1b exploratory read (NOT pre-registered): where does the volume gain come from?

    MTG_REPO=<tree> .venv/bin/python tools/k1/k1b_explore.py --data DIR --run A|B

Reads the per-card errors that tools/k1/curve.py saved (``k1b_curve_<run>.cards.json``) and splits
the held-out effect cards in two:
- **covered**: every atom of the card already occurs on some 1-set training card. A gain here is
  a better encoding of atoms the model had already seen, the owner's "nuance" question.
- **new atoms**: the card has an atom no 1-set training card has. A gain here can come from simply
  seeing the atom at all.

It also names the test cards that dominate the pooled R² at 1 set: their share of the state floor's
summed squared error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import curve as C
import train as T


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--run", required=True, choices=("A", "B"))
    ap.add_argument("--cap", type=int, default=60)
    args = ap.parse_args(argv)
    data = Path(args.data)
    side = json.loads((data / f"k1b_curve_{args.run}.cards.json").read_text(encoding="utf-8"))
    mse, raw = side["mse"], side["raw"]
    inputs: dict = {}
    for code in (*C.ALL_TRAIN, "M20", "KHM"):
        for key, value in T.card_inputs(code).items():
            inputs.setdefault(key, value)
    first, last = C.STEPS[0][0], C.STEPS[-1][0]
    rows = {code: C.capped(T.load(data, code), args.cap) for code in C.ALL_TRAIN}
    held = set(side["population"]["heldout/all"])
    first_train = {r["oid"] for code in C.STEPS[0][1] for r in rows[code] if r["oid"] not in held}
    seen_atoms = set().union(*(T.atoms_of_tokens(inputs[(oid, "card")]["ir"])
                               for oid in first_train if (oid, "card") in inputs))
    effect = set(side["population"]["heldout/effect"])
    groups = {
        "covered": {c for c in effect if T.atoms_of_tokens(inputs[(c, "card")]["ir"]) <= seen_atoms},
        "new atoms": {c for c in effect
                      if not T.atoms_of_tokens(inputs[(c, "card")]["ir"]) <= seen_atoms},
    }
    m21 = {r["oid"] for r in rows["M21"]}
    groups["from M21"] = effect & m21
    out: dict = {"run": args.run, "groups": {}}
    for name, cards in groups.items():
        cell: dict[str, Any] = {"cards": len(cards)}
        for encoder in ("ir-bag", "ir-pairs", "text-bag", "hybrid"):
            a = C.skills(mse[last][encoder]["heldout"], mse[last]["state"]["heldout"], cards)
            b = C.skills(mse[first][encoder]["heldout"], mse[first]["state"]["heldout"], cards)
            cell[encoder] = {first: C.summary(b).get("median_skill"),
                             last: C.summary(a).get("median_skill"),
                             "gap": C.paired_gap(a, b, f"explore:{args.run}:{name}:{encoder}")}
        out["groups"][name] = cell
    # who dominates the pooled R² at 1 set: share of the floor's summed squared error, board units
    counts: dict[str, int] = {}
    for code in C.ALL_TRAIN:
        for r in rows[code]:
            if r["oid"] in held:
                counts[r["oid"]] = counts.get(r["oid"], 0) + 1
    floor = raw[first]["state"]["heldout"]
    total = sum(floor[c] * counts[c] for c in floor)
    top = sorted(floor, key=lambda c: -floor[c] * counts[c])[:5]
    names = {}
    for code in C.ALL_TRAIN:
        for oid, raw_card in T.ingest_pool(T.REPO / "MTG_bot" / "data" / f"{code}.json").items():
            names.setdefault(oid, raw_card.identity.name)
    out["pooled_r2_dominated_by"] = [
        {"card": names.get(c, c), "rows": counts[c],
         "share_of_floor_sse": round(floor[c] * counts[c] / total, 3)} for c in top]
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
