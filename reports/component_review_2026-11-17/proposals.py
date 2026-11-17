"""The proposals' gain and blast radius, by script.

    .venv/bin/python reports/component_review_2026-11-17/proposals.py > reports/component_review_2026-11-17/proposals.txt

IR side, per proposal: the tokens it removes from the vocabulary and the one(s) it adds; the trees
of the 19 sets that change (distinct oracle ids); the verified stamps that re-bake (home stamps of
M21, M20 and FDN; reprint stamps of the 16 other sets); the unverified trees of M21, M20 and FDN
that change (no stamp to lose); the unparsed sentences of the unverified M21, M20 and FDN cards
that need the form (mapped before the fold, each would be mapped again after it); examples per
token before and after (cards of the 19 sets).

Network side: the stream with field keys and exact copies dropped (tokens per card, cards past
128), and the per-forward cost of the component pool.
"""
from __future__ import annotations

import re
import statistics as stats
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C
import duplicates as Dp

MAX_IR = 128


def has_pred(names):
    def f(t, r):
        return any(n.get("tag") == "FAtom" and Dp.enum(n, "pred") in names for n, _ in Dp.nodes(t))
    return f


def has_tag(names):
    def f(t, r):
        return any(n.get("tag") in names for n, _ in Dp.nodes(t))
    return f


def has_verb(names):
    def f(t, r):
        return any(Dp.is_atom(n) and Dp.enum(n, "verb") in names for n, _ in Dp.nodes(t))
    return f


def any_of(*fs):
    return lambda t, r: any(f(t, r) for f in fs)


COMPARATORS = ("POWER_LE", "POWER_GE", "CMC_LE", "CMC_GE", "COLOR_COUNT_GE", "LIFE_TOTAL_GE",
               "LIFE_LEAD_OVER_START_GE", "CONTROLLER_COUNT_GE", "CONTROLLER_COUNT_GT", "ZONE_COUNT_GE",
               "NAME_PARTITION_COUNT_GE")
LEGACY_TURN = ("DIED_THIS_TURN", "LIFE_GAINED_THIS_TURN_GE", "CARDS_DRAWN_THIS_TURN_GE", "MOVED_TO_ZONE_THIS_TURN",
               "INSTANT_OR_SORCERY_CAST_THIS_TURN", "CAST_THIS_TURN_FROM", "ENTERED_THIS_TURN_FROM",
               "NOT_FIRST_DRAW_THIS_STEP", "ATTACK_AGAINST_COUNT_GE")


def self_forms(t, r):
    """'this <permanent>' written as ALL+QConst(1)+FAnd(CONTROLLER_IS YOU, IS_SOURCE) in an effect,
    CHOOSE+QConst(1)+FAnd(...) in an effect, or the FAnd form in a cost part (D25)."""
    for n, path in Dp.nodes(t):
        if n.get("tag") in Dp.COST_PARTS and isinstance(n.get("target"), dict):
            f = n["target"].get("filter") or {}
            if f.get("tag") == "FAnd" and Dp.preds(f) == {"IS_SOURCE", "CONTROLLER_IS"}:
                return True
        if n.get("tag") == "Selector":
            f = n.get("filter") or {}
            if f.get("tag") == "FAnd" and Dp.preds(f) == {"IS_SOURCE", "CONTROLLER_IS"}:
                return True
    return False


def move_target(t, r):
    return any(Dp.is_atom(n, "MOVE_ZONE") and "target" in Dp.roles(n) for n, _ in Dp.nodes(t))


def names_self(t, r):
    """A card's own name in its tree (NAME_EQ "cards named ~", the party template's NAME_CONTAINS
    beside IS_SOURCE), or a planeswalker type written as NAME_CONTAINS (CR 205.3j: "a Garruk
    planeswalker" is a subtype, which other trees write SUBTYPE_EQ)."""
    for n, _ in Dp.nodes(t):
        if n.get("tag") != "FAtom":
            continue
        p = Dp.enum(n, "pred")
        if p in ("NAME_EQ", "NAME_CONTAINS") and n.get("string_value") == r["name"]:
            return True
        if p == "NAME_CONTAINS":
            return True
    return False


def colour_choose(t, r):
    return "Choose over five colours (resolution)" in Dp.detectors()["F13 'choose a colour': a Choose over five or CHOOSE_NAME(COLOR)"](t, r)


def small_folds(t, r):
    D = Dp.detectors()
    sides = set()
    for name, keep in (("D12 SEARCH.controller written or left out", {"controller written"}),
                       ("D13 a cost victim's selector mode (TARGET or CHOOSE)", {"cost victim mode TARGET", "cost victim mode ALL"}),
                       ("D14 Planeswalker as SUPERTYPE_EQ or TYPE_EQ", {"SUPERTYPE_EQ Planeswalker"}),
                       ("D18 'its controller' as TARGET_PLAYER", {"TARGET_PLAYER, text prints none (the D18 form)"}),
                       ("D19 a move into a library with or without a position", {"library, no position"}),
                       ("D22 'as long as' on a static: its condition or a DurationWhileCondition", {"DurationWhileCondition on the atom"}),
                       ("D23 one static's keyword grants: sorted or printed order", {"two or more grants, printed order"}),
                       ("B-48 discard: Verb.DISCARD or MOVE_ZONE from a hand to a graveyard", {"Verb.DISCARD"})):
        if D[name](t, r) & keep:
            sides.add(name.split()[0])
    for side in D["D21 'each opponent <verb>s': EachPlayer around one atom or a plural controller"](t, r):
        if side.startswith("EachPlayer") and any(v in side for v in ("DRAW", "CREATE_TOKEN", "DEAL_DAMAGE", "MOVE_ZONE")) \
                and r["name"] not in ("Yarok's Fenlurker",):
            sides.add("D21")
    return bool(sides)


PROPOSALS = (
    ("I1 one quantity comparison", any_of(has_pred(COMPARATORS)),
     list(COMPARATORS) + ["PT_LE", "PT_GE", "CONTROLLER_COUNT_LE"], ["FAtomPred.QTY_GE"],
     r"(power|toughness|mana value) (\w+ )?(or greater|or less)|(less|greater) than or equal to|"
     r"toughness (less|greater) than|\b(two|three|four|five|six|seven|eight|nine|ten|thirteen|\d+) or more \w+|"
     r"starting life total|\d+ or more life|total power|life total is"),
    ("I2 turn history on EVENT_THIS_TURN", any_of(has_pred(LEGACY_TURN), has_tag(("QThisTurn",))),
     list(LEGACY_TURN), ["(none: EVENT_THIS_TURN, SUBJECT_OF_EVENT_THIS_TURN exist)"],
     r"died this turn|attacked this turn|lost life this turn|gained this turn|this turn dies|put there this turn|"
     r"you've cast|second card each turn|first time each turn|cast before it this turn"),
    ("I3 one form for 'this <permanent>'", self_forms, [], [],
     r"\b(this (creature|artifact|land|enchantment|equipment|aura)|~) (gets|gains)\b|"
     r"counters? on (this \w+|~|it)\b|sacrifice (this|~)"),
    ("I4 one role for MOVE_ZONE's objects (B-42)", move_target, [], [],
     r"\bexile (up to \w+ )?(another )?(target|it|that|them|each|all|those)\b"),
    ("I5 names by referent or type, not by string", names_self, ["NAME_CONTAINS"], ["(NAME_EQ takes a referent)"],
     r"\bnamed\b|same name"),
    ("I6 one POLICY verb, one MANDATE verb (F9)", has_verb(("MANA_POLICY", "DAMAGE_ASSIGN_POLICY", "ATTACK_POLICY",
                                                              "MANDATE_BLOCK")),
     ["MANA_POLICY", "DAMAGE_ASSIGN_POLICY", "ATTACK_POLICY", "MANDATE_BLOCK"], ["Verb.POLICY", "(MANDATE_ATTACK kept as MANDATE)"],
     r"as though|assigns combat damage|attacks each combat if able|able to block|spend (this )?mana|mana of any type"),
    ("I7 'choose a colour' at resolution as CHOOSE_NAME(COLOR) (F13)", colour_choose, [], [],
     r"color of your choice|choose a color"),
    ("I8 the ledger's small folds (D12-D14, D18, D19, D21-D23, B-48)", small_folds, ["Verb.DISCARD"], [],
     r"(each opponent|each player) (draws|mills|creates)|search your library"),
    ("I9 three one-case nodes made general: TARGETS(filter), QDistinct(property), zone counts as QCount",
     any_of(has_pred(("TARGETS_SOURCE",)), has_tag(("QDistinctColorCount",)),
            lambda t, r: any(n.get("tag") == "QProp" and Dp.enum(n, "field") in
                             ("CARDS_IN_HAND", "CARDS_IN_GRAVEYARD", "CARDS_IN_LIBRARY") for n, _ in Dp.nodes(t))),
     ["TARGETS_SOURCE", "QDistinctColorCount", "QPropField.CARDS_IN_HAND", "QPropField.CARDS_IN_GRAVEYARD"],
     ["FAtomPred.TARGETS", "QDistinct"],
     r"targets? (you|a creature|this|a tapped)|becomes the target of a spell|different (names|mana)|"
     r"number of cards in"),
)


def main() -> None:
    rows = C.load()
    allc = C.compiled_all(rows)
    df = C.doc_freq(allc)
    rem_sents = []
    for r in rows:
        if r["set"] in C.HOME and r["state"] != "verified":
            for s, _ in (r.get("unparsed") or []) + (r.get("back_unparsed") or []):
                # reminder text in parentheses restates a keyword; it is not a sentence to map
                rem_sents.append((r, re.sub(r"\([^)]*\)", "", C.norm_sentence(s, r["name"]))))
    print("# IR-side proposals: gain and blast radius")
    print("trees: distinct oracle ids of the 19 sets whose tree changes | stamps: verified home (M21+M20+FDN) "
          "+ reprint | unverified home trees | remaining unparsed sentences needing the form")
    for name, fn, removed, added, pattern in PROPOSALS:
        oids, home, rep, unv = set(), [], 0, set()
        for r in rows:
            if "tree" not in r or not fn(r["tree"], r):
                continue
            oids.add(r["oid"])
            if r["state"] == "verified":
                if r["reprint_of"]:
                    rep += 1
                else:
                    home.append(f"{r['set']} {r['name']}")
            elif r["set"] in C.HOME:
                unv.add(r["oid"])
        pat = re.compile(pattern, re.IGNORECASE)
        need = [(r, s) for r, s in rem_sents if pat.search(s)]
        print(f"\n## {name}")
        print(f"  trees {len(oids)} | stamps {len(home)} home + {rep} reprint | unverified home trees {len(unv)} | "
              f"remaining sentences {len(need)} on {len({r['oid'] for r, _ in need})} cards")
        if removed:
            before = [(t, df.get(t, 0) or df.get(f"FAtomPred.{t}", 0) or df.get(f"Verb.{t}", 0)) for t in removed]
            print("  tokens removed (cards of the 19 sets each): " + ", ".join(f"{t} {n}" for t, n in before)
                  + f"; added: {', '.join(added)} (on {len(oids)} trees)")
        print("  home stamps: " + "; ".join(sorted(home)[:40]) + (" ..." if len(home) > 40 else ""))
        print("  remaining sentences, e.g.: " + " | ".join(f"{r['name']}: {s[:70]}" for r, s in need[:6]))

    # bundles: the union of what several proposals touch (a card in two proposals re-bakes once)
    print("\n\n# Bundles (one gate round each, the recommended order)")
    fns = {name.split()[0]: fn for name, fn, *_ in PROPOSALS}
    pats = {name.split()[0]: re.compile(p, re.IGNORECASE) for name, _, _, _, p in PROPOSALS}
    for bundle in (("I1", "I9"), ("I2", "I5", "I6"), ("I3", "I4"), ("I8", "I7"),
                   ("I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8", "I9")):
        oids, home, rep, unv = set(), set(), set(), set()
        for r in rows:
            if "tree" in r and any(fns[b](r["tree"], r) for b in bundle):
                oids.add(r["oid"])
                if r["state"] == "verified":
                    (rep if r["reprint_of"] else home).add((r["set"], r["oid"]))
                elif r["set"] in C.HOME:
                    unv.add(r["oid"])
        need = {r["oid"] for r, s in rem_sents if any(pats[b].search(s) for b in bundle)}
        print(f"  {'+'.join(bundle)}: trees {len(oids)}, stamps {len(home)} home + {len(rep)} reprint, "
              f"unverified home trees {len(unv)}, remaining cards with a sentence needing it {len(need)}")

    # network side: the slim stream
    print("\n\n# Network side: the stream without field keys and exact copies")
    sig = defaultdict(list)
    vocab = sorted({t for r in allc for t in r["tokens"]})
    counts = [Counter(r["tokens"]) for r in allc]
    for t in vocab:
        sig[tuple(c.get(t, 0) for c in counts)].append(t)
    drop = {t for g in sig.values() if len(g) > 1 for t in sorted(g, key=lambda x: (x.startswith("@"), x))[1:]}
    drop |= {t for t in vocab if t.startswith("@")}
    for label, pop in (("verified", C.verified_home(rows)), ("19 sets", allc)):
        full = [len(r["tokens"]) for r in pop]
        slim = [len([t for t in r["tokens"] if t not in drop]) for r in pop]
        q = lambda xs, p: sorted(xs)[min(len(xs) - 1, int(p * len(xs)))]
        print(f"  {label}: tokens per card mean {stats.mean(full):.1f} -> {stats.mean(slim):.1f}, median "
              f"{q(full, .5)} -> {q(slim, .5)}, p90 {q(full, .9)} -> {q(slim, .9)}, max {max(full)} -> {max(slim)}; "
              f"past 128: {sum(1 for n in full if n > MAX_IR)} -> {sum(1 for n in slim if n > MAX_IR)}")
    print(f"  tokens dropped from the vocabulary: {len(drop)} of {len(vocab)} "
          f"(field keys {sum(1 for t in drop if t.startswith('@'))}, copies {sum(1 for t in drop if not t.startswith('@'))})")

    # the safer variant: a field key before a scalar value (num:, bool:, str:) is fused with it into
    # one token (it says which field the bare value fills: '@tapped bool:True'); a key before a
    # tagged node or an enum is dropped (the tag says it); exact copies dropped
    def slim_fused(toks: list[str]) -> list[str]:
        out, i = [], 0
        while i < len(toks):
            t = toks[i]
            if t.startswith("@"):
                nxt = toks[i + 1] if i + 1 < len(toks) else ""
                if nxt.startswith(("num:", "bool:", "str:")):
                    out.append(f"{t[1:]}={nxt}")
                    i += 2
                    continue
                i += 1
                continue
            if t not in drop:
                out.append(t)
            i += 1
        return out
    for label, pop in (("verified", C.verified_home(rows)), ("19 sets", allc)):
        full = [len(r["tokens"]) for r in pop]
        fused = [slim_fused(r["tokens"]) for r in pop]
        n = [len(x) for x in fused]
        q = lambda xs, p: sorted(xs)[min(len(xs) - 1, int(p * len(xs)))]
        v = {t for x in fused for t in x}
        print(f"  fused variant, {label}: tokens per card mean {stats.mean(full):.1f} -> {stats.mean(n):.1f}, median "
              f"{q(full, .5)} -> {q(n, .5)}, max {max(full)} -> {max(n)}; past 128: "
              f"{sum(1 for x in full if x > MAX_IR)} -> {sum(1 for x in n if x > MAX_IR)}; vocabulary {len(v)}")
    n_rows, d = 611, 512
    print(f"  the component pool per forward (r28 v2: {n_rows} rows, d {d}): a gather of {n_rows}x{MAX_IR}x{d} = "
          f"{n_rows * MAX_IR * d / 1e6:.1f}M values, against a count matrix {n_rows}x{len(vocab)} times the table "
          f"{len(vocab)}x{d} ({n_rows * len(vocab) * d / 1e6:.0f}M multiply-adds, {n_rows * d / 1e6:.2f}M values out)")


if __name__ == "__main__":
    main()
