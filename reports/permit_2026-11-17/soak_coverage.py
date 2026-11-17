"""The soak (G5: tools/cards/soak.py, its own games: play_one, summarize) of the pools that deal the
round's new and changed trees, with what the round's lanes did in them. Per run: the soak's
summary (crashes, detector hits, the abuse screen: win-rate outliers, repeatable activations,
trigger loops), and for the round's cards the games each was cast in, the permissions resolved
(PERMIT, by source), the casts and land plays made through a permission (by card), and the spells
a rider moved. Run from the repo root:

    .venv/bin/python reports/permit_2026-11-17/soak_coverage.py [--workers N] [--scale F]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "tools" / "cards", REPO / "tools" / "audit"):
    sys.path.insert(0, str(p))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(REPO)), MTG_bot.__file__
import soak  # noqa: E402

from MTG_bot.core.executor import permits, stack, verbs  # noqa: E402

#: The round's cards: the changed trees of the 19 sets (tree_diff.txt) and the two M20 records.
FAMILY = {
    "Chandra, Flame's Catalyst", "Chandra, Heart of Fire", "Conspicuous Snoop", "Demonic Embrace",
    "Idol of Endurance", "Radha, Heart of Keld", "Golos, Tireless Pilgrim", "Mystic Forge",
    "Bulk Up", "Electroduplicate", "Inspiration from Beyond", "Mystical Teachings", "Omniscience",
    "Revenge of the Rats", "Self-Reflection", "Sphinx of Forgotten Lore", "Think Twice",
    "Vizier of the Menagerie", "Zul Ashur, Lich Lord", "Ancient Greenwarden", "Coveted Prize",
    "Valakut Exploration", "Crucible of Worlds", "Liliana, Untouched by Death", "Squee, the Immortal",
    "Precognition Field", "Garruk's Horde", "Jace, Vryn's Prodigy // Jace, Telepath Unbound",
    "Vivien, Monsters' Advocate", "Bolas's Citadel", "Dreadhorde Arcanist",
}
#: (set, supply mode, unverified records applied, games).
RUNS = (("M21", "castable", False, 300), ("FDN", "castable", False, 200),
        ("M20", "castable", True, 200), ("ZNR", "castable", False, 100),
        ("M19", "castable", False, 100), ("DOM", "castable", False, 100),
        ("M12", "castable", False, 100))

lanes: dict[str, Counter] = {"permits": Counter(), "path_casts": Counter(), "path_lands": Counter(),
                             "riders": Counter()}


def _name(executor, handle) -> str:
    card = executor.world.cards.get(handle)
    return card.identity.name if card is not None else str(handle)


_cast, _use, _exit, _permit = stack.cast, permits.use, stack.exit_zone, verbs._v_permit


def counting_cast(executor, seat, handle, **kw):
    if kw.get("path") is not None:
        lanes["path_casts"][_name(executor, handle)] += 1
    return _cast(executor, seat, handle, **kw)


def counting_use(path):
    if path.lands:
        lanes["path_lands"][str(path.card)] += 1  # names filled in by the caller's game
    return _use(path)


def counting_exit(frame, dest):
    out = _exit(frame, dest)
    if out != dest:
        lanes["riders"][str(frame.handle)] += 1
    return out


def counting_permit(ctx, atom):
    lanes["permits"][_name(ctx.executor, ctx.source)] += 1
    return _permit(ctx, atom)


stack.cast = counting_cast
permits.use = counting_use
stack.exit_zone = verbs.exit_zone = counting_exit
verbs._v_permit = counting_permit
verbs.HANDLERS[verbs.Verb.PERMIT] = counting_permit
import MTG_bot.core.executor.menu as menu_mod  # noqa: E402

menu_mod.cast = counting_cast


def job(args):
    for c in lanes.values():
        c.clear()
    row = soak.play_one(args)
    return row, {k: dict(v) for k, v in lanes.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--out", default=str(REPO / "reports" / "permit_2026-11-17" / "soak_coverage.json"))
    a = ap.parse_args()
    report = []
    for code, mode, unverified, games in RUNS:
        n = max(1, int(games * a.scale))
        jobs = [(code, mode, unverified, "stress", s) for s in range(1, n + 1)]
        with ProcessPoolExecutor(max_workers=a.workers) as pool:
            out = list(pool.map(job, jobs, chunksize=4))
        rows = [r for r, _ in out]
        sup = soak._supply(code, mode, unverified)
        summary = soak.summarize(rows, sup)
        names = {oid: sup.metas[oid].name for oid in sup.deckable if sup.metas[oid].name in FAMILY}
        cast_in = Counter(names[oid] for r in rows for oid in r["casts"] if oid in names)
        totals = {k: Counter() for k in lanes}
        for _r, counts in out:
            for k, v in counts.items():
                totals[k].update(v)
        entry = {"set": code, "mode": mode, "unverified_records": unverified, "games": n,
                 "crashed": summary["crashed"], "crashes": summary["crashes"],
                 "detector_hits": summary["detector_hits"], "outliers": summary["outliers"],
                 "repeatable_activations": summary["repeatable_activations"],
                 "trigger_loops": summary["trigger_loops"], "dealt": sorted(names.values()),
                 "games_cast_in": dict(cast_in.most_common()),
                 "permits_resolved": dict(totals["permits"].most_common()),
                 "casts_through_a_permission": dict(totals["path_casts"].most_common()),
                 "land_plays_through_a_permission": sum(totals["path_lands"].values()),
                 "rider_moves": sum(totals["riders"].values())}
        report.append(entry)
        print(json.dumps({k: v for k, v in entry.items() if k != "dealt"}), flush=True)
    Path(a.out).write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    main()
