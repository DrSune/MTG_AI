#!/usr/bin/env python3
"""The blast radius of an engine change: one protocol for every wave (KNOWLEDGE/2026-11-18/215 §8
c, d, f), engine waves C1 and E3's scripts made one tool.

Two checkouts, the base and the branch (a worktree, or a commit exported with
``git archive <sha> | tar -x -C <dir>``), each played by its own Python process, since one process
imports one MTG_bot:

1. **trees**: per checkout, every card of the 19 sets with its compiler tree sha, its tree with card
   records applied and whether that tree is the verified one; then the diff (trees changed, cards
   leaving or joining the verified pool).
2. **replays**: N seeded heuristic games per verified pool (M21, M20, FDN) on each checkout, seeds
   930000 + i, coherent decks every third game and stress decks otherwise, dealt only from the
   cards verified with the same tree on both checkouts (so a change of stamps moves no deal), as
   ``tools/selfplay/rig.play_game`` plays them. Per game: the replay digest (``preflight._digest``:
   outcome, lives, asks), a sha of the journal dump and of the raw event log, the crash, and the
   CPU seconds it took.
3. **compare**: identical digests, journals and event logs per pool, crashes, the games that differ,
   and games per CPU-second of each side (215 §8 f: within 5% of the base).
4. **rows**: each differing game played again on both sides with its journal kept, and its first
   differing journal row printed with the rows around it (card names beside the handles).

    blast_radius.py run --base <dir> --branch <dir> --out <dir> [--games 200]
    blast_radius.py trees <checkout> <out.json>                       # one side's tree dump
    blast_radius.py replay <checkout> <base_trees> <branch_trees> <games> <out.json> [only.txt]
    blast_radius.py compare <base.json> <branch.json> [<list.txt>]
    blast_radius.py rows <base_rows.json> <branch_rows.json>

``run`` does all four and writes ``trees_*.json``, ``tree_diff.txt``, ``replay_*.json``,
``compare.txt`` and ``first_rows.txt`` into ``--out``. It reads tools/selfplay (rig, preflight,
heuristic) and never edits it. CPU only: run it niced, each side under a memory cap, as 215 §8 asks:

    CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 nice -n 19 .venv/bin/python tools/audit/blast_radius.py \\
        run --base /tmp/base --branch . --out reports/<wave>/blast --games 200
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

POOLS = ("M21", "M20", "FDN")
SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
SEED0 = 930000


def _checkout(root: str) -> Path:
    """Put ``root`` first on the path, so MTG_bot and tools are that checkout's, and prove it."""
    path = Path(root).resolve()
    sys.path.insert(0, str(path))
    import MTG_bot

    if not Path(MTG_bot.__file__).resolve().is_relative_to(path):
        raise SystemExit(f"imported MTG_bot from {MTG_bot.__file__}, not {path}")
    return path


# ------------------------------------------------------------------------------------- trees

def tree_dump(root: str, out: str) -> None:
    """Every card of the 19 sets: its compiler tree sha, its tree with records applied (verified or
    not) and whether that is the verified one; a refusal is recorded as its reason."""
    path = _checkout(root)
    from MTG_bot.core.compiler import card_records
    from MTG_bot.core.compiler.compiler import compile_pool
    from MTG_bot.core.compiler.coverage import build_full_registry
    from MTG_bot.core.compiler.ingest import ingest_pool
    from MTG_bot.core.errors import StateCorruptionError

    registry = build_full_registry()

    def compiled(oid, rc, records=None):
        try:
            return compile_pool({oid: rc}, registry, records=records, require_verified=False).results[oid]
        except (StateCorruptionError, ValueError) as exc:
            return f"refused: {type(exc).__name__}: {str(exc)[:160]}"

    dump: dict = {}
    for code in SETS:
        raw = ingest_pool(path / "MTG_bot" / "data" / f"{code}.json")
        records = card_records.load_records(code)
        rows = {}
        for oid, rc in raw.items():
            if rc.is_token or rc.is_emblem:
                continue
            comp, rec = compiled(oid, rc), compiled(oid, rc, records)
            row = {"name": rc.identity.name,
                   "compiler": comp if isinstance(comp, str) else card_records.tree_sha(comp.card)}
            if isinstance(rec, str):
                row["tree"] = rec
            else:
                row.update(tree=card_records.tree_sha(rec.card), record=rec.record is not None,
                           verified=card_records.is_verified(rec, records.get(oid)))
            rows[oid] = row
        dump[code] = rows
        print(code, len(rows), file=sys.stderr)
    Path(out).write_text(json.dumps(dump, indent=0, sort_keys=True))


def tree_diff(base_json: str, branch_json: str) -> str:
    base, new = json.loads(Path(base_json).read_text()), json.loads(Path(branch_json).read_text())
    changed_compiler, changed_tree, leaving, joining = [], [], [], []
    for code in base:
        for oid, b in base[code].items():
            n = new[code].get(oid, {})
            if b["compiler"] != n.get("compiler"):
                changed_compiler.append(f"{code} {b['name']}")
            if b["tree"] != n.get("tree"):
                changed_tree.append(f"{code} {b['name']} ({'verified' if b.get('verified') else 'unverified'})")
            if b.get("verified") and not n.get("verified"):
                leaving.append(f"{code} {b['name']}")
            if n.get("verified") and not b.get("verified"):
                joining.append(f"{code} {b['name']}")
    lines = [f"compiler trees changed ({len(changed_compiler)}): {sorted(changed_compiler)}",
             f"trees with records applied changed ({len(changed_tree)}): {sorted(changed_tree)}",
             f"verified cards leaving the verified pool ({len(leaving)}): {sorted(leaving)}",
             f"verified cards joining ({len(joining)}): {sorted(joining)}"]
    totals = {code: (sum(1 for r in base[code].values() if r.get("verified")),
                     sum(1 for r in new[code].values() if r.get("verified"))) for code in base}
    lines.append("verified stamps per set (base -> branch): "
                 + str({k: f"{a}->{b}" for k, (a, b) in totals.items() if a or b}))
    return "\n".join(lines)


# ----------------------------------------------------------------------------------- replays

def replay(root: str, base_trees: str, branch_trees: str, n: int, out: str, only: str | None = None) -> None:
    """N seeded heuristic games per verified pool on one checkout (module docstring, step 2). Given
    ``only`` (SET:i lines), it plays only those games and keeps their journal rows and card names."""
    _checkout(root)
    from MTG_bot.core.executor import games
    from tools.selfplay import preflight, rig
    from tools.selfplay.heuristic import HeuristicAgent

    captured: dict = {}
    setup = rig._setup_game

    def capture(*args, **kwargs):  # the game object play_game builds, to read its journal
        captured["game"] = game = setup(*args, **kwargs)
        return game

    rig._setup_game = capture
    base, new = json.loads(Path(base_trees).read_text()), json.loads(Path(branch_trees).read_text())
    keep = set(Path(only).read_text().split()) if only else None
    result = {}
    for code in POOLS:
        # a card whose stamp or tree differs between the checkouts is dealt on neither side
        stale = {oid for oid, row in base[code].items()
                 if row.get("verified") != new[code].get(oid, {}).get("verified")
                 or row["tree"] != new[code].get(oid, {}).get("tree")}
        supply = games.get_supply("verified", code)
        kept = tuple(oid for oid in supply.deckable if oid not in stale)
        games._SUPPLY_CACHE[f"verified:{code}"] = dataclasses.replace(supply, deckable=kept)
        played = []
        for i in range(n):
            if keep is not None and f"{code}:{i}" not in keep:
                continue
            t0 = time.process_time()
            res = rig.play_game(SEED0 + i, [HeuristicAgent(), HeuristicAgent()],
                                deck_mode="stress" if i % 3 else "coherent", pool_mode="verified", set_code=code)
            cpu = time.process_time() - t0
            ex = captured["game"].executor
            dump = ex.journal.dump()
            row = {"game": i, "digest": preflight._digest(res)[:16],
                   "journal": hashlib.sha256(repr(dump).encode()).hexdigest()[:16],
                   "events": hashlib.sha256(repr(ex.events).encode()).hexdigest()[:16],
                   "outcome": res["outcome"], "turns": res["turns"], "crash": res["crash"], "cpu": round(cpu, 4)}
            if keep is not None:
                names = {str(h): c.identity.name for h, c in ex.world.cards.items()}
                for h, lki in ex.departed_lki.items():
                    if getattr(lki, "identity", None) is not None:
                        names.setdefault(str(h), lki.identity.name)
                row.update(rows=[repr(r) for r in dump], names=names)
            played.append(row)
        result[code] = {"deckable": len(kept), "taken_out": sorted(stale & set(supply.deckable)), "games": played}
        print(code, len(kept), "deckable;", sum(1 for r in played if r["crash"]), "crashes", file=sys.stderr)
    Path(out).write_text(json.dumps(result))


def compare(base_json: str, branch_json: str, listing: str | None = None) -> str:
    """Per pool: identical digests, journals and event logs, crashes, games per CPU-second; then the
    differing games (written as SET:i lines to ``listing``)."""
    base, new = json.loads(Path(base_json).read_text()), json.loads(Path(branch_json).read_text())
    lines, differing = [], []
    cpu = {"base": 0.0, "branch": 0.0}
    count = 0
    for code in base:
        b, n = base[code]["games"], new[code]["games"]
        pairs = list(zip(b, n, strict=True))
        same = {k: sum(x[k] == y[k] for x, y in pairs) for k in ("digest", "journal", "events")}
        crashes = (sum(1 for g in b if g["crash"]), sum(1 for g in n if g["crash"]))
        cpu["base"] += sum(g["cpu"] for g in b)
        cpu["branch"] += sum(g["cpu"] for g in n)
        count += len(pairs)
        lines.append(f"{code}: deckable {base[code]['deckable']} / {new[code]['deckable']}; taken out "
                     f"{len(base[code]['taken_out'])}; games {len(pairs)}; identical digests {same['digest']}, "
                     f"journals {same['journal']}, event logs {same['events']}; crashes {crashes[0]} / {crashes[1]}")
        for x, y in pairs:
            if any(x[k] != y[k] for k in ("digest", "journal", "events")):
                differing.append(f"{code}:{x['game']}")
                lines.append(f"  {code}:{x['game']}: digest {x['digest'] == y['digest']}, journal "
                             f"{x['journal'] == y['journal']}, events {x['events'] == y['events']}; outcome "
                             f"{x['outcome']} -> {y['outcome']}; crash {x['crash']} -> {y['crash']}")
    rate = {k: count / v if v else float("nan") for k, v in cpu.items()}
    lines.append(f"games that differ: {len(differing)} of {count}")
    lines.append(f"games per CPU-second: base {rate['base']:.2f}, branch {rate['branch']:.2f} "
                 f"({100 * (rate['branch'] / rate['base'] - 1):+.1f}%; 215 §8 f asks within 5%)")
    if listing:
        Path(listing).write_text("".join(f"{d}\n" for d in differing))
    return "\n".join(lines)


def _label(row: str, names: dict) -> str:
    return re.sub(r"card:(\d+)", lambda m: f"card:{m.group(1)}[{names.get('card:' + m.group(1), '?')}]", row)


def first_rows(base_json: str, branch_json: str) -> str:
    """Each differing game's first differing journal row on both sides, with the rows around it."""
    base, new = json.loads(Path(base_json).read_text()), json.loads(Path(branch_json).read_text())
    lines = []
    for code in base:
        for b, n in zip(base[code]["games"], new[code]["games"], strict=True):
            names = {**b["names"], **n["names"]}
            br, nr = b["rows"], n["rows"]
            first = next((k for k, (x, y) in enumerate(zip(br, nr)) if x != y), min(len(br), len(nr)))
            lines.append(f"{code}:{b['game']}: first differing row {first} of {len(br)} (base) / {len(nr)} "
                         f"(branch); outcome {b['outcome']} -> {n['outcome']}, turns {b['turns']} -> {n['turns']}")
            lines += [f"   same:   {_label(br[k], names)}" for k in range(max(0, first - 3), first)]
            lines += [f"   base:   {_label(br[k], names)}" for k in range(first, min(first + 3, len(br)))]
            lines += [f"   branch: {_label(nr[k], names)}" for k in range(first, min(first + 3, len(nr)))]
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------- run

def _side(*args: str) -> subprocess.Popen:
    """This tool, as a subprocess (each checkout in its own interpreter, two at a time)."""
    return subprocess.Popen([sys.executable, str(Path(__file__).resolve()), *args])


def run(base: str, branch: str, out: str, n: int) -> None:
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    trees = {side: str(o / f"trees_{side}.json") for side in ("base", "branch")}
    for proc in [_side("trees", base, trees["base"]), _side("trees", branch, trees["branch"])]:
        if proc.wait():
            raise SystemExit("a tree dump failed")
    (o / "tree_diff.txt").write_text(tree_diff(trees["base"], trees["branch"]) + "\n")
    replays = {side: str(o / f"replay_{side}.json") for side in ("base", "branch")}
    for proc in [_side("replay", base, trees["base"], trees["branch"], str(n), replays["base"]),
                 _side("replay", branch, trees["base"], trees["branch"], str(n), replays["branch"])]:
        if proc.wait():
            raise SystemExit("a replay failed")
    listing = o / "differing.txt"
    (o / "compare.txt").write_text(compare(replays["base"], replays["branch"], str(listing)) + "\n")
    if listing.read_text().strip():
        rows = {side: str(o / f"rows_{side}.json") for side in ("base", "branch")}
        for proc in [_side("replay", base, trees["base"], trees["branch"], str(n), rows["base"], str(listing)),
                     _side("replay", branch, trees["base"], trees["branch"], str(n), rows["branch"], str(listing))]:
            if proc.wait():
                raise SystemExit("a replay of the differing games failed")
        (o / "first_rows.txt").write_text(first_rows(rows["base"], rows["branch"]) + "\n")
    print((o / "tree_diff.txt").read_text() + (o / "compare.txt").read_text(), end="")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--base", required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--games", type=int, default=200, help="games per verified pool (215 §8 d: 200)")
    p = sub.add_parser("trees")
    p.add_argument("checkout")
    p.add_argument("out")
    p = sub.add_parser("replay")
    for name in ("checkout", "base_trees", "branch_trees"):
        p.add_argument(name)
    p.add_argument("games", type=int)
    p.add_argument("out")
    p.add_argument("only", nargs="?")
    p = sub.add_parser("compare")
    p.add_argument("base")
    p.add_argument("branch")
    p.add_argument("listing", nargs="?")
    p = sub.add_parser("rows")
    p.add_argument("base")
    p.add_argument("branch")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        run(args.base, args.branch, args.out, args.games)
    elif args.cmd == "trees":
        tree_dump(args.checkout, args.out)
    elif args.cmd == "replay":
        replay(args.checkout, args.base_trees, args.branch_trees, args.games, args.out, args.only)
    elif args.cmd == "compare":
        print(compare(args.base, args.branch, args.listing))
    else:
        print(first_rows(args.base, args.branch))
    return 0


if __name__ == "__main__":
    sys.exit(main())
