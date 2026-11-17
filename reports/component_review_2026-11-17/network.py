"""Measure 4: what the network's card input (``features.card_tokens``, mean-pooled by
``model.card_table_emb``, first ``max_ir`` = 128 tokens) can and cannot share.

    .venv/bin/python reports/component_review_2026-11-17/network.py > reports/component_review_2026-11-17/network.txt

1. Two cards one slot word apart (Murder, Shatter): what they share.
2. Mass: structural tokens (``@field`` keys and tags that always travel with another token) and
   their share of a card's mean; tokens that are perfect copies of each other (same count on
   every card).
3. Collisions: distinct trees that become the same bag (multiset), the same mean (multiset up to
   scale) and the same truncated mean, with examples; what tells them apart.
4. Numbers: cards carrying two or more different number tokens (which number goes with which
   verb is not in the bag).
5. Truncation: cards past 128, the tokens cut by kind, and the components a card loses entirely.
6. Names: card names inside component tokens (a back face's name, NAME_EQ, NAME_CONTAINS).
7. One value, two tokens: a face's ``type:X`` / ``sub:X`` and a filter's ``str:X``.
"""
from __future__ import annotations

import json
import statistics as stats
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from functools import reduce
from math import gcd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

MAX_IR = 128


def norm_hist(tokens: list[str]) -> tuple:
    """The token histogram up to scale: the mean pool of any embedding is the same for two cards
    exactly when this is."""
    c = Counter(tokens)
    g = reduce(gcd, c.values())
    return tuple(sorted((t, n // g) for t, n in c.items()))


def tree_key(r: dict) -> str:
    return json.dumps(r["tree"], sort_keys=True) + "|" + "|".join(r["face"])


def collisions(pop: list[dict], label: str) -> None:
    trees = {}
    for r in pop:
        trees.setdefault(tree_key(r), r)
    print(f"\n## 3. Collisions over {label}: {len(trees)} distinct (tree + face) meanings")
    for name, key in (("same multiset (order lost)", lambda t: tuple(sorted(Counter(t).items()))),
                      ("same mean (multiset up to scale)", norm_hist),
                      ("same set (counts lost)", lambda t: tuple(sorted(set(t)))),
                      ("same mean of the first 128 (what the network reads)", lambda t: norm_hist(t[:MAX_IR]))):
        groups = defaultdict(list)
        for r in trees.values():
            groups[key(r["tokens"])].append(r)
        coll = [g for g in groups.values() if len(g) > 1]
        print(f"  {name}: {len(groups)} distinct bags; {len(coll)} bags hold 2+ meanings "
              f"({sum(len(g) for g in coll)} meanings)")
        if name.startswith("same multiset") or name.startswith("same mean of the first"):
            for g in sorted(coll, key=lambda g: -len(g))[:6]:
                print("    e.g. " + " | ".join(f"{r['set']} {r['name']}" for r in g[:4]))


def main() -> None:
    rows = C.load()
    ver, allc = C.verified_home(rows), C.compiled_all(rows)
    by_name = {}
    for r in rows:
        by_name.setdefault(r["name"], r)

    # 1. Murder and Shatter
    print("## 1. 'Destroy target creature.' (M20 Murder) against 'Destroy target artifact.' (M10 Shatter)")
    a, b = by_name["Murder"]["tokens"], by_name["Shatter"]["tokens"]
    ca, cb = Counter(a), Counter(b)
    shared = sum((ca & cb).values())
    print(f"  tokens {len(a)} and {len(b)}; shared {shared}; only Murder: {sorted((ca - cb).elements())}; "
          f"only Shatter: {sorted((cb - ca).elements())}")
    info = [t for t in a if not t.startswith("@") and t not in ("Atom", "AtomArgs", "Selector", "FAtom", "Zone")]
    print(f"  of Murder's {len(a)} tokens, {len(a) - len(info)} are field keys or carrier tags "
          f"(@..., Atom, AtomArgs, Selector, FAtom, Zone); the rest: {' '.join(info)}")

    # 2. mass
    for label, pop in (("verified", ver), ("19 sets", allc)):
        fields = [sum(1 for t in r["tokens"][:MAX_IR] if t.startswith("@")) / max(1, len(r["tokens"][:MAX_IR]))
                  for r in pop]
        print(f"\n## 2. Mass ({label}): '@field' tokens are {stats.mean(fields):.2f} of a card's (truncated) "
              f"bag on average (median {stats.median(fields):.2f})")
    # perfect copies: same count on every card of the 19 sets
    sig = defaultdict(list)
    vocab = sorted({t for r in allc for t in r["tokens"]})
    counts = [Counter(r["tokens"]) for r in allc]
    for t in vocab:
        sig[tuple(c.get(t, 0) for c in counts)].append(t)
    copies = [g for g in sig.values() if len(g) > 1]
    redundant = sum(len(g) - 1 for g in copies)
    print(f"  tokens that are an exact copy of another (the same count on every compiled card of the "
          f"19 sets): {redundant} tokens in {len(copies)} groups; the largest:")
    for g in sorted(copies, key=lambda g: -sum(sig_k for sig_k in [0]) - len(g))[:12]:
        uses = sum(counts[i].get(g[0], 0) for i in range(len(allc)))
        print(f"    {uses:6d} uses each: {' = '.join(g)}")
    copy_mass = []
    copyset = {t for g in copies for t in g[1:]}
    for r in ver:
        toks = r["tokens"][:MAX_IR]
        copy_mass.append(sum(1 for t in toks if t in copyset) / max(1, len(toks)))
    print(f"  share of a verified card's (truncated) bag that is such a copy: mean {stats.mean(copy_mass):.2f}")

    # 3. collisions
    collisions(ver, "the verified cards")
    collisions(allc, "the 19 sets' compiled trees")

    # 4. numbers
    for label, pop in (("verified", ver), ("19 sets", allc)):
        multi = 0
        for r in pop:
            nums = {t for t in r["tokens"][len(r["face"]):] if t.startswith("num:")}
            multi += len(nums) >= 2
        print(f"\n## 4. Numbers ({label}): {multi} of {len(pop)} cards ({100 * multi / len(pop):.0f}%) carry two "
              f"or more different number tokens in their tree; the bag does not say which number belongs "
              f"to which verb or role")

    # 5. truncation
    for label, pop in (("verified", ver), ("19 sets", allc)):
        over = [r for r in pop if len(r["tokens"]) > MAX_IR]
        cut = Counter()
        lost_cards = Counter()
        lost_examples = defaultdict(list)
        kw_cut = 0
        for r in over:
            kept, gone = r["tokens"][:MAX_IR], r["tokens"][MAX_IR:]
            cut.update(C.kind(t) for t in gone)
            lost = {t for t in gone if t not in set(kept)}
            for t in lost:
                k = C.kind(t)
                if k in ("verb", "filter predicate", "keyword", "event", "quantity", "duration", "cost/counter",
                         "string"):
                    lost_cards[k] += 1
                    lost_examples[k].append(f"{r['name']}:{t}")
            kw_cut += any(t.startswith("Keyword.") for t in gone)
        print(f"\n## 5. Truncation ({label}): {len(over)} of {len(pop)} cards past {MAX_IR}; "
              f"{sum(cut.values())} tokens cut, by kind: " + ", ".join(f"{k} {v}" for k, v in cut.most_common()))
        print(f"  cards whose cut part holds a printed keyword (keywords come last): {kw_cut}")
        print("  components a card loses entirely (in the cut part only), by kind (card-component pairs): "
              + ", ".join(f"{k} {v}" for k, v in lost_cards.most_common()))
        for k in ("verb", "filter predicate", "event", "keyword"):
            if lost_examples[k]:
                print(f"    {k}: " + "; ".join(lost_examples[k][:14]))
        if label == "verified":
            print("  the longest: " + ", ".join(f"{r['set']} {r['name']} {len(r['tokens'])}"
                                              for r in sorted(over, key=lambda r: -len(r['tokens']))[:12]))

    # 6. names
    names = {r["name"] for r in rows}
    face_names = set()
    for r in rows:
        for part in r["name"].split(" // "):
            face_names.add(part)
    for label, pop in (("verified", ver), ("19 sets", allc)):
        name_tok = Counter()
        cards = Counter()
        for r in pop:
            toks = r["tokens"]
            kinds = set()
            if "@face_name" in toks:
                kinds.add("back face name (@face_name)")
            for i, t in enumerate(toks):
                if t.startswith("str:") and (t[4:] in names or t[4:] in face_names):
                    prev = toks[i - 2] if i >= 2 else ""
                    kinds.add("a card name in a filter or value" if prev != "@face_name" else "")
                    name_tok[t] += 1
            kinds.discard("")
            for k in kinds:
                cards[k] += 1
        print(f"\n## 6. Names inside component tokens ({label}): " + ", ".join(f"{k}: {v} cards" for k, v in cards.items())
              + f"; distinct card-name tokens {len(name_tok)}")
    # self references
    selfref = [r for r in ver if f"str:{r['name']}" in r["tokens"]]
    print(f"  verified cards naming themselves in a filter ('cards named ~'): {len(selfref)}: "
          + ", ".join(r["name"] for r in selfref))

    # 7. one value, two tokens
    for label, pop in (("verified", ver), ("19 sets", allc)):
        face_vals = Counter()
        str_vals = Counter()
        for r in pop:
            face_vals.update({t.split(":", 1)[1] for t in r["face"] if t.startswith(("type:", "sub:"))})
            str_vals.update({t[4:] for t in r["tokens"] if t.startswith("str:")})
        both = set(face_vals) & set(str_vals)
        cards_str = sum(1 for r in pop if any(t.startswith("str:") and t[4:] in both for t in r["tokens"]))
        print(f"\n## 7. One value, two tokens ({label}): {len(both)} type or subtype values are both a face "
              f"token (type:/sub:) and a filter value (str:); {cards_str} cards name one in a filter. "
              f"e.g. " + ", ".join(sorted(both)[:30]))
    spell_kind = sum(1 for r in ver if any(t.startswith("SpellKind.") for t in r["tokens"]))
    print(f"  SpellKind.X beside type:X: on {spell_kind} of {len(ver)} verified cards (a creature is "
          f"type:Creature and SpellKind.CREATURE)")

    # 8. abilities per card
    for label, pop in (("verified", ver), ("19 sets", allc)):
        n_ab = [sum(1 for k, _ in r["abilities"] if k == "ab" and _ != ["SpellAbility", "@kind"] and len(_) > 3)
                for r in pop]
        multi = sum(1 for n in n_ab if n >= 2)
        print(f"\n## 8. Ability structure ({label}): {multi} of {len(pop)} cards ({100 * multi / len(pop):.0f}%) "
              f"have two or more abilities beyond a bare spell kind; their tokens mix in one bag")


if __name__ == "__main__":
    main()
