"""N1/N2 over the cards themselves: every compiled card of the 19 sets (records applied, the
review's population, KNOWLEDGE/2026-11-17/210 §0), tokenised by the base commit's
``features.card_tokens`` (read from git) and by this one's.

    CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 nice -n 19 .venv/bin/python \
        reports/n1n2_2026-11-17/census.py > reports/n1n2_2026-11-17/census.txt

N1: the cards past 128 tokens, the tokens and the components the cut took. N2: the cards whose
tokens held a card name, by path, and a check that no name is left; and that the two
tokenisations differ only there.
"""
from __future__ import annotations

import subprocess
import sys
import types
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "tools" / "cards"):
    sys.path.insert(0, str(p))
import corpus
from cardtool import _state

from tools.selfplay import features as FT

BASE = "32e804ec"  # main before N1/N2
CUT = 128
LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest"}  # basic land types, CR 205.3i


def old_features() -> types.ModuleType:
    src = subprocess.run(["git", "-C", str(REPO), "show", f"{BASE}:tools/selfplay/features.py"],
                         capture_output=True, text=True, check=True).stdout
    mod = sys.modules["features_base"] = types.ModuleType("features_base")  # for its dataclass
    exec(compile(src, f"{BASE}:tools/selfplay/features.py", "exec"), mod.__dict__)  # noqa: S102
    return mod


def first(rows: list[dict], keep) -> list[dict]:
    """One row per oracle id, the first kept one (the review's common.verified_home and
    compiled_all)."""
    out, seen = [], set()
    for r in rows:
        if keep(r) and r["oid"] not in seen:
            seen.add(r["oid"])
            out.append(r)
    return out


def main() -> None:
    old = old_features()
    rows = []
    names: set[str] = set()
    for code in corpus.SETS:
        sc = corpus.compile_set(code)
        for oid, raw in sc.raw.items():
            if raw.is_token or raw.is_emblem:
                continue
            names.update({raw.identity.name, *raw.identity.name.split(" // ")})
            if oid in sc.refused:
                continue
            card = sc.results[oid].card
            rows.append({"set": code, "oid": oid, "name": raw.identity.name,
                         "state": _state(sc, oid), "old": old.card_tokens(card),
                         "new": FT.card_tokens(card)})
    home = sorted((r for r in rows if r["set"] in ("M21", "M20", "FDN")),
                  key=lambda r: ("M21", "M20", "FDN").index(r["set"]))
    for label, pop in (("verified M21+M20+FDN", first(home, lambda r: r["state"] == "verified")),
                       ("every compiled tree, 19 sets", first(rows, lambda r: True))):
        print(f"\n## {label}: {len(pop)} cards (one per oracle id, the first set's)")
        # N1
        over = [r for r in pop if len(r["new"]) > CUT]
        lost = Counter()
        for r in over:
            kept = set(r["new"][:CUT])
            lost.update(t.split(".")[0] for t in set(r["new"][CUT:]) - kept
                        if t.startswith(("Verb.", "Keyword.")))
        print(f"  N1: past {CUT} tokens {len(over)} cards ({100 * len(over) / len(pop):.1f}%); tokens the "
              f"cut took {sum(len(r['new']) - CUT for r in over)}; components a card lost outright, back "
              f"now: verbs {lost['Verb']}, keywords {lost['Keyword']}; the longest "
              f"{max(len(r['new']) for r in pop)} tokens")
        # N2
        kinds = defaultdict(list)
        for r in pop:
            if r["old"] == r["new"]:
                continue
            a, b = r["old"], r["new"]
            k = []
            if "@face_name" in a:
                k.append("a back face's name left out")
            if FT.SELF_NAME in b:
                k.append("own name -> str:~")
            if FT.OTHER_NAME in b:
                k.append("another card's name -> str:<name>")
            # the two differ only there: drop the face name pairs and map the name strings back
            a2 = [t for i, t in enumerate(a) if t != "@face_name" and not (i and a[i - 1] == "@face_name")]
            assert len(a2) == len(b) and all(x == y or y in (FT.SELF_NAME, FT.OTHER_NAME)
                                             for x, y in zip(a2, b, strict=True)), r["name"]
            for x in k:
                kinds[x].append(r)
        left = Counter(t for r in pop for t in r["new"] if t == "@face_name"
                       or (t.startswith("str:") and t[4:] in names - LANDS))
        print(f"  N2: cards whose tokens changed {sum(1 for r in pop if r['old'] != r['new'])}; "
              f"name tokens left: {dict(left) or 'none'} (a basic land type, CR 205.3i, is a subtype)")
        for k, rs in sorted(kinds.items()):
            shown = ", ".join(f"{r['set']} {r['name']}" for r in rs[:40])
            print(f"    {k}: {len(rs)}: {shown}{' ...' if len(rs) > 40 else ''}")
        old_vocab = {t for r in pop for t in r["old"]}
        new_vocab = {t for r in pop for t in r["new"]}
        print(f"  distinct tokens {len(old_vocab)} -> {len(new_vocab)} (gone: {len(old_vocab - new_vocab)}, "
              f"new: {sorted(new_vocab - old_vocab)})")


if __name__ == "__main__":
    main()
