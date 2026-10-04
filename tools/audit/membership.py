"""BUGCATCH B4a-instrument calibration: disk-truth card membership (§F PC-11).

Why this exists.  ``bcs.json`` carried ``in_pack`` / ``in_suspect`` copied from
a catalog row whose derivation is not reproducible from this repo, and
``tools/audit/suspects/`` is EMPTY (B3a adjudicated its three suspects and
``secure_the_scene.json`` was promoted to green) while 22 cards still claimed
``in_suspect``.  A campaign gate keyed on a stale flag is not a gate — it is a
report of what somebody once believed.

Derivation law (2026-10-04 ruling):

* A card is a member of a pack iff its **PRINTED NAME** appears as a ``"real"``
  value inside that pack file.  ``"real"`` is the slot
  :class:`run_scenarios.ScenarioRunner` resolves into a real card; synthetic
  cards spell themselves ``"name"`` and are NOT real-card evidence.
* NEVER a handle substring.  Packs talk about cards by printed name, so a
  handle search finds almost nothing and understates coverage badly (measured
  on 2026-10-04: it wrongly marked ``secure_the_scene`` uncovered while its own
  pack file sat on disk).  Handles are for journal rows, names are for packs.
* NEVER ``bcs.json``'s own flags — those are the thing being audited.

Every number this tool prints is recomputed from files on disk.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BCS_JSON = HERE / "bcs.json"
PACKS_DIR = REPO / "tools" / "scenarios"
SUSPECTS_DIR = HERE / "suspects"
T_DEFAULT = 20  # §F "BCS >= T", fixed by the 2026-10-04 ruling


def _real_names(node: object) -> set[str]:
    """Every ``"real"`` value in a pack tree (cards[], steps, anywhere)."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "real" and isinstance(value, str) and value.strip():
                found.add(value.strip())
            else:
                found |= _real_names(value)
    elif isinstance(node, list):
        for item in node:
            found |= _real_names(item)
    return found


def disk_membership(
    packs_dir: Path = PACKS_DIR, suspects_dir: Path = SUSPECTS_DIR
) -> dict[str, dict[str, list[str]]]:
    """printed name -> {"packs": [filenames], "suspects": [filenames]}."""
    out: dict[str, dict[str, list[str]]] = {}

    def lane(d: Path, key: str) -> None:
        if not d.is_dir():
            return
        for path in sorted(d.glob("*.json")):
            try:
                tree = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                print(f"membership: SKIP {path.name}: {e}", file=sys.stderr)
                continue
            for name in _real_names(tree):
                rec = out.setdefault(name, {"packs": [], "suspects": []})
                if path.name not in rec[key]:
                    rec[key].append(path.name)

    lane(packs_dir, "packs")
    lane(suspects_dir, "suspects")
    return out


def refresh(
    bcs: dict[str, Any], member: dict[str, dict[str, list[str]]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Rewrite per-card membership from disk; return (bcs, membership block).

    The prior flag values are preserved inside the block so the correction is
    auditable rather than silent.
    """
    was = {"in_pack": [], "in_suspect": []}
    now = {"in_pack": [], "in_suspect": []}
    changed: dict[str, dict[str, list[bool]]] = {}

    for name, card in bcs["cards"].items():
        rec = member.get(name, {"packs": [], "suspects": []})
        new_pack = bool(rec["packs"])
        new_susp = bool(rec["suspects"])
        if card.get("in_pack"):
            was["in_pack"].append(name)
        if card.get("in_suspect"):
            was["in_suspect"].append(name)
        if (
            bool(card.get("in_pack")) != new_pack
            or bool(card.get("in_suspect")) != new_susp
        ):
            changed[name] = {
                "was": [bool(card.get("in_pack")), bool(card.get("in_suspect"))],
                "now": [new_pack, new_susp],
            }
        card["in_pack"] = new_pack
        card["in_suspect"] = new_susp
        if new_pack:
            now["in_pack"].append(name)
        if new_susp:
            now["in_suspect"].append(name)

    block = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "command": ".venv/bin/python tools/audit/membership.py --write",
        "law": 'a card is covered iff its PRINTED NAME appears as a "real" '
        "value in a pack file; never a handle substring, never bcs.json's own "
        "flags",
        "sources": {
            "packs_dir": str(PACKS_DIR.relative_to(REPO)),
            "pack_files": len(list(PACKS_DIR.glob("*.json"))),
            "suspects_dir": str(SUSPECTS_DIR.relative_to(REPO)),
            "suspect_files": len(list(SUSPECTS_DIR.glob("*.json")))
            if SUSPECTS_DIR.is_dir()
            else 0,
        },
        "supersedes": "in_pack/in_suspect copied from an unreproducible "
        "catalog row in B1 (tools/audit/bcs.py main)",
        "before": {k: len(v) for k, v in was.items()},
        "after": {k: len(v) for k, v in now.items()},
        "changed": changed,
        "changed_count": len(changed),
    }
    return bcs, block


def pc11(bcs: dict[str, Any], t: int) -> dict[str, Any]:
    """§F PC-11: every card with BCS >= T is in_pack or in_suspect."""
    hi = [(n, c) for n, c in bcs["cards"].items() if int(c.get("bcs", 0)) >= t]
    residue = sorted(n for n, c in hi if not (c.get("in_pack") or c.get("in_suspect")))
    return {
        "t": t,
        "cards_at_or_above_t": len(hi),
        "covered": len(hi) - len(residue),
        "residue": len(residue),
        "residue_handles": [bcs["cards"][n].get("handle", n) for n in residue],
        "residue_names": residue,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BUGCATCH disk-truth membership (PC-11)")
    ap.add_argument("--t", type=int, default=T_DEFAULT, help="PC-11 BCS floor")
    ap.add_argument("--write", action="store_true", help="patch bcs.json in place")
    ap.add_argument("--list", type=int, default=12, help="residue names to print")
    args = ap.parse_args(argv)

    bcs = json.loads(BCS_JSON.read_text(encoding="utf-8"))
    before_pack = sum(1 for c in bcs["cards"].values() if c.get("in_pack"))
    before_susp = sum(1 for c in bcs["cards"].values() if c.get("in_suspect"))
    before = pc11(bcs, args.t)

    member = disk_membership()
    bcs, block = refresh(bcs, member)
    after = pc11(bcs, args.t)

    print(f"cards known to packs by name: {len(member)}")
    print(
        f"in_pack    {before_pack} -> {block['after']['in_pack']}   "
        f"in_suspect {before_susp} -> {block['after']['in_suspect']}   "
        f"flags changed on {block['changed_count']} cards"
    )
    print(
        f"PC-11 @ BCS>={args.t}: at-or-above {before['cards_at_or_above_t']} | "
        f"residue CACHED {before['residue']} -> TRUE {after['residue']} "
        f"({after['covered']} covered)"
    )
    for n in after["residue_names"][: args.list]:
        c = bcs["cards"][n]
        print(f"  residue: {n} (bcs {c.get('bcs')}, {c.get('handle')})")

    if args.write:
        bcs["membership"] = block
        BCS_JSON.write_text(json.dumps(bcs, indent=1), encoding="utf-8")
        print(f"wrote {BCS_JSON}")
    else:
        print("(dry run — pass --write to patch bcs.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
