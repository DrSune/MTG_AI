"""The census for completing M21, M20 and FDN (KNOWLEDGE/2026-11-17/209).

Run from the repository root (CPU only, gently; about 10 minutes):

    CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 nice -n 19 .venv/bin/python \
        reports/completion_2026-11-17/census.py reports/completion_2026-11-17

It writes ``worklist.json`` (one entry per unverified card of the three sets) and
``census.txt`` (the numbers the note quotes) into the directory given. Read-only: it compiles the
19 ingested sets with the card records applied (``tools/cards/corpus.py``), as ``cardtool status``
does, and changes no record.

What is computed, and what is judged:
- computed: each card's state, its sentences and their parse (template id, or UNPARSED with what
  the compiler's sentence layer makes of the sentence alone), a verified analog of each unparsed
  sentence (word for word, or with its number, colour and type words as slots: 207 §4), the
  nearest parsed sentence (``cardtool similar``), the printings of the same card in the other
  16 sets, the packages' reach in the other 16 sets (their patterns over unparsed sentences), the
  mapping batches and the totals per step;
- judged, in ``classes.py``: the need class of every card that is not a plain mapping, each
  package's missing piece, and the labels. A pattern hit on a card the table does not give that
  package is printed under "review", so a judgment that disagrees with the text shows.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path.cwd()
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(REPO), str(REPO / "tools" / "cards"), str(HERE)]

import classes
import corpus

from MTG_bot.core.compiler import card_records
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.frames import compose
from MTG_bot.core.executor.games import compile_supply

OUT = Path(sys.argv[1])
HOME = ("M21", "M20", "FDN")
OTHER = tuple(s for s in corpus.SETS if s not in HOME)
lines: list[str] = []


def say(text: str = "") -> None:
    lines.append(text)
    print(text, flush=True)


# ------------------------------------------------------------------ compile the 19 sets
comp = {code: corpus.compile_set(code) for code in corpus.SETS}
castable = {}
for code in corpus.SETS:
    try:
        castable[code] = set(compile_supply("castable", code, require_verified=False, records={}).deckable)
    except Exception:  # noqa: BLE001 - a set with too few mana sources deals no deck (M14)
        castable[code] = set()
registry = build_full_registry()


def state(sc: corpus.SetCompile, oid: str) -> str:  # cardtool._state
    rec = sc.records.get(oid, {})
    if "needs_atom" in rec:
        return "needs-atom"
    if oid in sc.refused:
        return "refused"
    res = sc.results[oid]
    if card_records.is_verified(res, rec):
        return "verified"
    if res.record is not None:
        return "mapped"
    if res.unparsed or res.back_face_unparsed or res.ambiguities:
        return "partly-compiled"
    return "compiled"


def unparsed_of(sc: corpus.SetCompile, oid: str) -> list[str]:
    raw, res = sc.raw[oid], sc.results.get(oid)
    if res is None:
        return list(raw.sentences) + (list(raw.back_face.sentences) if raw.back_face else [])
    return [s for s, _ in res.unparsed] + [s for s, _ in res.back_face_unparsed]


def alone(sentence: str) -> str:
    """What the compiler's sentence layer makes of the sentence alone (cardtool parse)."""
    m = list(registry.match(sentence))
    if m:
        return "template " + m[0].template.tid
    m = list(compose(sentence, registry))
    return "frame " + m[0].template.tid if m else "no parse"


cards = {code: {oid: raw for oid, raw in comp[code].raw.items() if not raw.is_token and not raw.is_emblem}
         for code in corpus.SETS}
states = {code: {oid: state(comp[code], oid) for oid in cards[code]} for code in corpus.SETS}

# ------------------------------------------------------------------ verified sentences (207 §4)
NUMW = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "a", "an")
COLW = ("white", "blue", "black", "red", "green", "colorless", "multicolored", "monocolored")
CARD_TYPES = ("artifact", "creature", "enchantment", "instant", "land", "planeswalker", "sorcery", "battle")
subtypes = {w.strip() for code in corpus.SETS for raw in cards[code].values()
            if "—" in (raw.type_line or "") for w in raw.type_line.split("—", 1)[1].split()}
IRREG = {"Elf": "Elves", "Wolf": "Wolves", "Dwarf": "Dwarves", "Werewolf": "Werewolves", "Mouse": "Mice",
         "Ox": "Oxen", "Fungus": "Fungi"}
type_words = set()
for t in subtypes | {c.capitalize() for c in CARD_TYPES} | set(CARD_TYPES):
    type_words |= {t, t + "s", t + "es", IRREG.get(t, t), t.lower(), (t + "s").lower(), IRREG.get(t, t).lower()}
type_words.discard("")
TYPE_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, type_words), key=len, reverse=True)) + r")\b")
NUM_RE = re.compile(r"\b(" + "|".join(NUMW) + r")\b", re.IGNORECASE)
COL_RE = re.compile(r"\b(" + "|".join(COLW) + r")\b", re.IGNORECASE)
SELF_RE = re.compile(r"\bthis (creature|enchantment|artifact|land|spell|Aura|Equipment|planeswalker)\b")


def base_norm(s: str, name: str) -> str:
    s = re.sub(r"\([^)]*\)", "", s).strip().replace(name, "~")
    short = name.split(",")[0]
    if short != name and len(short) > 3:
        s = s.replace(short, "~")
    return re.sub(r"\s+", " ", SELF_RE.sub("~", s))


def slot_norm(s: str, name: str) -> str:
    s = re.sub(r"\{[WUBRG]\}", "{C}", base_norm(s, name))
    s = NUM_RE.sub("N", re.sub(r"\d+", "N", s))
    s = re.sub(r"\bN (\w+?)s\b", r"N \1", s)
    return TYPE_RE.sub("T", COL_RE.sub("COL", s))


ver_exact: dict[str, str] = {}
ver_slot: dict[str, str] = {}
for code in corpus.SETS:
    sc = comp[code]
    for oid, st in states[code].items():
        if st != "verified":
            continue
        raw = sc.raw[oid]
        tag = f"{code} {raw.identity.name}" + (" (record)" if "ir" in sc.records.get(oid, {}) else "")
        for s in raw.sentences:
            if base_norm(s, raw.identity.name):
                ver_exact.setdefault(base_norm(s, raw.identity.name), tag)
                ver_slot.setdefault(slot_norm(s, raw.identity.name), tag)
exemplars = corpus.Exemplars.load()

# ------------------------------------------------------------------ the package patterns
PKG = classes.PACKAGES
for key in classes.CARDS:
    code, name = key.split("|", 1)
    if not any(r.identity.name == name for r in cards.get(code, {}).values()):
        raise SystemExit(f"classes.CARDS names no card: {key}")
for key, (_, pkgs, _) in classes.CARDS.items():
    unknown = [p for p in pkgs if p not in PKG]
    if unknown:
        raise SystemExit(f"{key}: unknown packages {unknown}")
PATTERNS = {pid: [re.compile(p, re.IGNORECASE) for p in spec[5]] for pid, spec in PKG.items()}


REMINDER = re.compile(r"\s*\([^)]*\)")


def pattern_hits(sentences: list[str]) -> set[str]:
    """The packages whose patterns match a sentence, reminder text left out."""
    core = [REMINDER.sub("", s) for s in sentences]
    return {pid for pid, pats in PATTERNS.items() for s in core if any(p.search(s) for p in pats)}


# ------------------------------------------------------------------ the three sets' rows
CLASS_NAMES = {"a": "blind verification only", "b": "a record from existing atoms",
               "c": "a new or generalised component", "d": "an engine or compiler fault",
               "e": "refusal or label"}


COMPONENT_RE = re.compile(r"Verb\.(\w+)|\b(\w+Event)\(|\b(StaticAbility|TriggeredAbility|ActivatedAbility|"
                          r"ReplacementAbility|Choose|Conditional|OptionalEffect|EachPlayer|DelayedTrigger|"
                          r"CostModifier|EtBState|TokenSpec|CostSacrifice|CostTap|CostDiscard|CostLife)\(")


def components(tree: str) -> list[str]:
    """The verbs, events and ability nodes a tree (rendered as Python) names."""
    return sorted({next(g for g in m if g) for m in COMPONENT_RE.findall(tree)})


def shape(raw, unp: list[str]) -> str:
    """The mapping batch a (b) card goes to, by its hardest unparsed construct."""
    text = " ".join(unp)
    if "Planeswalker" in raw.types:
        return "planeswalkers and legends with several abilities"
    if any(s.startswith(("Choose one", "•")) or "choose one —" in s for s in unp):
        return "modal spells and modal triggers"
    if "Instant" in raw.types or "Sorcery" in raw.types:
        return "instants and sorceries"
    if any(re.match(r"^(\{|\[|Sacrifice|Tap|Exile|Discard|Remove|Pay)[^:\"]*:", s) for s in unp):
        return "activated abilities"
    if any(re.match(r"^(\w+ — )?When (this|~|[A-Z])[^,]* (enters|dies)", s) for s in unp):
        return "enters and dies triggers"
    if any(re.match(r"^(\w+( \w+)? — )?(When|Whenever|At)\b", s) for s in unp):
        return "other triggers"
    if re.search(r"create", text, re.IGNORECASE):
        return "other triggers"
    return "statics: anthems, Auras, Equipment, conditions, costs"


rows = []
for code in HOME:
    sc = comp[code]
    for oid, raw in sorted(cards[code].items(), key=lambda kv: kv[1].identity.name):
        st = states[code][oid]
        if st == "verified":
            continue
        name = raw.identity.name
        key = f"{code}|{name}"
        res = sc.results.get(oid)
        unp = unparsed_of(sc, oid)
        sent_rows = []
        for s in raw.sentences + (raw.back_face.sentences if raw.back_face else ()):
            row = {"sentence": s}
            if s in unp:
                row["parse"] = "UNPARSED"
                row["alone"] = alone(s)
                b, sl = base_norm(s, name), slot_norm(s, name)
                if b in ver_exact:
                    row["verified_analog"] = "word for word: " + ver_exact[b]
                elif sl in ver_slot:
                    row["verified_analog"] = "by slot: " + ver_slot[sl]
                near = exemplars.search(s, 1, name=name)
                if near:
                    score, ex = near[0]
                    row["nearest"] = f"{score:.2f} {ex['tid']} ({ex['set']} {ex['card']}): {ex['sentence']}"
                    row["nearest_components"] = components(ex["tree"])
            else:
                row["parse"] = corpus.sentence_status(raw, res, s, registry) if res else "card refused"
            sent_rows.append(row)
        need, pkgs, note = classes.CARDS.get(key, ("b", [], ""))
        if need == "b" and st in ("compiled", "mapped") and key not in classes.CARDS:
            need = "a"
        hits = pattern_hits(unp)
        review = sorted(hits - set(pkgs))
        same_text = sorted(f"{o} ({states[o][oid]})" for o in OTHER if oid in cards[o]
                           and card_records.text_sha(cards[o][oid]) == card_records.text_sha(raw))
        same_card = sorted(o for o in OTHER if oid in cards[o])
        rows.append({
            "set": code, "name": name, "oracle_id": oid, "state": st, "castable": oid in castable[code],
            "type": raw.type_line, "need": need, "need_text": CLASS_NAMES[need],
            "packages": [p for p in pkgs if PKG[p][0] != "r"], "rulings": [p for p in pkgs if PKG[p][0] == "r"],
            "batch": None, "shape": shape(raw, unp) if need == "b" else None,
            "notes": note, "label": classes.LABELS.get(key, (None, None))[1],
            "needs_atom_note": sc.records.get(oid, {}).get("needs_atom", {}).get("missing"),
            "refused_by_compiler": sc.refused.get(oid), "known_gaps": list(res.known_gaps) if res else [],
            "sentences": sent_rows, "unparsed": len(unp), "review_pattern_hits": review,
            "printings_elsewhere": same_card, "same_text_elsewhere": same_text,
        })

# ------------------------------------------------------------------ the mapping batches
# The (b) cards in a fixed order of shapes, cut into consecutive batches of 20-30 (207: 24 cards a
# mapper, about 40 minutes), so a batch holds one shape or two neighbouring ones.
order_shapes = ["modal spells and modal triggers", "instants and sorceries", "enters and dies triggers",
                "other triggers", "statics: anthems, Auras, Equipment, conditions, costs",
                "activated abilities", "planeswalkers and legends with several abilities"]
b_sorted = sorted((r for r in rows if r["need"] == "b"),
                  key=lambda r: (order_shapes.index(r["shape"]), r["set"], r["name"]))
n_batches = max(1, round(len(b_sorted) / 24))
size, extra = divmod(len(b_sorted), n_batches)
batches: dict[str, list[dict]] = {}
pos = 0
for i in range(n_batches):
    take = size + (1 if i < extra else 0)
    batches[f"M{i + 1}"] = b_sorted[pos:pos + take]
    pos += take
for bid, part in batches.items():
    for r in part:
        r["batch"] = bid
for r in rows:
    if r["need"] in ("c", "d"):
        r["batch"] = "+".join(r["packages"])
    elif r["need"] == "a":
        r["batch"] = "V0"

# ------------------------------------------------------------------ reach in the other 16 sets
other_rows = []
for code in OTHER:
    sc = comp[code]
    for oid, raw in cards[code].items():
        st = states[code][oid]
        if st == "verified":
            continue
        unp = unparsed_of(sc, oid)
        other_rows.append({"set": code, "name": raw.identity.name, "oid": oid, "state": st,
                           "castable": oid in castable[code], "unparsed": unp, "hits": pattern_hits(unp)})

home_need: dict[str, list[dict]] = defaultdict(list)
for r in rows:
    for p in r["packages"] + r["rulings"]:
        home_need[p].append(r)
pkg_rows = []
for pid, (kind, title, cr, near, build, _pats) in PKG.items():
    need = home_need.get(pid, [])
    only = [r for r in need if r["packages"] == [pid] or (kind == "r" and not r["packages"])]
    touched = [o for o in other_rows if pid in o["hits"]]
    other_only = [o for o in touched if o["hits"] - {p for p in o["hits"] if PKG[p][0] == "r"} <= {pid}]
    other_whole = [o for o in touched if all(any(p.search(REMINDER.sub("", s)) for p in PATTERNS[pid])
                                             for s in o["unparsed"] if REMINDER.sub("", s))]
    pkg_rows.append({
        "id": pid, "kind": kind, "title": title, "cr": cr, "nearest_atoms": near, "build": build,
        "gate_round": kind == "c",
        "here_needing": len(need), "here_only": len(only),
        "here_cards": sorted(f"{r['set']} {r['name']}" for r in need),
        "other16_touched": len(touched), "other16_touched_names": len({o["name"] for o in touched}),
        "other16_only": len(other_only), "other16_whole": len(other_whole),
        "other16_examples": sorted({f"{o['set']} {o['name']}" for o in other_only})[:12],
        "reach": len(only) + len(other_only),
        "low_use": len(need) + len(touched) <= 2,
    })
pkg_rows.sort(key=lambda p: (-p["reach"], -p["here_needing"], p["id"]))

# ------------------------------------------------------------------ the order of work
# First-pass yields, from 207: a mapped card ends needs-atom or WRONG about 15% of the time even
# after this census (M20's wave without one: 35% needs-atom; blind review since 11-05: 5% WRONG);
# a card on a landed package 10%; a compiled card 5%.
RATE = {"a": 0.95, "b": 0.85, "c": 0.90, "d": 0.90}
MIN_LANE, MIN_GATE, MIN_G3, MIN_MAP, MIN_REVIEW = 118, 40, 20, 1.75, 1.1  # 207 §4, agent-minutes
step_of_pkg = {p: step[0] for step in classes.ORDER for p in step[3]}
unplaced = [p for p in PKG if p not in step_of_pkg]
if unplaced:
    raise SystemExit(f"classes.ORDER lands no step for {unplaced}")
step_index = {step[0]: i for i, step in enumerate(classes.ORDER)}
for r in rows:
    if r["need"] == "a":
        r["completes_at"] = "A0"
    elif r["need"] == "b":
        r["completes_at"] = next(step[0] for step in classes.ORDER if r["batch"] in step[4])
    else:
        r["completes_at"] = max((step_of_pkg[p] for p in r["packages"] + r["rulings"]), key=step_index.get)
plan_rows = []
upper = {code: Counter(states[code].values())["verified"] for code in HOME}
expected = {code: float(n) for code, n in upper.items()}
unlocked: set[tuple[str, str]] = set()
for sid, track, title, pkgs, groups, lanes, beside, conflicts in classes.ORDER:
    done = [r for r in rows if r["completes_at"] == sid]
    for r in done:
        upper[r["set"]] += 1
        expected[r["set"]] += RATE[r["need"]]
    n = len(done)
    if track == "A":
        minutes = 30 if not groups else (MIN_REVIEW * n if groups == ["a"] else (MIN_MAP + MIN_REVIEW) * n)
    else:
        minutes = lanes * MIN_LANE + (MIN_GATE + MIN_G3 if track == "B" else 0) + (MIN_MAP + MIN_REVIEW) * n
    landed = {q for q in step_of_pkg if step_index[step_of_pkg[q]] <= step_index[sid]}
    unlocked |= {(o["set"], o["name"]) for o in other_rows
                 if o["hits"] & set(pkgs) and o["hits"] - {q for q in o["hits"] if PKG[q][0] == "r"} <= landed}
    plan_rows.append({"step": sid, "track": track, "title": title, "packages": pkgs, "batches": groups,
                      "lanes": lanes, "runs_beside": beside, "conflicts": conflicts, "cards_completed": n,
                      "per_set": dict(Counter(r["set"] for r in done)), "agent_minutes": round(minutes),
                      "gate_round": track == "B",
                      "verified_after_all_pass": dict(upper),
                      "verified_after_expected": {k: round(v) for k, v in expected.items()},
                      "other16_unlocked_so_far": len(unlocked)})

# ------------------------------------------------------------------ write the worklist
worklist = [{k: r[k] for k in ("set", "name", "oracle_id", "state", "castable", "need", "packages", "rulings",
                               "batch", "completes_at", "shape", "notes", "label", "needs_atom_note",
                               "refused_by_compiler", "known_gaps", "unparsed", "sentences",
                               "review_pattern_hits", "printings_elsewhere", "same_text_elsewhere")} for r in rows]
(OUT / "worklist.json").write_text(json.dumps({"cards": worklist, "packages": pkg_rows, "order": plan_rows,
                                               "batches": {b: [f"{r['set']} {r['name']}" for r in part]
                                                           for b, part in batches.items()}},
                                              indent=1, ensure_ascii=False) + "\n")

# ------------------------------------------------------------------ the census in numbers
say("# Census: completing M21, M20 and FDN (2026-11-17)")
say()
say("## 1. Per set: the cards by state, and the unverified ones by need class")
for code in HOME:
    st = Counter(states[code].values())
    need = Counter(r["need"] for r in rows if r["set"] == code)
    say(f"{code}: {len(states[code])} cards: " + ", ".join(f"{k} {v}" for k, v in st.most_common()))
    say(f"    unverified {sum(need.values())}: " + ", ".join(f"({k}) {need[k]}" for k in "abcde" if need[k]))
need_all = Counter(r["need"] for r in rows)
say(f"all three: unverified {len(rows)}: " + ", ".join(f"({k}) {need_all[k]}" for k in "abcde" if need_all[k]))
say(f"  ... castable today among them: {sum(r['castable'] for r in rows)}")
say(f"  ... with a ruling: {sum(bool(r['rulings']) for r in rows)} cards; with a label: "
    f"{sum(bool(r['label']) for r in rows)}")
unp = [s for r in rows for s in r["sentences"] if s["parse"] == "UNPARSED"]
say(f"unparsed sentences: {len(unp)}; parse alone: {sum(not s['alone'].startswith('no parse') for s in unp)}; "
    f"verified analog word for word {sum(s.get('verified_analog', '').startswith('word') for s in unp)}, "
    f"by slot {sum(s.get('verified_analog', '').startswith('by slot') for s in unp)}")
b_rows = [r for r in rows if r["need"] == "b"]
b_unp = [s for r in b_rows for s in r["sentences"] if s["parse"] == "UNPARSED"]
say(f"(b) cards: {len(b_rows)}, {len(b_unp)} unparsed sentences, of which a verified analog: "
    f"{sum('verified_analog' in s for s in b_unp)}; cards whose every unparsed sentence has one: "
    f"{sum(all('verified_analog' in s for s in r['sentences'] if s['parse'] == 'UNPARSED') for r in b_rows)}")
say(f"multi-package cards (c/d): {sum(len(r['packages']) > 1 for r in rows if r['need'] in 'cd')}")
reprint_reach = sum(len(r["same_text_elsewhere"]) for r in rows)
say(f"printings of these cards in the other 16 sets with the same printed text (reprint stamps once "
    f"verified): {reprint_reach}, of {sum(len(r['printings_elsewhere']) for r in rows)} printings")

say()
say("## 2. Packages ((c) a gate round; (d) an engine wave; (r) a ruling), by reach")
say("reach = cards here that need only it + printings of the other 16 sets where it is the only "
    "piece the patterns detect")
say(f"{'id':<17} {'kind':<4} {'here':>4} {'only':>4} {'o16 touch':>9} {'o16 only':>8} {'o16 whole':>9} {'reach':>5}  low-use")
for p in pkg_rows:
    say(f"{p['id']:<17} {p['kind']:<4} {p['here_needing']:>4} {p['here_only']:>4} {p['other16_touched']:>9} "
        f"{p['other16_only']:>8} {p['other16_whole']:>9} {p['reach']:>5}  {'LOW' if p['low_use'] else ''}")
say()
for p in pkg_rows:
    say(f"[{p['id']}] ({p['kind']}) {p['title']}. CR {p['cr']}. Nearest: {p['nearest_atoms']}. "
        f"Build: {p['build']}.")
    say(f"    here: {', '.join(p['here_cards']) or '-'}")
    if p["other16_examples"]:
        say(f"    other 16 (only this piece): {', '.join(p['other16_examples'])}"
            + (" ..." if p["other16_only"] > len(p["other16_examples"]) else ""))

say()
say("## 3. Mapping batches ((b) cards), with 207's rates (mapping 1.75, blind review about 1.1 with "
    "G3 follow-ups, agent-minutes per card)")
for bid, part in batches.items():
    shp = "; ".join(f"{k} {v}" for k, v in Counter(r["shape"] for r in part).most_common())
    per_set = Counter(r["set"] for r in part)
    rul = Counter(x for r in part for x in r["rulings"])
    analog = sum(all("verified_analog" in s for s in r["sentences"] if s["parse"] == "UNPARSED") for r in part)
    risky = sum(bool(r["notes"]) for r in part)
    say(f"{bid}: {len(part)} cards ({', '.join(f'{k} {v}' for k, v in per_set.items())}): {shp}; "
        f"mapping {MIN_MAP * len(part):.0f} min, review {MIN_REVIEW * len(part):.0f} min"
        + (f"; rulings {dict(rul)}" if rul else "") + f"; every unparsed sentence with a verified analog: "
        f"{analog}; with a note (risk, ruling, carrier): {risky}")
    say("    " + ", ".join(r["name"] for r in part))
    reuse = Counter(c for r in part for s in r["sentences"] for c in s.get("nearest_components", []))
    say("    components the nearest parsed sentences use (what the batch reuses): "
        + ", ".join(f"{c} {n}" for c, n in reuse.most_common(14)))
covered = [r for r in rows if r["need"] == "b"
           and all("verified_analog" in s for s in r["sentences"] if s["parse"] == "UNPARSED")]
say(f"(b) cards whose every unparsed sentence has a verified analog ({len(covered)}): "
    + ", ".join(f"{r['set']} {r['name']}" for r in covered))

say()
say("## 4. Blind verification only ((a))")
for r in rows:
    if r["need"] == "a":
        say(f"  {r['set']} {r['name']} [{r['state']}]: {r['notes']}")

say()
say("## 5. Labels")
for key, (scope, why) in classes.LABELS.items():
    say(f"  {key.replace('|', ' ')} ({scope}): {why}")

say()
say("## 6. Order of work (A: cards, no code; B: gate rounds, one merge each; C: engine wave)")
say(f"{'step':<4} {'tr':<2} {'lanes':>5} {'cards':>5} {'agent-min':>9}  verified after it (all pass / expected)"
    f"   other-16 printings unlocked")
for pr in plan_rows:
    up, ex = pr["verified_after_all_pass"], pr["verified_after_expected"]
    say(f"{pr['step']:<4} {pr['track']:<2} {pr['lanes']:>5} {pr['cards_completed']:>5} {pr['agent_minutes']:>9}  "
        f"M21 {up['M21']}/{ex['M21']}  M20 {up['M20']}/{ex['M20']}  FDN {up['FDN']}/{ex['FDN']}"
        f"{pr['other16_unlocked_so_far']:>8}")
for pr in plan_rows:
    say(f"  {pr['step']}: {pr['title']}. Beside: {pr['runs_beside']}. Conflicts: {pr['conflicts']}. "
        f"Completes: {pr['per_set'] or '-'}")
tot_bc = sum(pr["agent_minutes"] for pr in plan_rows if pr["track"] in "BC")
n_bc = sum(pr["cards_completed"] for pr in plan_rows if pr["track"] in "BC")
say(f"agent-minutes: A {sum(pr['agent_minutes'] for pr in plan_rows if pr['track'] == 'A')}, "
    f"B and C {tot_bc} for {n_bc} cards ({tot_bc / max(n_bc, 1):.0f} a card; 207's tail: about 49)")
say(f"gate rounds: {sum(pr['gate_round'] for pr in plan_rows)}")

say()
say("## 7. Review: pattern hits the table does not assign (each checked by hand in 209)")
for r in rows:
    if r["review_pattern_hits"]:
        say(f"  {r['set']} {r['name']} [{r['need']}]: {', '.join(r['review_pattern_hits'])}")

(OUT / "census.txt").write_text("\n".join(lines) + "\n")
