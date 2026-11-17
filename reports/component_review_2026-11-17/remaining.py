"""Measure 5: the unverified cards of M21, M20 and FDN, and what their unparsed sentences need.

    .venv/bin/python reports/component_review_2026-11-17/remaining.py > reports/component_review_2026-11-17/remaining.txt

Every unparsed sentence (front and back faces; records applied) is classed by a hand-written
lexicon (``RULES``, first match wins; the reviewer's reading, from the needs-atom notes and the
IR's vocabulary, ability_tree.py):
- T: existing components suffice; what is missing is a template (or a mapper's record);
- P: an existing component plus a parameter (an enum value, a role, a slot), named;
- E: the IR can say it, the engine has no lane for it, named;
- N: a new component (a verb, predicate, event, quantity, node or zone), named;
- -: nothing to encode (a deck-building rule).
A sentence no rule matches is T by default; the default bucket is printed in full for review.
Then per card: whole with templates alone, with parameters, with engine lanes, or waiting on a new
component; and the pieces ranked by the cards each one completes (greedy, every card's other
sentences assumed handled by T).
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

# (pattern, class, piece). Matched case-insensitively on the sentence, first match wins.
RULES: tuple[tuple[str, str, str], ...] = (
    (r"a deck can have any number", "-", "deck-building rule"),
    (r"opening hand", "N", "pregame action from the opening hand (CR 103.6)"),
    (r"choose new targets for the cop|\bcopy (that|it|this)\b|\bcopies of\b|a copy of|becomes a copy|copy it for each|copy that (spell|ability)",
     "N", "COPY: of a spell or ability, a token copy, become a copy (Verb.COPY has no handler)"),
    (r"^flashback|gains flashback|flashback cost", "N", "flashback (alternative cost from a graveyard + exile replacement)"),
    (r"rather than pay th\w+ \w+'s mana cost|by removing .* counters from among|you may pay .* rather than pay",
     "N", "alternative cost (CR 118.9)"),
    (r"sacrifice a \w+ or pay \{", "N", "a choice between additional costs"),
    (r"^ward|, ward\b|ward—", "P", "WARD: TargetingEvent trigger + COUNTER_SPELL unless (a Keyword.WARD with a cost)"),
    (r"changeling|all creature types|every creature type", "P", "GRANT_TYPE of every creature type"),
    (r"additional combat phase", "N", "an extra combat phase (EXTRA_TURN's sibling)"),
    (r"as though (it|they) had flash", "P", "POLICY scope: cast timing (F9)"),
    (r"you may play (that|them|those|this)|may play a land and cast|play them this turn|cast any number of .* from among those",
     "N", "a play permission with a duration for exiled or revealed cards (impulse)"),
    (r"you may cast (target|\w+ \w+ card|.*from your graveyard this turn)", "N",
     "a play permission with a duration for exiled or revealed cards (impulse)"),
    (r"surveil", "P", "SCRY with the graveyard as its other pile (surveil, CR 701.25)"),
    (r"different (names|mana values?|mana costs?)", "P", "a distinct-value count (QDistinctColorCount over a property)"),
    (r"for as long as you control", "P", "a duration that ends when control of the source is lost"),
    (r"milled this way|put into a graveyard this way", "E", "the mill lane writes no result register"),
    (r"any number of target", "P", "TARGET with an unbounded count"),
    (r"toughness (less|greater|\w+ or (greater|less))|with toughness", "P",
     "a property comparison (toughness, or against another object's value)"),
    (r"total power", "P", "a comparison over a quantity (total power)"),
    (r"causes a triggered ability", "P", "AbilityTriggerEvent with a cause filter"),
    (r"the sacrificed \w+'s", "P", "a referent for the object a cost took"),
    (r"life lost this way", "P", "the amount the previous step did"),
    (r"if you return .* this way", "P", "a filtered count of the result, by last known information"),
    (r"from your hand without paying", "P", "a cast permission with the mana cost waived (CostDeltaWaiveMana)"),
    (r"at the beginning of the next end step", "E", "a delayed trigger bound to the objects it names"),
    (r"double that damage|twice that many", "P", "a replacement that doubles the event's amount"),
    (r"can't gain life|can't cast more than|can't enter the battlefield|can't cast \w+ from", "E",
     "a standing prohibition on an event (PREVENT_EFFECT lanes for life, casts, entering)"),
    (r"unless (they|that player) (discard|sacrifice)|any opponent may sacrifice|if a player does", "N",
     "a choice made by the affected player (punisher)"),
    (r"their choice of the top or bottom", "P", "Choose with a chooser (the owner)"),
    (r"piles?\b", "N", "piles (separate, then an opponent picks)"),
    (r"life total become", "N", "SET_LIFE"),
    (r"color or colors of your choice", "N", "SET_COLOR"),
    (r"combat damage equal to its toughness", "P", "DAMAGE_ASSIGN_POLICY scope: toughness"),
    (r"able to block .* do so", "P", "MANDATE_BLOCK scope: lure"),
    (r"attack or block alone", "N", "a declaration-level restriction (alone)"),
    (r"outside the game", "N", "an outside-the-game zone"),
    (r"distribute|divided as you choose", "P", "division of an amount among targets (CR 601.2d)"),
    (r"change the target", "N", "CHANGE_TARGET"),
    (r"no maximum hand size", "N", "hand-size rule"),
    (r"can't lose the game|win the game", "N", "game result: win, can't lose"),
    (r"poison counter", "P", "PUT_COUNTER on a player, CounterKind POISON"),
    (r"stun counter", "P", "CounterKind STUN (an untap replaced)"),
    (r"don't lose this mana", "N", "mana kept between steps"),
    (r"triggers only once each turn", "N", "a once-each-turn limit on a trigger"),
    (r"second time this ability has resolved", "N", "an ability's resolutions this turn"),
    (r"hasn't been chosen", "N", "a menu that remembers its picks"),
    (r"activate only once", "P", "AbilityActivatedEvent naming the ability (EVENT_THIS_TURN)"),
    (r"with the same name as|named ~|all cards with that name", "P", "NAME_EQ with a referent slot (the same name as)"),
    (r"you don't own", "P", "an owner predicate beside CONTROLLER_IS"),
    (r"becomes the target of a spell|that targets (you|a creature)|if it targets", "P",
     "a targets(filter) predicate (TARGETS_SOURCE generalised)"),
    (r"you and/or at least one permanent you control becomes the target", "P",
     "a targets(filter) predicate (TARGETS_SOURCE generalised)"),
    (r"tap a \w+ for mana|that mana is spent|if that mana is spent", "N", "a mana event (tapped for mana, mana spent on)"),
    (r"spend this mana only to cast .* or activate|spend mana of any type", "P", "MANA_POLICY use and scope"),
    (r"loses all (other )?(card types and )?abilities", "P", "LOSE_ABILITY of every ability"),
    (r"excess damage", "P", "a quantity field: the excess damage"),
    (r"it's attacking", "P", "a referent: the player or planeswalker attacked"),
    (r"tapped and attacking", "P", "MOVE_ZONE onto the battlefield attacking"),
    (r"(return|put) .* battlefield .* with (a|an|\w+) \+1/\+1 counters? on it", "P", "MOVE_ZONE with entering counters"),
    (r"exactly \w+ life", "P", "LIFE_TOTAL_GE about another player"),
    (r"starting life total", "P", "a starting-life quantity (ledger F11)"),
    (r"controlled by different players|choose two target players|each of them searches", "N",
     "a designation across several players"),
    (r"look at the top card of your library any time", "N", "a standing look at your library's top card"),
    (r"you may reveal an angel card, a demon card", "N", "per-category picks from one look"),
    (r"chooses a \w+ they control of each permanent type", "N", "a choice per type, then the rest"),
    (r"causes you to discard", "N", "a discard replacement keyed on its cause"),
    (r"whenever you discard", "N", "DiscardEvent (B-48)"),
    (r"each kind of counter", "P", "PUT_COUNTER over every counter kind present"),
    (r"draw step", "P", "Phase.DRAW (a draw-step trigger)"),
    (r"for the first time each turn", "P", "an ordinal on DeclareAttackersEvent"),
    (r"each \w+ you control enters with an additional", "P", "an entering-counter replacement for other permanents"),
    (r"until end of turn, you don't lose", "N", "mana kept between steps"),
    (r"mana of the chosen color", "P", "ADD_MANA reading a chosen colour"),
    (r"is the chosen type", "P", "GRANT_TYPE reading a chosen creature type"),
    (r"choose any \w+ name|with the chosen name", "P", "the chosen-name read on activated abilities"),
    (r"was dealt combat damage by this", "P", "EVENT_THIS_TURN over the object's controller"),
    (r"if you cast it\b|if you cast it from your hand", "P", "an enters condition: cast (from a zone)"),
    (r"revival counter|divinity counter|incubation counter|wish counter|bait counter", "P", "a CounterKind value"),
    (r"named [A-Z]", "T", "a named card (NAME_EQ)"),
)
_COMPILED = tuple((re.compile(p, re.IGNORECASE), c, piece) for p, c, piece in RULES)


def classify(sentence: str, name: str) -> tuple[str, str]:
    s = C.norm_sentence(sentence, name)
    for pat, cls, piece in _COMPILED:
        if pat.search(s):
            return cls, piece
    return "T", "template only"


ORDER = {"-": 0, "T": 1, "P": 2, "E": 3, "N": 4}


def main() -> None:
    rows = C.load()
    rem = [r for r in rows if r["set"] in C.HOME and r["state"] != "verified"]
    print("# The unverified cards of M21, M20 and FDN: what their unparsed sentences need")
    print("cards by state: " + ", ".join(f"{s} {n}" for s, n in Counter(f"{r['set']} {r['state']}" for r in rem).most_common()))
    sent_cls = Counter()
    piece_sents = Counter()
    piece_cards = defaultdict(set)
    card_need = {}
    default_bucket = []
    for r in rem:
        uns = [s for s, _ in (r.get("unparsed") or []) + (r.get("back_unparsed") or [])]
        needs = []
        for s in uns:
            cls, piece = classify(s, r["name"])
            sent_cls[cls] += 1
            if cls in "PEN":
                piece_sents[(cls, piece)] += 1
                piece_cards[(cls, piece)].add(r["oid"])
            if piece == "template only":
                default_bucket.append(f"{r['set']} {r['name']}: {s}")
            needs.append((cls, piece))
        worst = max((ORDER[c] for c, _ in needs), default=1)
        card_need[r["oid"]] = (r, worst, {p for c, p in needs if c in "PEN"}, len(uns))
    n_s = sum(sent_cls.values())
    print(f"\nunparsed sentences: {n_s} on {sum(1 for v in card_need.values() if v[3])} cards "
          f"({sum(1 for v in card_need.values() if not v[3])} cards have none: compiled whole or refused or mapped)")
    for cls, label in (("T", "existing components, a template is missing"), ("P", "existing component + a parameter"),
                       ("E", "the IR has the shape, the engine has no lane"), ("N", "a new component"),
                       ("-", "nothing to encode")):
        print(f"  {cls} {label}: {sent_cls[cls]} ({100 * sent_cls[cls] / n_s:.0f}%)")
    inv = {v: k for k, v in ORDER.items()}
    per = Counter(inv[w] for _, w, _, _ in card_need.values())
    print("\ncards by what their worst sentence needs (a card with no unparsed sentence counts as T):")
    for cls in ("-", "T", "P", "E", "N"):
        print(f"  {cls}: {per[cls]}")
    by_state = defaultdict(Counter)
    for r, w, _, _ in card_need.values():
        by_state[f"{r['set']} {r['state']}"][inv[w]] += 1
    for k, c in sorted(by_state.items()):
        print(f"    {k}: " + ", ".join(f"{x} {c[x]}" for x in ("T", "P", "E", "N") if c[x]))

    print("\n## The pieces, by the cards waiting on each (sentences in brackets)")
    for (cls, piece), cards in sorted(piece_cards.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        names = sorted(f"{card_need[o][0]['set']} {card_need[o][0]['name']}" for o in cards)
        print(f"  {cls} {len(cards):3d} [{piece_sents[(cls, piece)]:3d}] {piece}: " + "; ".join(names[:8])
              + (" ..." if len(names) > 8 else ""))

    # greedy: which pieces complete the most cards (every T sentence assumed done)
    print("\n## Greedy cover: pieces in the order that completes the most cards (T sentences assumed done)")
    open_cards = {o: set(p) for o, (_, _, p, _) in card_need.items() if p}
    done = sum(1 for o, (_, _, p, _) in card_need.items() if not p)
    print(f"  with templates only: {done} cards whole")
    have = set()
    step = 0
    while open_cards and step < 40:
        gains = Counter()
        for o, need in open_cards.items():
            missing = need - have
            if len(missing) == 1:
                gains[next(iter(missing))] += 1
        if not gains:
            # take the piece most cards still need
            for o, need in open_cards.items():
                for p in need - have:
                    gains[p] += 0.001
        piece, g = gains.most_common(1)[0]
        have.add(piece)
        closed = [o for o, need in open_cards.items() if need <= have]
        for o in closed:
            del open_cards[o]
        done += len(closed)
        step += 1
        cls = next(c for (c, p) in piece_cards if p == piece)
        print(f"  {step:2d}. +{len(closed):3d} -> {done:3d}  {cls} {piece}")
    print(f"  still open: {len(open_cards)}")

    # by class: every P piece, then every E piece, then the N pieces by cards waiting
    print("\n## By class: every parameter, then every engine lane, then the new components by cards waiting")
    pieces_of = {cls: {p for (c, p) in piece_cards if c == cls} for cls in "PEN"}
    print("  distinct pieces: " + ", ".join(f"{c} {len(pieces_of[c])}" for c in "PEN"))
    need = {o: p for o, (_, _, p, _) in card_need.items()}
    have = set()
    whole = sum(1 for p in need.values() if not p)
    print(f"  templates only: {whole} of {len(need)} cards whole")
    for cls in "PE":
        have |= pieces_of[cls]
        whole = sum(1 for p in need.values() if p <= have)
        print(f"  + every {cls} piece ({len(pieces_of[cls])}): {whole} whole")
    n_sorted = sorted(pieces_of["N"], key=lambda p: -len(piece_cards[("N", p)]))
    for k, p in enumerate(n_sorted, 1):
        have.add(p)
        whole = sum(1 for q in need.values() if q <= have)
        if k <= 6 or k == len(n_sorted):
            print(f"  + N piece {k} ({p[:60]}): {whole} whole")

    print("\n## The default bucket (no rule matched: read as T, existing components) for review")
    for line in default_bucket:
        print("  " + line[:220])


if __name__ == "__main__":
    main()
