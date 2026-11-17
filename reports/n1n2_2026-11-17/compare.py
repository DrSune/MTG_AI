"""N1/N2 on r28's v2: the old code against the new, from the two sides ``v2_side.py`` wrote.

    .venv/bin/python reports/n1n2_2026-11-17/compare.py OLD.pkl NEW.pkl > reports/n1n2_2026-11-17/compare.txt

1. ``saved`` (v2's own rows, read as saved): every row's component vector, the encodings, v2's
   logits and value on the recorded decisions and in the games it plays, old against new.
2. ``refreshed`` (r28's and r29's table flags): the rows whose tokens differ (cut at 128 before,
   a card name in them before, or both) with the size of the change on their vectors under v2's
   weights; the decisions with none of them visible against those with one; the games, decision
   by decision, up to the first that differs.
"""
from __future__ import annotations

import pickle
import sys
from collections import Counter
from pathlib import Path

import numpy as np

CUT = 128


def toks(side: dict, row: int) -> list[str]:
    return [side["ir_vocab"][i] for i in side["ir"][row]]


def max_abs(pairs) -> float:
    return max((float(np.max(np.abs(np.asarray(a, np.float64) - np.asarray(b, np.float64))))
                for a, b in pairs), default=0.0)


def same_feats(fa: dict, fb: dict) -> bool:
    return fa.keys() == fb.keys() and all(np.array_equal(fa[k], fb[k]) for k in fa)


def visible(feats: dict) -> set[int]:
    return {int(r) for r in feats["cards_i"][:, 0]}


def decisions(old: dict, new: dict, changed: set[int], label: str) -> None:
    ro, rn = old["recorded"], new["recorded"]
    assert ro["where"] == rn["where"], "the heuristic games differ"
    n = len(ro["feats"])
    enc = sum(same_feats(a, b) for a, b in zip(ro["feats"], rn["feats"], strict=True))
    touched = [i for i in range(n) if visible(ro["feats"][i]) & changed]
    clean = sorted(set(range(n)) - set(touched))
    print(f"  recorded decisions (heuristic games, {len({w[:2] for w in ro['where']})} deals): {n}; "
          f"encodings bitwise equal: {enc}/{n}")
    for name, idx in (("no changed card visible", clean), ("a changed card visible", touched)):
        if not idx:
            print(f"    {name}: none")
            continue
        dl = [float(np.max(np.abs(ro["logits"][i].astype(np.float64) - rn["logits"][i]))) for i in idx]
        dv = [abs(float(ro["values"][i]) - float(rn["values"][i])) for i in idx]
        same = sum(np.array_equal(ro["logits"][i], rn["logits"][i]) and ro["values"][i] == rn["values"][i]
                   for i in idx)
        flips = sum(int(np.argmax(ro["logits"][i])) != int(np.argmax(rn["logits"][i])) for i in idx)
        print(f"    {name}: {len(idx)}; logits and value bitwise equal {same}; max |dlogit| "
              f"{max(dl):.2e} (median {np.median(dl):.2e}), max |dvalue| {max(dv):.2e}; "
              f"greedy choice differs {flips}")
    # the games v2 plays
    print(f"  games v2 plays greedily ({label}):")
    for go, gn in zip(old["played"], new["played"], strict=True):
        do, dn = go["decisions"], gn["decisions"]
        first = next((i for i, (a, b) in enumerate(zip(do, dn)) if a["choice"] != b["choice"]
                      or not same_feats(a["feats"], b["feats"])), None)
        if first is None and len(do) != len(dn):
            first = min(len(do), len(dn))
        upto = len(do) if first is None else first
        pre = [(do[i], dn[i]) for i in range(upto)]
        pre_clean = [p for p in pre if not visible(p[0]["feats"]) & changed]
        lmax = max_abs((a["logits"], b["logits"]) for a, b in pre_clean)
        vmax = max_abs(([a["value"]], [b["value"]]) for a, b in pre_clean)
        bit = sum(np.array_equal(a["logits"], b["logits"]) and a["value"] == b["value"] for a, b in pre_clean)
        head = (f"    {go['set']} seed {go['seed']} vs {go['opp']}: {len(do)} / {len(dn)} decisions, "
                f"result {go['result']['outcome']} w{go['result']['winner']} t{go['result']['turns']} / "
                f"{gn['result']['outcome']} w{gn['result']['winner']} t{gn['result']['turns']}; ")
        if first is None:
            print(head + f"the same game ({len(pre_clean)} decisions without a changed card: "
                  f"{bit} bitwise, max |dlogit| {lmax:.2e}, |dvalue| {vmax:.2e})")
            continue
        at = do[first] if first < len(do) else dn[first]
        vis = sorted(visible(at["feats"]) & changed)
        print(head + f"the same up to decision {first} ({len(pre_clean)} before it without a changed "
              f"card: {bit} bitwise, max |dlogit| {lmax:.2e}); there a {at['kind']} ask on turn "
              f"{at['turn']}, changed cards visible: {[old['names'][r] for r in vis]}")


def main(path_old: str, path_new: str) -> None:
    O, N = (pickle.loads(Path(p).read_bytes()) for p in (path_old, path_new))
    print("# N1/N2 on r28 v2: the base commit's code (32e804ec) against N1/N2's, CPU fp32")

    print("\n## 1. v2's own table, read as saved (rows cut at 128, names in)")
    old, new = O["saved"], N["saved"]
    assert old["ir"] == new["ir"] and old["ir_vocab"] == new["ir_vocab"]
    d = np.abs(old["card_vec"].astype(np.float64) - new["card_vec"])
    eq = int(np.sum(np.all(old["card_vec"] == new["card_vec"], axis=1)))
    print(f"  rows {len(old['ir'])}: the same rows; component vectors bitwise equal {eq}, max |diff| "
          f"{d.max():.2e} (count matrix against gather-and-mean: fp32 summation order)")
    decisions(old, new, set(), "saved")

    print("\n## 2. Refreshed as r28 and r29 build it (--refresh-table --extend-sets M20 --mix-sets M20)")
    old, new = O["refreshed"], N["refreshed"]
    print(f"  old: {O['refreshed_log']['refresh']['rows_changed']} rows rebuilt, "
          f"{O['refreshed_log']['refresh']['tokens_added']} tokens added; new: "
          f"{N['refreshed_log']['refresh']['rows_changed']} rows, {N['refreshed_log']['refresh']['tokens_added']} tokens")
    added_o = old["ir_vocab"][590:]
    added_n = new["ir_vocab"][590:]
    print(f"  tokens only the old refresh adds: {sorted(set(added_o) - set(added_n))}")
    print(f"  tokens only the new refresh adds: {sorted(set(added_n) - set(added_o))}")
    assert old["oracle_ids"] == new["oracle_ids"]
    cut, named, both = [], [], []
    for r in range(len(old["ir"])):
        a, b = toks(old, r), toks(new, r)
        if a == b:
            continue
        is_cut = len(a) == CUT and len(b) > CUT
        is_name = ("@face_name" in a or any(t in ("str:~", "str:<name>") for t in b))
        assert is_cut or is_name, (old["names"][r], len(a), len(b))
        (both if is_cut and is_name else cut if is_cut else named).append(r)
    changed = set(cut) | set(named) | set(both)
    unchanged = [r for r in range(len(old["ir"])) if r not in changed]
    du = np.abs(old["card_vec"][unchanged].astype(np.float64) - new["card_vec"][unchanged])
    eq = int(np.sum(np.all(old["card_vec"][unchanged] == new["card_vec"][unchanged], axis=1)))
    print(f"  rows {len(old['ir'])}: tokens differ on {len(changed)} (past {CUT}: {len(cut) + len(both)}, "
          f"a card name: {len(named) + len(both)}, both: {len(both)}); the other {len(unchanged)}: "
          f"vectors bitwise equal {eq}, max |diff| {du.max():.2e}")

    def size(r: int) -> str:
        vo, vn = old["card_vec"][r].astype(np.float64), new["card_vec"][r].astype(np.float64)
        return f"|dv| {np.linalg.norm(vn - vo):.3f} ({np.linalg.norm(vn - vo) / np.linalg.norm(vo):.0%} of |v| {np.linalg.norm(vo):.3f})"

    zero = {i for i in range(len(new["ir_emb"])) if not np.any(new["ir_emb"][i])}
    # tokens v2 never trained: no saved row holds them (they were only ever past the cut), or
    # their row is still zero, or the refresh added them
    held = {i for r in N["saved"]["ir"] for i in r}
    untrained = {t for i, t in enumerate(new["ir_vocab"]) if i not in held or i in zero}
    print(f"\n  tokens of v2's vocabulary no saved row holds (only ever past the cut, never trained): "
          f"{sorted(t for i, t in enumerate(new['ir_vocab'][:590]) if i and i not in held)}")
    print(f"\n  ### rows past {CUT}, now whole ({len(cut) + len(both)}), longest first: the verbs and "
          f"keywords the row lacked entirely and has back (other components back counted), and how "
          f"many of its tokens v2 never trained")
    lost_verbs = 0
    for r in sorted(cut + both, key=lambda r: -len(new["ir"][r])):
        a, b = toks(old, r), toks(new, r)
        back = sorted({t for t in b if t not in set(a)} - {"str:~", "str:<name>"})
        verbs = [t for t in back if t.startswith(("Verb.", "Keyword."))]
        lost_verbs += sum(1 for t in back if t.startswith("Verb."))
        cold = sum(1 for t in b if t in untrained)
        print(f"    {old['names'][r]}: {len(a)} -> {len(b)} tokens, {size(r)}; back: "
              f"{', '.join(verbs) or '-'}{' (+' + str(len(back) - len(verbs)) + ' others)' if len(back) > len(verbs) else ''}"
              f"{f'; untrained {cold}' if cold else ''}{'; also a name' if r in both else ''}")
    print(f"  verb-card pairs back: {lost_verbs}")
    print(f"\n  ### rows with a card name in them before ({len(named) + len(both)})")
    for r in sorted(named + both, key=lambda r: old["names"][r]):
        a, b = toks(old, r), toks(new, r)
        gone = sorted((Counter(a) - Counter(b)).elements())
        came = sorted((Counter(b) - Counter(a)).elements())
        if r in both:
            gone, came = [t for t in gone if t.startswith("str:") or t == "@face_name"], \
                [t for t in came if t in ("str:~", "str:<name>")]
        print(f"    {old['names'][r]}: {size(r)}; {gone} -> {came}")
    print("  (the new tokens str:~ and str:<name> start at zero, extend_cards, as every new token)")
    for label, rs in (("past 128", cut + both), ("a name", named + both), ("all changed", sorted(changed))):
        rel = [np.linalg.norm(new["card_vec"][r].astype(np.float64) - old["card_vec"][r])
               / np.linalg.norm(old["card_vec"][r].astype(np.float64)) for r in rs]
        print(f"  |dv| / |v| over the rows {label} ({len(rs)}): median {np.median(rel):.0%}, "
              f"quartiles {np.percentile(rel, 25):.0%}-{np.percentile(rel, 75):.0%}, max {max(rel):.0%}")
    decisions(old, new, changed, "refreshed")
    print(f"\n  component rows exactly zero in v2: {sorted(new['ir_vocab'][i] for i in zero if i < 590)}")
    for i in sorted(z for z in zero if z < 590):
        rows = [new["names"][r] for r in range(len(new["ir"])) if i in new["ir"][r]]
        print(f"    {new['ir_vocab'][i]}: on {rows}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
