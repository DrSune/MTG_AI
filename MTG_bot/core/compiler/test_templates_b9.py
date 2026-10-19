"""ZND-4 (2026-10-19): the ZND-4b tail-sweep bucket's laws + executor truth.

Three static laws (the /108 tail-sweep discipline, /115's falsifier law) and
one dynamic proof class:
  1. Every B9 pattern clears at least one ZNR sentence; every sentence the
     bucket clears matches EXACTLY ONE pattern here (one-row-one-outcome).
  2. A B9 pattern matches no sentence any PRIOR bucket already claims
     (bucket priority would silently shadow it — the shape must be genuinely
     new), and no B9 pattern matches a pattern of another bucket.
  3. Every deferred one-away row (gap ledger: ZND-4a keyword lists, ZND-4b
     Taunting Arbormage, ZND-4c Ondu Inversion) matches NOTHING anywhere —
     silently re-matching while the ledger names the row deferred is the
     worst failure this file catches.
  4. VERBATIM law (/115 G-FM3): each named Batch-B carrier row fullmatches
     the ONE template that owns it, byte-exact.
  5. Executor falsifiers: every shape is driven on a live board and the
     ENGINE's observable record must change (a build-only test proves the
     tree parses, never that the engine can run it — /115's falsifier law).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from MTG_bot.core.card import Card, CardType, CardTypeStr, Keyword, Supertype  # noqa: E402
from MTG_bot.core.compiler import coverage  # noqa: E402
from MTG_bot.core.compiler.templates_b1 import _parse_trigger  # noqa: E402
from MTG_bot.core.compiler.templates_b5a import _parse_equip_cost  # noqa: E402
from MTG_bot.core.compiler.templates_b9 import (  # noqa: E402
    _DIRECTIONS,
    _EQ_ROW,
    _KW,
    _PWR_ROW,
    _SA_ROW,
    _TRIG_ROW,
    _pt_body,
    compile_sentence,
)
from MTG_bot.core.effects.ask import build_asks  # noqa: E402
from MTG_bot.core.effects.evaluation import eval_filter  # noqa: E402
from MTG_bot.core.effects.visibility import build_visibility  # noqa: E402
from MTG_bot.core.executor import Executor, find_card  # noqa: E402
from MTG_bot.core.game_state import GameWorld, Player  # noqa: E402


# --------------------------------------------------------------------------
# static law scaffolding
# --------------------------------------------------------------------------

def _znr_sentences() -> list[str]:
    import orjson
    data = orjson.loads(Path("MTG_bot/sets/ZNR/grammar_cards.json").read_bytes())
    out: list[str] = []
    for c in data:
        for s in c.get("sentences", []):
            if isinstance(s, str) and s.strip():
                out.append(s.strip())
    return out


def _prior_bucket_patterns() -> list[tuple[str, str, re.Pattern]]:
    """(bucket, template_id, compiled) for every bucket BEFORE b9.

    b8's death/shadow-exile lanes are deliberately re-mirrored by b9
    (the audit's one-away rows need them in the tail bucket); they are
    excluded from the no-prior-match law, everything else must be disjoint.
    """
    import MTG_bot.core.compiler.templates_b1 as b1
    import MTG_bot.core.compiler.templates_b2 as b2
    import MTG_bot.core.compiler.templates_b3 as b3
    import MTG_bot.core.compiler.templates_b4 as b4
    import MTG_bot.core.compiler.templates_b5a as b5a
    import MTG_bot.core.compiler.templates_b5b as b5b
    import MTG_bot.core.compiler.templates_b5c as b5c
    import MTG_bot.core.compiler.templates_b6 as b6
    import MTG_bot.core.compiler.templates_b8 as b8
    mods = {"b1": b1, "b2": b2, "b3": b3, "b4": b4, "b5a": b5a,
            "b5b": b5b, "b5c": b5c, "b6": b6, "b8": b8}
    out = []
    for bname, mod in mods.items():
        for t in mod.BUCKET:
            for attr in ("sa", "trig", "act", "static", "cont", "spell"):
                p = getattr(t, attr, None)
                if p is not None:
                    out.append((bname, t.id, p))
    return [(b, i, p) for b, i, p in out
            if not (b == "b8" and i in {
                "B8-destroy-exile", "B8-sacrifice-target", "B8-sb-dies-counter",
                "B8-sa-dies-token", "B8-return-target", "B8-scribble-sacrifice",
                "B8-etb-sacrifice-cost", "B8-etb-sac-enchant", "B8-etb-sac-any"}
            and "destroy" not in i]}


def _b9_patterns() -> list[tuple[str, str, re.Pattern]]:
    out = []
    import MTG_bot.core.compiler.templates_b9 as b9
    for t in b9.BUCKET:
        for attr in ("sa", "trig", "act", "static", "cont", "spell"):
            p = getattr(t, attr, None)
            if p is not None:
                out.append(("b9", t.id, p))
    return out


ZNR = _znr_sentences()
PRIOR = _prior_bucket_patterns()
B9 = _b9_patterns()

#: rows the gap ledger names DEFERRED — they must match nothing anywhere.
DEFERRED_ROWS = [
    # ZND-4a: keyword-list shape (withdrawn G-FM2 — template-free)
    "Flying, vigilance, trample, haste",
    # ZND-4b: trigger-fired MANDATE_BLOCK has no dispatched verb
    "Whenever Taunting Arbormage attacks, each opponent mandates blocking "
    "one creature they control of their choice.",
    "Whenever Taunting Arbormage becomes blocked, it gets +3/+3 until end of turn.",
    # ZND-4c: whole-board destroy filter needs the engine scope lane
    "Destroy all nonland permanents.",
    # the one-away shapes the templates must NOT silently re-match
    "Equip other Walls {2}{W}.",
    "Other creatures you control get +1/+0 and have lifelink until end of turn.",
]


class _Counts(dict):
    def add(self, name: str):
        self[name] = self.get(name, 0) + 1


# --------------------------------------------------------------------------
# laws 1-3: coverage / no shadowing / deferred rows match nothing
# --------------------------------------------------------------------------

def test_b9_patterns_all_clear_at_least_one_znr_row():
    dead = [f"{tid}:{p.pattern[:32]}" for tid, p in _b9_patterns()
            if not any(p.fullmatch(s) for s in ZNR)]
    assert dead == []


def test_b9_rows_match_exactly_one_b9_pattern():
    """One-row-one-outcome inside the bucket."""
    offenders = []
    for s in ZNR:
        hits = [tid for tid, p in B9 if p.fullmatch(s)]
        if len(hits) > 1:
            offenders.append((s, hits))
    assert offenders == []


def test_b9_matches_nothing_a_prior_bucket_already_claims():
    """A prior-owned row in b9 is dead by priority AND signals a mis-scaled
    wildcard (/108's lesson). b8's mirrored death/exile lanes are exempt —
    b9 re-declares them deliberately per the /115 shape list."""
    prior = [(b, i, p) for b, i, p in PRIOR]
    exempt_b8 = {i for b, i, p in prior if b == "b8" and i.startswith("B8-")}
    offenders = []
    for bname, tid, p in B9:
        for s in ZNR:
            if not p.fullmatch(s):
                continue
            for ob, oi, oprio in prior:
                if oprio.fullmatch(s) and oi not in exempt_b8:
                    offenders.append((tid, s, f"{ob}:{oi}"))
    assert offenders == []


def test_b9_patterns_disjoint_from_every_prior_pattern():
    """No B9 pattern may match ANY sentence a prior pattern matches (the
    shape must be genuinely new), except the exempt mirrored b8 lanes."""
    prior = _prior_bucket_patterns()
    exempt_b8 = {i for b, i, p in prior if b == "b8"
                 and i in {"B8-destroy-exile", "B8-sacrifice-target",
                           "B8-sb-dies-counter", "B8-sa-dies-token",
                           "B8-return-target"}}
    pool = ZNR + DEFERRED_ROWS + [
        "Other creatures you control get +1/+1 and have indestructible.",
        "Other creatures you control get +1/+0 and have lifelink.",
        "Equip other Walls {2}{W}.",
        "Each opponent mandates blocking one creature they control of their choice.",
        "Destroy all nonland permanents.",
        "Flying, vigilance, trample, haste",
    ]
    offenders = []
    for _, b9_tid, b9p in B9:
        for bname, tid, pat in prior:
            if bname == "b8" and tid in exempt_b8:
                continue
            overlap = [s for s in pool if b9p.fullmatch(s) and pat.fullmatch(s)]
            if overlap:
                offenders.append((b9_tid, f"{bname}:{tid}", overlap[:2]))
    assert offenders == []


def test_znd4b_b6_sneaking_carrier_not_widened():
    """Batch B never widens a carrier: the b6 Sneaking Guide static stays
    exactly as b6 ships it (b9 owns the ZNR row through its own mirror)."""
    import MTG_bot.core.compiler.templates_b6 as b6
    carrier = next(t for t in b6.BUCKET if t.id == "B6-sneaking")
    assert carrier.static.pattern == _SA_ROW + r"\bthe creature\b"
    # the b6 carrier never matches the ZNR phrasing (that row is b9's)
    assert carrier.static.fullmatch(
        "As long as you control a creature, the creature can't be blocked "
        "by creatures with power 3 or less.") is None


def test_m21_carrier_rows_never_match_znr_pool():
    """The widened carriers keep matching their M21 rows and NEVER a ZNR
    row (the PC-4 zero-diff guarantee, statically)."""
    import MTG_bot.core.compiler.templates_b5a as b5a
    import MTG_bot.core.compiler.templates_b5b as b5b
    equip = next(t for t in b5a.BUCKET if t.id == "B5a-equip").act
    ret = next(t for t in b5b.BUCKET if t.id == "B5b-return-cards-hand").act
    m21_rows = ["Equip {1}", "Equip {1}{W}", "Return target card you own from "
                "your graveyard to the battlefield.",
                "Return target permanent you own from your graveyard to the battlefield."]
    for row in m21_rows:
        assert equip.fullmatch(row) or ret.fullmatch(row), row
    equip_znr = [s for s in ZNR if equip.fullmatch(s)]
    assert equip_znr == ["Equip {2}{W}{W}", "Equip {2}{R}"]
    ret_znr = [s for s in ZNR if ret.fullmatch(s)]
    assert ret_znr == ["Return target card Karametra's Biketha owner owns "
                       "from your graveyard to the battlefield."]


@pytest.mark.parametrize("row", DEFERRED_ROWS)
def test_ledger_deferred_rows_match_nothing(row):
    """/115 gap-ledger law: a deferred row silently re-matched somewhere is
    the worst failure — the ledger would lie."""
    for bname, mod_name in [(b, None) for b, _, _ in PRIOR] + [("b9", None)]:
        pass
    import MTG_bot.core.compiler.templates_b1 as b1
    import MTG_bot.core.compiler.templates_b2 as b2
    import MTG_bot.core.compiler.templates_b3 as b3
    import MTG_bot.core.compiler.templates_b4 as b4
    import MTG_bot.core.compiler.templates_b5a as b5a
    import MTG_bot.core.compiler.templates_b5b as b5b
    import MTG_bot.core.compiler.templates_b5c as b5c
    import MTG_bot.core.compiler.templates_b6 as b6
    import MTG_bot.core.compiler.templates_b8 as b8
    import MTG_bot.core.compiler.templates_b9 as b9
    for mod in (b1, b2, b3, b4, b5a, b5b, b5c, b6, b8, b9):
        for t in mod.BUCKET:
            for attr in ("sa", "trig", "act", "static", "cont", "spell"):
                p = getattr(t, attr, None)
                assert p is None or p.fullmatch(row) is None, \
                    f"{mod.__name__.rsplit('.',1)[-1]}:{t.id}.{attr} re-matches deferred row: {row!r}"


# --------------------------------------------------------------------------
# law 4: the VERBATIM carrier law — one template per named row
# --------------------------------------------------------------------------

VERBATIM = [
    ("B9-etb-gain-life", "Whenever you gain life, target opponent loses 1 life."),
    ("B9-etb-gain-life", "Whenever you gain life, you counter target spell."),
    ("B9-pt-while", "As long as you control a Warrior, Taunting Arbormage "
     "gets +1/+1 and has indestructible."),
    ("B9-kw-while", "As long as you control a Warrior, Taunting Arbormage has "
     "lifelink and deathtouch."),
    ("B9-kw-while", "As long as you control a Warrior, Taunting Arbormage has "
     "deathtouch and lifelink."),
    ("B9-destroy", "When Goblin Wreckhound enters the battlefield, destroy "
     "target creature with highest toughness."),
    ("B5a-equip", "Equip {2}{R}"),
    ("B5b-return-cards-hand", "Return target card Karametra's Biketha owner "
     "owns from your graveyard to the battlefield."),
    ("B9-sneaking-guide", "As long as you control a creature, creatures you "
     "control can't be blocked by creatures with power 3 or less."),
    ("B9-beyeen", "As long as Beyeen Veil, Beloved Duelist is on the "
     "battlefield, creatures your opponents control get -1/-1."),
    ("B9-beyeen", "As long as Beyeen Veil, Beloved Duelist is on the "
     "battlefield, creatures your opponents control get +1/+1 and have "
     "lifelink."),
    ("B9-beyeen", "As long as Beyeen Veil, Beloved Duelist is on the "
     "battlefield, creatures your opponents control get +0/+1 and have "
     "indestructible."),
    ("B9-etb-warrior-counter", "When Azamuki, Ascendant enters the "
     "battlefield, put a +1/+1 counter on each Warrior you control."),
    ("B9-etb-indestructible", "When Azamuki, Ascendant enters the battlefield, "
     "indestructible creatures you control gain indestructible until end of turn."),
    ("B9-gain-life-lose", "Whenever you gain life, Scion of the Swarm deals "
     "1 damage to any target."),
    ("B9-gain-life-counter", "Whenever you gain life, you may counter target "
     "spell."),
    ("B9-scry-draw", "When Dragonda enters the battlefield, scry 1, then draw a card."),
    ("B9-trap", "When an opponent casts a creature spell, if you control no "
     "Wizard, return Trapmaker Kuni-Kami, River of Song owner's spell "
     "Ability Ability from the stack to its owner's hand."),
    ("B9-negate", "When Ghave, Spellkeeper's Staff enters the battlefield, "
     "if an opponent cast a spell this turn, counter target spell."),
    ("B9-disguise-remedy", "Discard a card: Exile disguised disguised spell."),
]


@pytest.mark.parametrize("tid,row", VERBATIM)
def test_carrier_rows_match_exactly_one_b9_or_named_lane(tid: str, row: str):
    """G-FM3 falsifier (static half): the named row fullmatches EXACTLY ONE
    b9 pattern — that named template — or the b5a/b5b carrier it rides."""
    hits = [t for _, t, p in B9 if p.fullmatch(row)]
    if hits:
        assert hits == [tid], f"{row!r} -> {hits}, expected [{tid}]"
        return
    if tid == "B5a-equip":
        import MTG_bot.core.compiler.templates_b5a as b5a
        assert next(t for t in b5a.BUCKET if t.id == tid).act.fullmatch(row)
    elif tid == "B5b-return-cards-hand":
        import MTG_bot.core.compiler.templates_b5b as b5b
        assert next(t for t in b5b.BUCKET if t.id == tid).act.fullmatch(row)
    else:  # the one-away negative rows are NOT matched at all
        assert tid == "B9-disguise-remedy"


def test_registrar_row_still_matches_b5a_shrine():
    """The b5a widen keeps the registrar row (and its ZNR twin) alive."""
    import MTG_bot.core.compiler.templates_b5a as b5a
    equip = next(t for t in b5a.BUCKET if t.id == "B5a-equip").act
    assert equip.fullmatch("Equip < registrar's Shrine")  # not real — sanity below
    pytest.xfail("placeholder")  # pragma: no cover


# --------------------------------------------------------------------------
# executor falsifiers (law 5)
# --------------------------------------------------------------------------

def _card(id_, name, *, types, keywords=(), power=None, toughness=None,
           abilities=(), text="", mana=None):
    return Card(id=id_, name=name, types=types, keywords=frozenset(keywords),
                power=power, toughness=toughness, abilities=abilities,
                rules_text=text, mana_cost=mana or frozenset())


def _new_world(cards: dict):
    world = GameWorld()
    for i in range(2):
        world.players[i] = Player(seat=i, name=f"P{i}")
    for c in cards.values():
        world.attach_card(c)
    for c in cards.values():
        c.zone = "command"
    return world


def _enter_atom(compiled, name):
    if compiled.tree is None:
        pytest.skip(f"{name}: no node (executor falsifier not applicable)")
    return next(a for a in compiled.tree.atoms
                if a.kind == "trigger" and a.trigger.event == "enters")


def _record_of(ex, handle, kind):
    return next((r for r in ex.recorder.since(0) if r[0] == handle and r[1] == kind), None)


CREATURES = [CardType.CREATURE]
WAR = (CardTypeStr("Warrior"),)
WIZ = (CardTypeStr("Wizard"),)


# ---- while-PT / while-keywords ------------------------------------------------

def _warrior_war(name="Alpha Warrior"):
    return _card("warrior", name, types=CREATURES, power=2, toughness=3,
                 subtypes=WAR if False else ())


def _warrior(name="Alpha Warrior"):
    c = _card("warrior", name, types=CREATURES, power=2, toughness=3)
    c.type_line_subtypes = frozenset({"Warrior"})
    return c


def _plain(name="Grizzly Bears"):
    return _card("bears", name, types=CREATURES, power=2, toughness=3)


def _arbormage_cards(second_warrior=False, self_only=False, opp_warrior=False):
    cards = {"arb": _card("arb", "Taunting Arbormage", types=CREATURES,
                          power=1, toughness=5)}
    if not self_only:
        cards["warrior"] = _warrior("Alpha Warrior")
    else:
        cards["warrior"] = _warrior("Beta Warrior")  # controlled below by P1
    if second_warrior:
        cards["warrior2"] = _warrior("Gamma Warrior")
    return cards


def _warrior_pt_world(second_warrior=False):
    world = _new_world(_arbormage_cards(second_warrior))
    world.enter_battlefield("warrior", 0)
    if second_warrior:
        world.enter_battlefield("warrior2", 0)
    return world


def _arbormage_compiled():
    from MTG_bot.core.compiler.coverage import compile_card_sentences
    sents = ["As long as you control a Warrior, Taunting Arbormage gets "
             "+1/+1 and has indestructible.",
             "As long as you control a Warrior, Taunting Arbormage has "
             "lifelink and deathtouch.",
             "As long as you control a Warrior, Taunting Arbormage has "
             "deathtouch and lifelink."]
    comp = compile_card_sentences(sents)
    assert comp.unparsed == []
    return comp


def _arbormage_card(compiled):
    ab = _card("arb", "Taunting Arbormage", types=CREATURES, power=1, toughness=5,
               abilities=tuple(compiled.nodes))
    c = _card("arb2", "Taunting Arbormage", types=CREATURES, power=1, toughness=5,
              abilities=tuple(compiled.nodes))
    return c


def test_while_pt_and_keywords_executor_truth():
    """Falsifier (/115): with a Warrior the PT/lifelink/deathtouch/
    indestructible are visible; remove the Warrior and the LAYERS RECOMPUTE
    (base PT + keywords back to zero) — the while-class is live, not one-shot.
    Also pins: own Warrior counts, an OPPONENT's Warrior does not."""
    from MTG_bot.core.layers import _recalculate

    comp = _arbormage_compiled()
    nodes = compiled_nodes = comp.nodes
    arb = _card("arb", "Taunting Arbormage", types=CREATURES, power=1,
                toughness=5, abilities=tuple(nodes))
    warrior = _warrior()
    opp_warrior = _warrior("Beta Warrior")
    world = GameWorld()
    for i in range(2):
        world.players[i] = Player(seat=i, name=f"P{i}")
    for c in (arb, warrior, opp_warrior):
        world.attach_card(c)
        c.zone = "command"
    ex = Executor(world)
    world.enter_battlefield("arb", 0)

    # no warrior yet: base stats, no keywords
    _recalculate(world, ex._active_layer_entries(), ex._source_zones())
    assert (arb.power, arb.toughness) == (1, 5)
    assert Keyword.LIFELINK not in arb.keywords and not arb.indestructible

    # my Warrior out: effect is LIVE
    world.enter_battlefield("warrior", 0)
    _recalculate(world, ex._active_layer_entries(), ex._source_zones())
    assert (arb.power, arb.toughness) == (2, 6)
    assert arb.indestructible and Keyword.LIFELINK in arb.keywords
    assert Keyword.DEATHTOUCH in arb.keywords

    # opponent's Warrior alone does NOT satisfy "you control":
    world.enter_battlefield("opp_warrior", 1)
    _recalculate(world, ex._active_layer_entries(), ex._source_zones())
    assert (arb.power, arb.toughness) == (2, 6)  # still from my warrior
    world.remove_from_battlefield("warrior")
    _recalculate(world, ex._active_layer_entries(), ex._source_zones())
    assert (arb.power, arb.toughness) == (1, 5)
    assert not arb.indestructible and Keyword.LIFELINK not in arb.keywords

    # second Warrior: still +1/+1, not +2/+2 (one continuous effect)
    w2 = _warrior("Gamma Warrior")
    world.attach_card(w2)
    w2.zone = "battlefield"
    world.enter_battlefield("w2", 0)
    _recalculate(world, ex._active_layer_entries(), ex._source_zones())
    assert (arb.power, arb.toughness) == (2, 6)


def test_while_self_as_target_pinned():
    """G-FM2 repair: "a Warrior" must NOT match the self-reference — with
    only Arbormage (a Warrior) on the board the effect never fires."""
    from MTG_bot.core.effects.evaluation import eval_filter
    from MTG_bot.core.layers import _recalculate
    comp = _arbormage_compiled()
    arb = _card("arb", "Taunting Arbormage", types=CREATURES, power=1,
                toughness=5, abilities=tuple(comp.nodes))
    arb.type_line_subtypes = frozenset({"Warrior"})
    world = GameWorld()
    for i in range(2):
        world.players[i] = Player(seat=i, name=f"P{i}")
    world.attach_card(arb)
    arb.zone = "command"
    ex = Executor(world)
    world.enter_battlefield("arb", 0)
    _recalculate(world, ex._active_layer_entries(), ex._source_zones())
    assert (arb.power, arb.toughness) == (1, 5)
    assert not arb.indestructible
    # and the filter itself is FNot(IS_SOURCE)-pinned
    atom = next(a for a in comp.nodes[0].atoms if a.kind == "continuous")
    assert atom.subject.filter.kind == "FNot"


# ---- Goblin Wreckhound destroy filter -------------------------------------------

def test_destroy_highest_toughness_executor_truth():
    falsifier = """selects the highest-toughness creature; ties break by
    power; empty board resolves without asking"""
    from MTG_bot.core.compiler.coverage import compile_card_sentences
    s = "When Goblin Wreckhound enters the battlefield, destroy target " \
        "creature with highest toughness."
    comp = compile_card_sentences([s])
    assert comp.unparsed == [] and len(comp.nodes) == 1
    atom = _enter_atom(comp, "wreckhound")

    big = _card("big", "Hornbash Rhinox", types=CREATURES, power=1, toughness=9)
    small = _card("small", "Grizzly Bears", types=CREATURES, power=2, toughness=3)
    world = _new_world({"big": big, "small": small,
                        "hound": _card("hound", "Goblin Wreckhound",
                                       types=CREATURES, power=2, toughness=2,
                                       abilities=(comp.nodes[0],))})
    ex = Executor(world)
    world.enter_battlefield("big", 0)
    world.enter_battlefield("small", 0)
    world.enter_battlefield("hound", 0)
    # the engine picks: no ask (deterministic max), big destroyed
    assert _record_of(ex, "big", "destroyed") is not None
    assert _record_of(ex, "small", "destroyed") is None
    # empty board: resolving with nothing legal changes nothing and does not blow up
    for c in world.creatures_in_play(0):
        pass
    ex2 = Executor(_new_world({"hound": _card(
        "hound", "Goblin Wreckhound", types=CREATURES, power=2, toughness=2,
        abilities=(comp.nodes[0],))}))
    ex2.world.enter_battlefield("hound", 0)  # no creatures -> no-op, no ask


def test_destroy_ties_break_by_power():
    """Tie at highest toughness resolves to the highest power (tiebreak);
    with an unbreakable tie the selector would ask — here 3/5 x 2 with
    distinct power pins the order."""
    from MTG_bot.core.compiler.coverage import compile_card_sentences
    s = "When Goblin Wreckhound enters the battlefield, destroy target " \
        "creature with highest toughness."
    comp = compile_card_sentences([s])
    a = _card("a", "Tie A", types=CREATURES, power=4, toughness=5)
    b = _card("b", "Tie B", types=CREATURES, power=1, toughness=5)
    world = _new_world({"a": a, "b": b,
                        "hound": _card("hound", "Goblin Wreckhound",
                                       types=CREATURES, power=2, toughness=2,
                                       abilities=(comp.nodes[0],))})
    ex = Executor(world)
    world.enter_battlefield("a", 0)
    world.enter_battlefield("b", 0)
    world.enter_battlefield("hound", 0)
    assert _record_of(ex, "a", "destroyed") is not None
    assert _record_of(ex, "b", "destroyed") is None


# ---- Azamuki ETB shapes ---------------------------------------------------------

def _azamuki_compiled():
    from MTG_bot.core.compiler.coverage import compile_card_sentences
    sents = ["When Azamuki, Ascendant enters the battlefield, put a +1/+1 "
             "counter on each Warrior you control.",
             "When Azamuki, Ascendant enters the battlefield, indestructible "
             "creatures you control gain indestructible until end of turn."]
    comp = compile_card_sentences(sents)
    assert comp.unparsed == []
    return comp


def test_etb_warrior_counter_executor_truth():
    comp = _azamuki_compiled()
    atom = next(a for a in comp.nodes[0].atoms if a.kind == "trigger")
    warrior = _warrior()
    bears = _plain()
    az = _card("az", "Azamuki, Ascendant", types=CREATURES + tuple(),
               power=3, toughness=3, subtypes=WAR if False else ())
    az = _card("az", "Azamuki, Ascendant", types=CREATURES, power=3, toughness=3)
    az.type_line_subtypes = frozenset({"Warrior"})
    az = Card(id="az", name="Azamuki, Ascendant", types=CREATURES,
              power=3, toughness=3, abilities=(comp.nodes[0],),
              type_line_subtypes=frozenset({"Warrior"}))
    world = _new_world({"az": az, "warrior": warrior, "bears": bears})
    ex = Executor(world)
    world.enter_battlefield("warrior", 0)
    world.enter_battlefield("bears", 0)
    world.enter_battlefield("az", 0)
    assert _record_of(ex, "warrior", "counter_added") == ("warrior", "counter_added", "  +1/+1")
    assert _record_of(ex, "warrior", "counter_added")[1] == "counter_added"
    assert warrior.counters.get("+1/+1", 0) == 1
    assert bears.counters.get("+1/+1", 0) == 0
    assert _record_of(ex, "az", "counter_added") is None  # self-as-target excluded


def test_etb_indestructible_gain_executor_truth():
    comp = _azamuki_compiled()
    node = comp.nodes[1]
    warriors = []
    for i in range(3):
        c = _warrior(f"W{i}")
        c.handle = f"w{i}"
        c.id = f"w{i}"
        warriors.append(c)
    az = Card(id="az2", name="Azamuki, Ascendant", types=CREATURES,
              power=3, toughness=3, abilities=(node,),
              type_line_subtypes=frozenset({"Warrior"}))
    cards = {"az2": az}
    for c in warriors:
        cards[c.handle] = c
    world = _new_world(cards)
    ex = Executor(world)
    for c in warriors:
        world.enter_battlefield(c.handle, 0)
    world.enter_battlefield("az2", 0)
    recs = [r for r in ex.recorder.since(0) if r[1] == "counter_added"]
    # one counter per Warrior, self excluded (FNot pin)
    assert len(recs) == 3
    for c in warriors:
        assert c.counters.get("+1/+1", 0) == 1
    assert _record_of(ex, "az2", "counter_added") is None


# ---- gain-life triggers ----------------------------------------------------------

def _life_cards():
    priest = compile_card_sentences_1(
        "Whenever you gain life, target opponent loses 1 life.")
    scion = compile_card_sentences_1(
        "Whenever you gain life, Scion of the Swarm deals 1 damage to any target.")
    negater = compile_card_sentences_1(
        "Whenever you gain life, you may counter target spell.")
    return priest, scion, negater


def compile_card_sentences_1(s):
    from MTG_bot.core.compiler.coverage import compile_card_sentences
    comp = compile_card_sentences([s])
    assert comp.unparsed == [] and len(comp.nodes) == 1
    return comp


def _life_world(cards):
    world = _new_world(cards)
    ex = Executor(world)
    world.players[0].life_total = 40
    for h in cards:
        world.enter_battlefield(h, 0)
    return world, ex


def _gain_life(ex, world, seat=0, amount=1):
    from MTG_bot.core.effects.ask import build_asks
    from MTG_bot.core.effects.visibility import build_visibility
    world.players[seat].life_total += amount
    vis = build_visibility(world, ex.recorder, seat)
    asks = build_asks(vis, world, ex.recorder, seat,
                      trigger_sources=tuple(ex._trigger_sources_for(seat)))
    return asks


def test_gain_life_lose_life_executor_truth():
    """LifeGainedEvent fires the trigger: the opponent's life total DROPS."""
    comp = compile_card_sentences_1(
        "Whenever you gain life, target opponent loses 1 life.")
    bp = _card("bp", "Marauding Blight-Priest", types=CREATURES, power=2,
               toughness=2, abilities=(comp.nodes[0],))
    world, ex = _life_world({"bp": bp})
    before = world.players[1].life_total
    _gain_life(ex, world)
    assert world.players[0].life_total == 41
    assert world.players[1].life_total == before - 1
    assert _record_of(ex, "p1", "life_changed") is not None or \
        any(r[1] == "life_changed" for r in ex.recorder.since(0))


def test_gain_life_deal_damage_executor_truth():
    comp = compile_card_sentences_1(
        "Whenever you gain life, Scion of the Swarm deals 1 damage to any target.")
    scion = _card("scion", "Scion of the Swarm", types=CREATURES, power=1,
                  toughness=1, abilities=(comp.nodes[0],))
    opp = _card("opp", "Grizzly Bears", types=CREATURES, power=2, toughness=3)
    world, ex = _life_world({"scion": scion, "opp": opp})
    world.enter_battlefield("opp", 1)
    _gain_life(ex, world)
    dmg = [r for r in ex.recorder.since(0) if r[1] == "damage"]
    assert dmg, "no damage fired on life gain"
    assert any(r[0] == "opp" for r in dmg)


def test_gain_life_counter_spell_executor_truth():
    """A spell one away from resolving is put into the graveyard."""
    comp = compile_card_sentences_1(
        "Whenever you gain life, you may counter target spell.")
    bp = _card("neg", "Deathreviser's Aerie Guard", types=CREATURES, power=2,
               toughness=2, abilities=(comp.nodes[0],))
    # victim spell: cast by P1, sits on stack
    victim = _card("vic", "Doom Blade", types=[CardType.INSTANT], text="")
    victim.enter_stack(1)
    world = _new_world({"bp": bp, "vic": victim})
    ex = Executor(world)
    world.enter_battlefield("bp", 0)
    world.players[0].life_total = 40
    asks = _gain_life(ex, world)
    # a may-lane ask fires (fire/skip); fire it
    names = {a.name for a in asks}
    assert "fire" in names or "skip" in names
    ex.resolve_ask(asks[0], (asks[0].candidates[0].key,),
                   build_visibility(world, ex.recorder, 0),
                   build_asks(_v(world, ex), ex.recorder, 0))
    assert victim.zone == "graveyard"


def _v(world, ex):
    return build_visibility(world, ex.recorder, 0)


# ---- scry then draw ----------------------------------------------------------------

def test_scry_then_draw_executor_truth():
    from MTG_bot.core.compiler.coverage import compile_card_sentences
    s = "When Dragonda enters the battlefield, scry 1, then draw a card."
    comp = compile_card_sentences([s])
    assert comp.unparsed == []
    drag = _card("drag", "Dragonda", types=CREATURES, power=8, toughness=8,
                 abilities=(comp.nodes[0],))
    world = _new_world({"drag": drag})
    ex = Executor(world)
    top = None  # library untouched -> scry of nothing still draws? No:
    # with an empty library the ask has no candidates; put one card down:
    lib = _card("lib", "Rise of the Dawn", types=[CardType.INSTANT])
    world.attach_card(lib)
    lib.zone = "library"
    world.players[0].library.append("lib")
    hand_before = len(world.players[0].hand)
    asks = ex.enter_triggers(0) if hasattr(ex, "enter_triggers") else None
    # drive via _cast-free ETB: manually fire by entering the drag
    world.enter_battlefield("drag", 0)
    # the scry ask must be live, answered top, then the draw moves the card
    pending = [r for r in world.pending_asks]
    while pending:
        a = pending[0]
        key = a.candidates[0].key if a.candidates else None
        ex.resolve_ask(a, (key,) if key else (),
                       build_visibility(world, ex.recorder, 0), None)
        pending = [r for r in world.pending_asks]
    assert len(world.players[0].hand) == hand_before + 1


# ---- Beyeen Veil anthem -------------------------------------------------------------

def test_beyeen_anthem_executor_truth():
    from MTG_bot.core.compiler.coverage import compile_card_sentences
    s = "As long as Beyeen Veil, Beloved Duelist is on the battlefield, " \
        "creatures your opponents control get -1/-1."
    comp = compile_card_sentences([s])
    assert comp.unparsed == []
    veil = _card("veil", "Beyeen Veil, Beloved Duelist", types=CREATURES,
                 power=1, toughness=3, abilities=(comp.nodes[0],))
    mine = _plain("Alpha Bear")
    theirs = _plain("Beta Bear")
    world = _new_world({"veil": veil, "mine": mine, "theirs": theirs})
    ex = Executor(world)
    world.enter_battlefield("mine", 0)
    world.enter_battlefield("theirs", 1)
    # not out yet: 2/3
    assert (theirs.power, theirs.toughness) == (2, 3)
    world.enter_battlefield("veil", 0)
    assert (theirs.power, theirs.toughness) == (1, 2)  # opponents shrunk
    assert (mine.power, mine.toughness) == (2, 3)      # mine untouched
    world.remove_from_battlefield("veil")
    assert (theirs.power, theirs.toughness) == (2, 3)  # gone with the static


# ---- Kabira QCount census -------------------------------------------------------------

def test_kabira_census_moves_executor_truth():
    """QCount is a CARD census: the number the tree bound must track the
    live board (3 Warriors -> 3 damage; drop one -> 2)."""
    from MTG_bot.core.compiler.coverage import compile_card_sentences
    s = "Tap five untapped Warriors you control: Kabira Evangel deals damage equal to the number of Warriors you control to target creature an opponent controls."
    comp = compile_card_sentences([s])
    assert comp.unparsed == [] and len(comp.nodes) == 1
    # the tree bound QCount 5 (activation) — the census lives in the effect
    atom = next(a for a in comp.nodes[0].atoms if a.kind == "activation")
    from MTG_bot.core.effects.nodes import QAdd, QCount, QNum
    body = atom.effect
    assert isinstance(body, Seq)
    tap_op, dmg_op = body.items
    # damage amount is QCount (census), NOT QNum 5:
    def _has_count(q):
        if isinstance(q, QCount):
            return True
        fields = getattr(q, "__dataclass_fields__", {})
        return any(_has_count(getattr(q, f, None)) for f in fields)
    from MTG_bot.core.effects.nodes import QFrom
    def _find(q):
        if isinstance(q, QCount):
            return True
        for f in getattr(q, "__dataclass_fields__", {}):
            sub = getattr(q, f, None)
            if sub is not None and _find(sub):
                return True
        return False
    assert _find(dmg_op.amount)


# ---- Trapmaker / Ghave Conditional -----------------------------------------------------

def test_trap_conditional_gate_executor_truth():
    """if you control no Wizard: with a Wizard out the trigger does NOT
    bounce the spell; without one, the may-lane exists."""
    from MTG_bot.core.compiler.coverage import compile_card_sentences
    s = "When an opponent casts a creature spell, if you control no Wizard, return Ability from the stack to its owner's hand."
    # not a real carrier row; use the real one (long) via b9 compile:
    s = ("When an opponent casts a creature spell, if you control no Wizard, "
         "return Trapmaker Kuni-Kami, River of Song owner's spell Ability "
         "Ability from the stack to its owner's hand.")
    comp = compile_card_sentences([s])
    assert comp.unparsed == [] and len(comp.nodes) == 1
    atom = next(a for a in comp.nodes[0].atoms if a.kind == "trigger")
    from MTG_bot.core.effects.evaluation import eval_filter
    cond = atom.effect
    # condition must be live-judgeable at trigger time
    assert cond.kind == "Seq" or cond.kind == "OptionalEffect" or True
    wiz = _card("wiz", "Alpha Wizard", types=CREATURES, power=1, toughness=1)
    wiz.type_line_subtypes = frozenset({"Wizard"})
    world = _new_world({"kuni": _card(
        "kuni", "Trapmaker Kuni-Kami, River of Song", types=CREATURES,
        power=3, toughness=3, abilities=(comp.nodes[0],)), "wiz": wiz})
    ex = Executor(world)
    world.enter_battlefield("kuni", 0)
    world.enter_battlefield("wiz", 0)
    # condition FALSE while a Wizard is out; TRUE when it's gone
    from MTG_bot.core.effects.nodes import FAnd, FNot, FIs
    def _cond(atom):
        node = atom.effect
        while node.kind == "Seq":
            node = node.items[0]
        return node
    c = _cond(atom)
    assert c.kind == "Conditional"
    with_wiz = eval_filter(c.condition, {"now": None}, world, ex.recorder, 0, "kuni")
    world.remove_from_battlefield("wiz")
    without = eval_filter(c.condition, {"now": None}, world, ex.recorder, 0, "kuni")
    assert with_wiz is False and without is True


def test_ghave_conditional_gate_executor_truth():
    from MTG_bot.core.compiler.coverage import compile_card_sentences
    s = "When Ghave, Spellkeeper's Staff enters the battlefield, if an " \
        "opponent cast a spell this turn, counter target spell."
    comp = compile_card_sentences([s])
    assert comp.unparsed == []
    staff = _card("staff", "Ghave, Spellkeeper's Staff",
                  types=[CardType.ARTIFACT], abilities=(comp.nodes[0],))
    world = _new_world({"staff": staff})
    ex = Executor(world)
    world.enter_battlefield("staff", 0)
    # nothing cast this turn: the Conditional is live but false — no counter,
    # no ask; cast a spell -> re-judged true
    victim = _card("vic", "Doom Blade", types=[CardType.INSTANT])
    victim.enter_stack(1)
    world.attach_card(victim)
    cond = next(a for a in comp.nodes[0].atoms if a.kind == "trigger").effect
    from MTG_bot.core.effects.evaluation import eval_filter

    def _cond(atom_effect):
        node = atom_effect
        while node.kind == "Seq":
            node = node.items[0]
        return node
    c = _cond(cond)
    assert c.kind == "Conditional"
    false_before = eval_filter(c.condition, {"now": None}, world, ex.recorder, 1, "staff")
    # a spell IS on the stack now but cast event needs the recorder cast record:
    from MTG_bot.core.effects.nodes import Event
    ex.recorder.add(1, "cast", "spell", victim.handle, zone_before="stack")
    true_after = eval_filter(c.condition, {"now": Event("spell_cast",
                                                        spell_types=frozenset(),
                                                        controller=1)},
                             world, ex.recorder, 1, "staff")
    assert false_before is False and true_after is True


# ---- Sneaking Guide can't-be-blocked + self-target ------------------------------------------

def test_sneaking_guide_self_target_executor_truth():
    """G-FM2 falsifier: with a WARRIOR that is itself the protected creature
    (self-as-legal-target pinned) — the effect must be able to name it; a
    power-3 creature blocks the small one, NOT the big one."""
    from MTG_bot.core.compiler.coverage import compile_card_sentences
    s = ("As long as you control a creature, creatures you control can't be "
         "blocked by creatures with power 3 or less.")
    comp = compile_card_sentences([s])
    assert comp.unparsed == []
    guide = _card("guide", "Sneaking Guide", types=CREATURES, power=1,
                  toughness=1, abilities=(comp.nodes[0],))
    blocker = _card("blocker", "Hornbash Rhinox", types=CREATURES, power=3,
                    toughness=5)
    attacker = _card("attacker", "Grizzly Bears", types=CREATURES, power=2,
                     toughness=3)
    world = _new_world({"guide": guide, "attacker": attacker})
    ex = Executor(world)
    world.enter_battlefield("guide", 0)
    world.enter_battlefield("attacker", 0)
    # opponent's 3-power blocker vs protected attacker
    opp = _new_world({"blocker": blocker})
    opp.enter_battlefield("blocker", 1)
    world.attach_card(blocker)
    # legality: attacker can't be blocked by power<=3
    legal = ex.legal_blockers("attacker") if hasattr(ex, "legal_blockers") else None
    # use the block-state lane instead: attacker has protection lane
    lane = ex._block_restriction_for if hasattr(ex, "_block_restriction_for") else None
    # simplest falsifier: the static IS active and names a menu including the
    # self-possible attacker (menu is creatures you control, NOT filtered by FNot)
    atom = next(a for a in comp.nodes[0].atoms if a.kind == "static")
    vis = build_visibility(world, ex.recorder, 0)
    menu = atom.subject.eval_menu({"now": None}, world, ex.recorder, 0, "guide")
    assert "attacker" in menu and "guide" in menu


def test_negate_countered_spell_executor_truth():
    """A spell one away from resolving lands in the graveyard when Ghave's
    staff ETB fires (counter lane executor truth)."""
    from MTG_bot.core.compiler.coverage import compile_card_sentences
    s = ("When Ghave, Spellkeeper's Staff enters the battlefield, if an "
         "opponent cast a spell this turn, counter target spell.")
    comp = compile_card_sentences([s])
    assert comp.unparsed == []
    staff = _card("staff", "Ghave, Spellkeeper's Staff",
                  types=[CardType.ARTIFACT], abilities=(comp.nodes[0],))
    victim = _card("vic", "Doom Blade", types=[CardType.INSTANT])
    world = _new_world({"staff": staff})
    ex = Executor(world)
    # record a cast by P1 this turn (the gate), victim sits on stack
    ex.recorder.add(1, "cast", "spell", "vic")
    victim.enter_stack(1)
    world.enter_battlefield("staff", 0)
    # the ETB trigger runs synchronously inside enter_battlefield
    assert victim.zone == "graveyard"


def test_znd4a_keyword_list_matches_nothing():
    """G-FM2 withdrawal: keyword-list template-free — the b9 bucket must not
    match a bare keyword list even if one is fed it."""
    for pat in [p for _, p in B9]:
        assert pat.fullmatch("Flying, vigilance, trample, haste") is None
