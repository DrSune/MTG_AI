"""Reprint reuse and slot near-reuse, measured over the 19 ingested sets.

Run from the worktree root:  .venv/bin/python <this> OUT.json
"""
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path.cwd()
sys.path[:0] = [str(REPO), str(REPO / "tools" / "cards")]

import corpus  # noqa: E402

from MTG_bot.core.compiler import card_records  # noqa: E402
from MTG_bot.core.executor.games import compile_supply  # noqa: E402

HOME = ("M21", "M20", "FDN")
OTHER = tuple(s for s in corpus.SETS if s not in HOME)
out_path = Path(sys.argv[1])

t0 = time.time()
comp = {}
for code in corpus.SETS:
    comp[code] = corpus.compile_set(code)
    print(code, "compiled", round(time.time() - t0), "s", flush=True)

castable = {}
for code in corpus.SETS:
    try:
        sup = compile_supply("castable", code, require_verified=False, records={})
        castable[code] = set(sup.deckable)
    except Exception as exc:  # noqa: BLE001
        print(code, "castable failed", exc)
        castable[code] = set()
print("castable done", round(time.time() - t0), flush=True)

# Verified home cards: the record's stamp equals the current tree.
verified = {}  # oid -> dict(home, text_sha, tree_sha, has_ir, record)
for code in HOME:
    sc = comp[code]
    for oid, rec in sc.records.items():
        res = sc.results.get(oid)
        if res is None or not card_records.is_verified(res, rec):
            continue
        verified.setdefault(oid, {"home": code, "text_sha": card_records.text_sha(sc.raw[oid]),
                                  "tree_sha": rec["verified"]["tree_sha"], "has_ir": "ir" in rec,
                                  "ir": rec.get("ir"), "name": sc.raw[oid].identity.name,
                                  "date": rec["verified"].get("date")})
print("verified home cards", len(verified), Counter(v["home"] for v in verified.values()))

# ---------------------------------------------------------------- reprints
rep = defaultdict(Counter)
rep_cards = defaultdict(list)
for code in OTHER:
    sc = comp[code]
    for oid, raw in sc.raw.items():
        if raw.is_token or raw.is_emblem:
            continue
        rep[code]["cards"] += 1
        if oid in castable[code]:
            rep[code]["castable"] += 1
        v = verified.get(oid)
        if v is None:
            continue
        rep[code]["same_oracle_id"] += 1
        if card_records.text_sha(raw) != v["text_sha"]:
            rep[code]["text_differs"] += 1
            continue
        rep[code]["same_text"] += 1
        res = sc.results.get(oid)
        try:
            if v["has_ir"]:
                base = res.card if res is not None else corpus.printed_only(raw).card
                card = card_records.build_card(raw, base, v["ir"])
            else:
                if res is None:
                    rep[code]["refused_here"] += 1
                    continue
                card = res.card
            same = card_records.tree_sha(card) == v["tree_sha"]
        except Exception as exc:  # noqa: BLE001
            rep[code]["build_error"] += 1
            print("build error", code, raw.identity.name, exc)
            continue
        rep[code]["stamp_bytes_equal" if same else "stamp_bytes_differ"] += 1
        if same and oid in castable[code]:
            rep[code]["equal_and_castable_alone"] += 1
        if same and v["has_ir"]:
            rep[code]["equal_needs_home_ir"] += 1
        rep_cards[code].append((raw.identity.name, v["home"], same, v["has_ir"], oid in castable[code]))

tot = Counter()
for code in OTHER:
    tot.update(rep[code])
print("reprints per set:")
for code in OTHER:
    print(" ", code, dict(rep[code]))
print("TOTAL", dict(tot))

# distinct oracle ids covered
distinct = {oid for code in OTHER for oid, raw in comp[code].raw.items()
            if oid in verified and card_records.text_sha(raw) == verified[oid]["text_sha"]}
print("distinct verified oracle ids reprinted in other sets:", len(distinct))

# ---------------------------------------------------------------- slots
NUMW = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "a", "an")
COLW = ("white", "blue", "black", "red", "green", "colorless", "multicolored", "monocolored")
CARD_TYPES = ("artifact", "creature", "enchantment", "instant", "land", "planeswalker", "sorcery",
              "battle")
subtypes = set()
for code in corpus.SETS:
    for raw in comp[code].raw.values():
        tl = raw.type_line or ""
        if "—" in tl:
            for w in tl.split("—", 1)[1].split():
                subtypes.add(w.strip())
IRREG = {"Elf": "Elves", "Wolf": "Wolves", "Dwarf": "Dwarves", "Werewolf": "Werewolves",
         "Mouse": "Mice", "Ox": "Oxen", "Fungus": "Fungi"}
type_words = set()
for t in subtypes | {c.capitalize() for c in CARD_TYPES} | set(CARD_TYPES):
    type_words |= {t, t + "s", t + "es", IRREG.get(t, t)}
    type_words |= {t.lower(), (t + "s").lower(), IRREG.get(t, t).lower()}
type_words.discard("")
TYPE_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, type_words), key=len, reverse=True)) + r")\b")
NUM_RE = re.compile(r"\b(" + "|".join(NUMW) + r")\b", re.IGNORECASE)
COL_RE = re.compile(r"\b(" + "|".join(COLW) + r")\b", re.IGNORECASE)


def base_norm(s, raw):
    s = re.sub(r"\([^)]*\)", "", s).strip()
    name = raw.identity.name
    s = s.replace(name, "~")
    short = name.split(",")[0]
    if short != name and len(short) > 3:
        s = s.replace(short, "~")
    return re.sub(r"\s+", " ", s)


def slot_norm(s, raw):
    s = base_norm(s, raw)
    s = re.sub(r"\{[WUBRG]\}", "{C}", s)
    s = re.sub(r"\d+", "N", s)
    s = NUM_RE.sub("N", s)
    s = re.sub(r"\bN (\w+?)s\b", r"N \1", s)
    s = COL_RE.sub("COL", s)
    s = TYPE_RE.sub("T", s)
    return s


ver_exact = {}
ver_slot = {}
for oid, v in verified.items():
    sc = comp[v["home"]]
    raw = sc.raw[oid]
    for s in raw.sentences:
        b = base_norm(s, raw)
        if not b:
            continue
        ver_exact.setdefault(b, v["name"])
        ver_slot.setdefault(slot_norm(s, raw), v["name"])
print("verified sentences:", len(ver_exact), "exact shapes,", len(ver_slot), "slot shapes")

sent = Counter()
cardlvl = Counter()
examples = defaultdict(list)
unparsed_slot_shapes = Counter()
for code in OTHER:
    sc = comp[code]
    for oid, raw in sc.raw.items():
        if raw.is_token or raw.is_emblem:
            continue
        if oid in distinct:
            continue  # reprint-covered
        res = sc.results.get(oid)
        unparsed = {s for s, _ in res.unparsed} if res is not None else set(raw.sentences)
        sents = [s for s in raw.sentences if base_norm(s, raw)]
        if not sents:
            cardlvl["no_rules_text"] += 1
            continue
        cls = []
        for s in sents:
            parsed = s not in unparsed
            b, sl = base_norm(s, raw), slot_norm(s, raw)
            if b in ver_exact:
                k = "exact"
            elif sl in ver_slot:
                k = "slot"
                if len(examples["slot_unparsed" if not parsed else "slot_parsed"]) < 40:
                    examples["slot_unparsed" if not parsed else "slot_parsed"].append(
                        (code, raw.identity.name, s, ver_slot[sl]))
                if not parsed:
                    unparsed_slot_shapes[sl] += 1
            else:
                k = "none"
            sent[f"{k}:{'parsed' if parsed else 'unparsed'}"] += 1
            cls.append((k, parsed))
        cardlvl["cards"] += 1
        if all(k != "none" for k, _ in cls):
            cardlvl["all_sentences_exact_or_slot"] += 1
            if any(not p for _, p in cls):
                cardlvl["all_exact_or_slot_with_some_unparsed"] += 1
            if any(k == "slot" for k, _ in cls):
                cardlvl["all_exact_or_slot_with_some_slot"] += 1
        if all(k == "exact" for k, _ in cls):
            cardlvl["all_exact"] += 1
        if all(p for _, p in cls):
            cardlvl["fully_parsed"] += 1
        if any(not p for _, p in cls):
            cardlvl["some_unparsed"] += 1
            if all(k != "none" or p for k, p in cls):
                cardlvl["every_unparsed_sentence_has_a_verified_analog"] += 1
            if all(k == "slot" or p for k, p in cls) and any(k == "slot" and not p for k, p in cls):
                cardlvl["every_unparsed_sentence_is_a_slot_variant"] += 1
print("sentences (unverified, not reprint-covered, 16 sets):", dict(sent))
print("cards:", dict(cardlvl))
print("top unparsed slot shapes:")
for shp, n in unparsed_slot_shapes.most_common(25):
    print(f"  {n:4} {shp}")
json.dump({"reprints": {k: dict(v) for k, v in rep.items()}, "total": dict(tot),
           "distinct": len(distinct), "sentences": dict(sent), "cards": dict(cardlvl),
           "examples": examples, "rep_cards": rep_cards,
           "unparsed_slot_shapes": unparsed_slot_shapes.most_common(200)},
          out_path.open("w"), indent=1)
print("done", round(time.time() - t0), "s")
