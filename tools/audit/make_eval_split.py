"""Deterministic family-wise eval split (KNOWLEDGE/2026-10-05/15 rule, toolified 2026-10-07).

Rule: sort distinct card names (families); index % 5 in {0, 1} -> EVAL (2 of every 5).
Frozen-assignment discipline: families already assigned in an existing split keep their
assignment; only NEW families are assigned by the rule over the regenerated sort.
No RNG, ever. Corpus is the single source of families/items.

Usage: python -m tools.audit.make_eval_split [--corpus PATH] [--split PATH] [--dry]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build(corpus: dict, existing: dict | None) -> dict:
    items = corpus["items"]
    fam_of = {}
    for it in items:
        fam_of.setdefault(it["card"], []).append(it)
    families = sorted(fam_of)
    frozen = {}
    if existing:
        for f in existing.get("eval_families", []):
            frozen[f] = "eval"
        for f in existing.get("train_families", []):
            frozen[f] = "train"
    eval_fams, train_fams, assigned_by_rule = [], [], []
    for i, fam in enumerate(families):
        if fam in frozen:
            (eval_fams if frozen[fam] == "eval" else train_fams).append(fam)
        else:
            if i % 5 in (0, 1):
                eval_fams.append(fam)
            else:
                train_fams.append(fam)
            assigned_by_rule.append(fam)
    eval_set = set(eval_fams)
    per_family = [
        {
            "family": f,
            "side": "eval" if f in eval_set else "train",
            "items": len(fam_of[f]),
            "l1_ready": sum(1 for it in fam_of[f] if it.get("l1_ready")),
        }
        for f in families
    ]
    return {
        "rule": (
            "family-wise deterministic: sort distinct card names, index%5 in {0,1} -> "
            "eval (2 of every 5). Frozen prior assignments win; new families take the "
            "rule in the regenerated sort."
        ),
        "seed_rule": "no RNG",
        "n_families": len(families),
        "eval_families": eval_fams,
        "train_families": train_fams,
        "eval_items": sum(len(fam_of[f]) for f in eval_fams),
        "train_items": sum(len(fam_of[f]) for f in train_fams),
        "eval_l1_ready": sum(
            sum(1 for it in fam_of[f] if it.get("l1_ready")) for f in eval_fams
        ),
        "new_families_assigned": assigned_by_rule,
        "per_family": per_family,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", default="tools/audit/puzzle_corpus.json")
    ap.add_argument("--split", default="tools/audit/eval_split.json")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    corpus = json.loads(Path(a.corpus).read_text())
    sp_path = Path(a.split)
    existing = json.loads(sp_path.read_text()) if sp_path.exists() else None
    out = build(corpus, existing)
    print(
        f"families {out['n_families']} | eval {len(out['eval_families'])}/"
        f"{out['eval_items']} items | train {len(out['train_families'])}/"
        f"{out['train_items']} | new assigned: {out['new_families_assigned']}"
    )
    if not a.dry:
        sp_path.write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
