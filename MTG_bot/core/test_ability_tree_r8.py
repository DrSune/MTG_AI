"""Grammar round 7 — nine additive items (2026-09-28).

Round-7 scope (spec: KNOWLEDGE/2026-09-28/03-grammar-round7-decision.md;
file-name offset is intentional — round-7 grammar ships in the r8 file,
following the r6-in-r7 precedent):

- R7-1: referent vocabulary ``"result"`` appended to
  ``_QPROP_STR_REFERENTS`` (the object(s) the previous sentence acted on —
  C12 anaphora referent); ``Verb.CHOOSE`` (pick a set FROM the target
  pool, Duress/Kitesail "You choose … from it"); ``FAtomPred.
  IS_ATTACHED_TO`` with a REQUIRED ``referent`` slot (Turn to Slag) — the
  FAtom str slot follows the R4-4 zone-slot precedent (omit-when-None,
  byte-stable).
- R7-2: ``DurationUntilLeaves`` (Kitesail Cabinet "until this creature
  leaves the battlefield", Idol of Endurance) — referent-string field,
  default "source", vocabulary-validated; ``_VERB_ROLES[GAIN_CONTROL]``
  gains the optional ``duration`` role (Traitorous).
- R7-3: compiler ``_CONTINUATION_PREFIXES`` += ("Otherwise", "When you
  do"); ``_merge_otherwise`` attaches the parsed effect as the
  ``else_effect`` of the previous Conditional, C13 fallback to the
  default merge. "When you do" prefix registered; its event binding
  (Tolarian Kraken, antecedent "you may pay {1}") has NO clean existing
  event — the row stays queued (batch-phase concern).
- R7-4: ``Verb.CHOOSE_NAME`` {name_filter?} + ``FAtomPred.NAME_CHOSEN``
  (no slots; Runed Halo / Necromentia).
- R7-5/6: ``QPropField.THIS_WAY_COUNT`` / ``THAT_MANY_COUNT`` — event
  referent, AMOUNT validation family (Siege Striker, Kinetic Augur).
- R7-7: ``SelectorMode.ONE_OF`` / ``REST`` — the split-selection pair
  (Waker of Waves, See the Truth, Cultivate); ONE_OF needs a concrete
  count (TARGET family), REST ignores count (ALL family).
- R7-8: ``Verb.FIGHT`` {target} (Brash Taunter, Primal Might) —
  executor deferred per the MANDATE_BLOCK orphan precedent.
- R7-9: ``Verb.LOSE_ABILITY`` mirrors ``GRANT_ABILITY`` (Soul Sear);
  ``QProp.COUNTER_COUNT`` referent validation relaxed to
  "event" | "source" (Malefic Scythe's SOUL counters on this Equipment —
  supersedes the r6 "qprop_cc_source" rejection case).

Guards:
- every pre-round-7 pinned fingerprint (the r6 + r7 pin sets) stays
  byte-identical — all nine items are additive;
- bare FAtom (no referent) serializes WITHOUT the new key — pinned
  against an explicit expected dict;
- the "result" referent serializes as a PLAIN STRING on both Selector and
  QProp (byte-shape pins);
- round-7 constructs round-trip through ``to_dict``/``from_dict`` with
  pinned fingerprints; rejections at every new validation point.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest

import MTG_bot.core.ability_tree as at
import MTG_bot.core.test_ability_tree_r6 as R6
import MTG_bot.core.test_ability_tree_r7 as R7
from MTG_bot.core.compiler.compiler import (
    _CONTINUATION_PREFIXES,
    _is_continuation,
    _merge_otherwise,
    compile_card,
)
from MTG_bot.core.compiler.ingest import RawCard
from MTG_bot.core.compiler.templates import (
    EffectOutcome,
    Template,
    TemplateRegistry,
)
from MTG_bot.core.identity import CardIdentity

# ---- builders for the round-7 constructs -----------------------------------

_UNIVERSAL = at.FAnd(())
_NEUTRAL = at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY)
_BF_YOU = at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU)
_LIB_OPP = at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.OPPONENT)
_IS_SOURCE = at.FAtom(at.FAtomPred.IS_SOURCE)


def _result_sel() -> at.Selector:
    """R7-1: the anaphoric "it/them" — a referent="result" selector
    (convention C2: CHOOSE + QConst(1) + the neutral zone)."""
    return at.Selector(
        at.QConst(1), at.SelectorMode.CHOOSE, _UNIVERSAL, _NEUTRAL, referent="result"
    )


def _pool_sel() -> at.Selector:
    """CHOOSE's pool role: "from it" = the opponent's library (Duress)."""
    return at.Selector(at.QUnbounded(), at.SelectorMode.ALL, _UNIVERSAL, _LIB_OPP)


def _target_sel() -> at.Selector:
    """A creature-target selector (FIGHT / GAIN_CONTROL / LOSE_ABILITY)."""
    return at.Selector(
        at.QConst(1),
        at.SelectorMode.TARGET,
        at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature"),
        _BF_YOU,
    )


def _draw_atom(amount: int = 1) -> at.Atom:
    return at.Atom(
        at.Verb.DRAW,
        at.AtomArgs(
            pairs=(("controller", at.ControllerRef.YOU), ("amount", at.QConst(amount)))
        ),
    )


def _mill_atom() -> at.Atom:
    return at.Atom(
        at.Verb.MILL,
        at.AtomArgs(
            pairs=(("controller", at.ControllerRef.YOU), ("amount", at.QConst(1)))
        ),
    )


def _atom_choose() -> at.Atom:
    """R7-1: Duress/Kitesail — choose a card FROM the looked-at pool."""
    return at.Atom(
        at.Verb.CHOOSE,
        at.AtomArgs(pairs=(("target", _pool_sel()), ("count", at.QConst(1)))),
    )


def _atom_choose_name_bare() -> at.Atom:
    """R7-4: Runed Halo s1 — a free choice of card name, no filter."""
    return at.Atom(at.Verb.CHOOSE_NAME, at.AtomArgs(pairs=()))


def _atom_choose_name_filtered() -> at.Atom:
    """R7-4: Necromentia s1 — "choose a nonbasic card name"."""
    return at.Atom(
        at.Verb.CHOOSE_NAME,
        at.AtomArgs(
            pairs=(
                (
                    "name_filter",
                    at.FNot(at.FAtom(at.FAtomPred.SUPERTYPE_EQ, string_value="Basic")),
                ),
            )
        ),
    )


def _atom_fight() -> at.Atom:
    """R7-8: Brash Taunter — "This creature fights another target
    creature" (attacker = the source object, never a role)."""
    return at.Atom(at.Verb.FIGHT, at.AtomArgs(pairs=(("target", _target_sel()),)))


def _atom_lose_ability() -> at.Atom:
    """R9a: Soul Sear — "that permanent loses indestructible until end of
    turn"; roles mirror GRANT_ABILITY."""
    return at.Atom(
        at.Verb.LOSE_ABILITY,
        at.AtomArgs(
            pairs=(
                ("target", _target_sel()),
                ("ability", at.KeywordAbility(at.Keyword.INDESTRUCTIBLE)),
                ("duration", at.DurationEot()),
            )
        ),
    )


def _atom_gain_control_duration() -> at.Atom:
    """R7-2: Traitorous — "gain control of target creature until end of
    turn": the new optional duration role."""
    return at.Atom(
        at.Verb.GAIN_CONTROL,
        at.AtomArgs(
            pairs=(
                ("target", _target_sel()),
                ("controller", at.ControllerRef.YOU),
                ("duration", at.DurationEot()),
            )
        ),
    )


def _dur_until_leaves() -> at.DurationUntilLeaves:
    """R7-2: default "source" anchor (Kitesail Cabinet's own creature)."""
    return at.DurationUntilLeaves()


def _dur_until_leaves_result() -> at.DurationUntilLeaves:
    """R7-2 with a non-default vocabulary referent anchor."""
    return at.DurationUntilLeaves(source="result")


def _sel_one_of() -> at.Selector:
    """R7-7: "put one of them in your hand" (Waker of Waves)."""
    return at.Selector(at.QConst(1), at.SelectorMode.ONE_OF, _UNIVERSAL, _BF_YOU)


def _sel_rest() -> at.Selector:
    """R7-7: "put the rest on the bottom" (See the Truth) — count ignored
    like ALL."""
    return at.Selector(at.QConst(1), at.SelectorMode.REST, _UNIVERSAL, _BF_YOU)


def _fatom_is_attached() -> at.FAtom:
    """R7-1: "Destroy target Equipment attached to that/source" (Turn to
    Slag) — the new required referent str slot."""
    return at.FAtom(at.FAtomPred.IS_ATTACHED_TO, referent="source")


def _fatom_name_chosen() -> at.FAtom:
    """R7-4: "cards with that name" (Runed Halo s2, Necromentia s2) — the
    CHOOSE_NAME read-back, no slots like IS_TAPPED."""
    return at.FAtom(at.FAtomPred.NAME_CHOSEN)


def _qprop_this_way() -> at.QProp:
    """R7-5: "for each creature tapped this way" (Siege Striker)."""
    return at.QProp(referent="event", field=at.QPropField.THIS_WAY_COUNT)


def _qprop_that_many() -> at.QProp:
    """R7-6: "discard up to two … draw that many" (Kinetic Augur)."""
    return at.QProp(referent="event", field=at.QPropField.THAT_MANY_COUNT)


def _qprop_cc_source() -> at.QProp:
    """R9b: Malefic Scythe — SOUL counter count of the SOURCE Equipment
    (the r6 rejection relaxed; kind detail stays executor-side, QProp
    carries no counter-kind field)."""
    return at.QProp(referent="source", field=at.QPropField.COUNTER_COUNT)


def _conditional_else() -> at.Conditional:
    """R7-3 merge TARGET: the pre-existing else_effect field, pinned as a
    regression anchor for _merge_otherwise (Garruk, Savage Herald s2
    after the Otherwise merge)."""
    return at.Conditional(
        pred=at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature"),
        then_effect=_draw_atom(1),
        else_effect=_mill_atom(),
    )


def _conditional_bare() -> at.Conditional:
    """The pre-merge shape: Conditional without else_effect."""
    return at.Conditional(
        pred=at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature"),
        then_effect=_draw_atom(1),
    )


# ---- pinned fingerprints (captured after the round-7 edits) ----------------

_NEW_PINS: list[tuple[str, Callable[[], object], str]] = [
    (
        "atom_choose",
        _atom_choose,
        "e8e5f1a33805867d6bb955c000088a438e899aaf7caae4e6efa0d1447792253f",
    ),
    (
        "atom_choose_name_bare",
        _atom_choose_name_bare,
        "05432a45ef231d79d2d0ea9068d4ed104385c062d1fe5daf8017e0edb397374e",
    ),
    (
        "atom_choose_name_filtered",
        _atom_choose_name_filtered,
        "92d17275ac1f705e6b9f9eea83fcad14e1d5316edd3030bd99cb1d7ecb5ef1d2",
    ),
    (
        "atom_fight",
        _atom_fight,
        "3a227ef67167d13063b10cb3ee746197f693b90927deb5675e2241f9a16b4118",
    ),
    (
        "atom_lose_ability",
        _atom_lose_ability,
        "e7604dbc1fb49a1a59e2075dece0a82780568750ef7ee6edab6fae343392e195",
    ),
    (
        "atom_gain_control_duration",
        _atom_gain_control_duration,
        "3e9a82d056210786cc92830b44626fd45a858c00aafce30709192426f3323b57",
    ),
    (
        "dur_until_leaves",
        _dur_until_leaves,
        "f03c5dfa7b84e55340aab71ae2710757a6e90e4a9bcf501ba80d018ad32d865b",
    ),
    (
        "dur_until_leaves_result",
        _dur_until_leaves_result,
        "125059b68d5ca9053d19f73a1dcf7eb878e7b5327bedf86b4d1a12cd6545cb5a",
    ),
    (
        "sel_one_of",
        _sel_one_of,
        "f579f21b8bf7648e0a897c2262c3c87e040a230544a3c874ea9773c3c20c9dfb",
    ),
    (
        "sel_rest",
        _sel_rest,
        "8fd5be5191ffce82b90a3e283832d8481954a5ff51e61bb5221878d88baf63ef",
    ),
    (
        "fatom_is_attached",
        _fatom_is_attached,
        "9c2d5b2f8948631ec98e43fa49fccb841310883a0eb3c655a9a018a38dd426d4",
    ),
    (
        "fatom_name_chosen",
        _fatom_name_chosen,
        "588d22c798d76e5d401b8136ef5c4fa5d7804ca5e7098b40d0a15e2c35458c40",
    ),
    (
        "qprop_this_way",
        _qprop_this_way,
        "2672b389a355956a60f28bc38a0c28faa3efdb1290839d259e9437585a91af62",
    ),
    (
        "qprop_that_many",
        _qprop_that_many,
        "6cb5885392efeebf80491ea2fa4b85aacdcd82e8dbaf8b002fb23c36e9d23cd0",
    ),
    (
        "qprop_cc_source",
        _qprop_cc_source,
        "2bb58241fc49dbc462ae4229fa74f108dea15d6e0d0fcee4cfae60a6e785288c",
    ),
    (
        "conditional_else",
        _conditional_else,
        "81e573b85eb3eae597a10973a5bc134e286e37ba92a39f22cc070fb1dd598241",
    ),
]


# ---- tests ----------------------------------------------------------------


@pytest.mark.parametrize(
    "name,build,fp",
    R6._NEW_PINS + R7._NEW_PINS,
    ids=[n for n, _, _ in R6._NEW_PINS + R7._NEW_PINS],
)
def test_pinned_pre_r8_fingerprint(
    name: str, build: Callable[[], object], fp: str
) -> None:
    """Byte stability: every pre-round-7 pinned tree (the r6 + r7 pin
    sets) serializes identically — all nine round-7 items are additive."""
    node = build()
    assert at.fingerprint(node) == fp
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d


@pytest.mark.parametrize("name,build,fp", _NEW_PINS, ids=[n for n, _, _ in _NEW_PINS])
def test_r8_roundtrip(name: str, build: Callable[[], object], fp: str) -> None:
    node = build()
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d
    back = at.from_dict(d["tag"], d)
    assert back == node, f"{name}: from_dict(to_dict(x)) != x"
    assert at.canonical_json(back) == at.canonical_json(node)
    if fp != "PENDING":
        assert at.fingerprint(back) == at.fingerprint(node) == fp


def test_r8_table_members() -> None:
    assert at.Verb.CHOOSE.value == "CHOOSE"
    assert at.Verb.CHOOSE_NAME.value == "CHOOSE_NAME"
    assert at.Verb.FIGHT.value == "FIGHT"
    assert at.Verb.LOSE_ABILITY.value == "LOSE_ABILITY"
    assert at.SelectorMode.ONE_OF.value == "ONE_OF"
    assert at.SelectorMode.REST.value == "REST"
    assert at.FAtomPred.IS_ATTACHED_TO.value == "IS_ATTACHED_TO"
    assert at.FAtomPred.NAME_CHOSEN.value == "NAME_CHOSEN"
    assert at.QPropField.THIS_WAY_COUNT.value == "THIS_WAY_COUNT"
    assert at.QPropField.THAT_MANY_COUNT.value == "THAT_MANY_COUNT"
    assert at.FAtomPred.IS_ATTACHED_TO in at.FAtomPred
    assert at.FAtomPred.NAME_CHOSEN in at.FAtomPred
    # DurationUntilLeaves is registered everywhere DurationWhileCondition
    # is (r6 R6-3 role-table-precedent for registration checks).
    assert at.DurationUntilLeaves in at._D_CLASSES
    assert at.DurationUntilLeaves in at._DATACLASSES
    assert "DurationUntilLeaves" in at._DURATION_TAGS
    spec = dict(at._SPECS["DurationUntilLeaves"])
    assert spec == {"source": "str"}
    # the appended vocabulary tail (r5 pinned the pre-r7 four order)
    assert at._QPROP_STR_REFERENTS[-1] == "result"
    # FAtom referent: opt slot + omit-if-empty (R4-4 precedent)
    assert dict(at._SPECS["FAtom"])["referent"] == "opt:str"
    assert "referent" in at._OMIT_IF_EMPTY["FAtom"]


def test_verb_role_tables_r7() -> None:
    assert at._VERB_ROLES[at.Verb.CHOOSE] == {
        "target": True,
        "count": False,
        "duration": False,
    }
    assert at._VERB_ROLES[at.Verb.CHOOSE_NAME] == {
        "name_filter": False,
    }
    assert at._VERB_ROLES[at.Verb.FIGHT] == {"target": True}
    # R9a: exact mirror of GRANT_ABILITY
    assert at._VERB_ROLES[at.Verb.LOSE_ABILITY] == at._VERB_ROLES[at.Verb.GRANT_ABILITY]
    # R7-2: GAIN_CONTROL widened, previous required roles unchanged
    assert at._VERB_ROLES[at.Verb.GAIN_CONTROL] == {
        "target": True,
        "controller": True,
        "duration": False,
    }
    assert at._ROLE_TYPES["name_filter"] == at._F_CLASSES


def test_gain_control_without_duration_still_builds() -> None:
    """R7-2: the pre-round-7 GAIN_CONTROL shape (no duration) keeps
    building — the role is optional, validation-only."""
    bare = at.Atom(
        at.Verb.GAIN_CONTROL,
        at.AtomArgs(
            pairs=(("target", _target_sel()), ("controller", at.ControllerRef.YOU))
        ),
    )
    assert at.from_dict("Atom", at.to_dict(bare)) == bare
    assert at.from_dict("Atom", at.to_dict(_atom_gain_control_duration())) == (
        _atom_gain_control_duration()
    )


def test_fatom_is_attached_rule_and_serialization() -> None:
    assert at._FATOM_RULES[at.FAtomPred.IS_ATTACHED_TO] == (
        frozenset({"referent"}),
        frozenset({"referent"}),
    )
    assert at._FATOM_RULES[at.FAtomPred.NAME_CHOSEN] == (
        frozenset(),
        frozenset(),
    )
    d = at.to_dict(_fatom_is_attached())
    # the referent slot serializes as a PLAIN STRING (C12: data, not node)
    assert d["referent"] == "source"


def test_bare_fatom_omits_referent_byte_shape() -> None:
    """Byte-shape pin: a pre-round-7 FAtom gains NO 'referent' key."""
    assert at.to_dict(at.FAtom(at.FAtomPred.IS_TAPPED)) == {
        "tag": "FAtom",
        "pred": {"tag": "FAtomPred", "name": "IS_TAPPED"},
        "string_value": None,
        "color": None,
        "colors": [],
        "count": None,
        "counter_kind": None,
        "keyword": None,
        "who": None,
        "inner_filter": None,
    }
    assert at.to_dict(_fatom_name_chosen()) == at.to_dict(
        at.FAtom(at.FAtomPred.IS_TAPPED)
    ) | {"pred": {"tag": "FAtomPred", "name": "NAME_CHOSEN"}}


def test_result_referent_plain_string_byte_pins() -> None:
    """R7-1/C12: 'result' serializes as a plain string on both Selector
    and QProp — pinned against explicit expected dicts."""
    assert at.to_dict(_result_sel()) == {
        "tag": "Selector",
        "count": {"tag": "QConst", "value": 1},
        "mode": {"tag": "SelectorMode", "name": "CHOOSE"},
        "filter": {"tag": "FAnd", "children": []},
        "zone": {
            "tag": "Zone",
            "kind": {"tag": "ZoneKind", "name": "ANY"},
            "controller": {"tag": "ControllerRef", "name": "ANY"},
        },
        "referent": "result",
    }
    q = at.QProp(referent="result", field=at.QPropField.POWER)
    assert at.to_dict(q) == {
        "tag": "QProp",
        "referent": "result",
        "field": {"tag": "QPropField", "name": "POWER"},
        "agg": {"tag": "QAgg", "name": "FIRST"},
    }
    assert at.from_dict("Selector", at.to_dict(_result_sel())) == _result_sel()
    assert at.from_dict("QProp", at.to_dict(q)) == q


def test_selector_mode_family_validation() -> None:
    """R7-7: ONE_OF belongs to the TARGET count family (concrete count
    required); REST to the ALL family (count ignored, separate test)."""
    with pytest.raises(ValueError):
        at.Selector(at.QUnbounded(), at.SelectorMode.ONE_OF, _UNIVERSAL, _BF_YOU)


def test_rest_ignores_unbounded_count() -> None:
    rest = at.Selector(at.QUnbounded(), at.SelectorMode.REST, _UNIVERSAL, _BF_YOU)
    assert rest.mode is at.SelectorMode.REST


def test_conditional_else_effect_roundtrip_pin() -> None:
    """The pre-existing else_effect field, pinned as a regression anchor
    for the R7-3 Otherwise merge."""
    node = _conditional_else()
    d = at.to_dict(node)
    assert d["tag"] == "Conditional"
    assert "else_effect" in d
    back = at.from_dict("Conditional", d)
    assert back == node
    assert at.fingerprint(back) == at.fingerprint(node)
    bare = _conditional_bare()
    assert at.from_dict("Conditional", at.to_dict(bare)) == bare


def test_qprop_counter_count_source_now_builds() -> None:
    """R9b: the r6 qprop_cc_source rejection is superseded — COUNTER_COUNT
    reads the source's counters (Malefic Scythe)."""
    node = _qprop_cc_source()
    d = at.to_dict(node)
    assert d["referent"] == "source"
    assert d["field"] == {"tag": "QPropField", "name": "COUNTER_COUNT"}
    assert at.from_dict("QProp", d) == node


# ---- R7-3 compiler: prefixes + the Otherwise merge -------------------------


def _oid(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012d}"


def _raw_card(name: str, n: int, sentences: tuple[str, ...]) -> RawCard:
    return RawCard(
        identity=CardIdentity(oracle_id=_oid(n), name=name),
        type_line="Instant",
        types=("Instant",),
        subtypes=(),
        supertypes=(),
        colors=(),
        color_identity=frozenset(),
        mana_cost_raw=None,
        mana_value=0,
        power_raw=None,
        toughness_raw=None,
        loyalty_raw=None,
        keywords=(),
        sentences=sentences,
        layout="normal",
        is_token=False,
        is_emblem=False,
        token_name_refs=(),
        related_names=(),
    )


def _template(tid: str, pattern: str, build: Callable[[re.Match[str]], object]):  # type: ignore[type-arg]
    return Template(
        tid=tid,
        name=tid,
        bucket="B5",
        pattern=re.compile(pattern),
        priority=1,
        build=build,  # type: ignore[arg-type]
    )


def test_r8_prefix_registration() -> None:
    assert "Otherwise" in _CONTINUATION_PREFIXES
    assert "When you do" in _CONTINUATION_PREFIXES
    assert _is_continuation("Otherwise, put it on the bottom of your library.")
    assert _is_continuation("When you do, you may tap target creature.")


def test_merge_otherwise_attaches_else_effect() -> None:
    """Top-level Conditional: the merged effect becomes else_effect."""
    merged = _merge_otherwise(_conditional_bare(), _mill_atom())
    assert isinstance(merged, at.Conditional)
    assert merged.else_effect == _mill_atom()
    assert merged.pred == _conditional_bare().pred
    assert merged.then_effect == _draw_atom(1)


def test_merge_otherwise_attaches_in_seq_tail() -> None:
    """Seq idiom "do X. If it's Y, do Z.": the last step's Conditional
    receives the else_effect."""
    seq = at.Seq(steps=(_draw_atom(1), _conditional_bare()))
    merged = _merge_otherwise(seq, _mill_atom())
    assert isinstance(merged, at.Seq)
    last = merged.steps[-1]
    assert isinstance(last, at.Conditional)
    assert last.else_effect == _mill_atom()
    assert merged.steps[0] == _draw_atom(1)


def test_merge_otherwise_c13_fallbacks() -> None:
    """C13: no attachable Conditional (bare Atom / already-else'd
    Conditional) falls back to the DEFAULT merge — never a failure."""
    fallback = _merge_otherwise(_draw_atom(1), _mill_atom())
    assert fallback == at.Seq(steps=(_draw_atom(1), at.OptionalEffect(_mill_atom())))
    taken = _merge_otherwise(_conditional_else(), _mill_atom())
    assert taken == at.Seq(steps=(_conditional_else(), at.OptionalEffect(_mill_atom())))


def test_compile_otherwise_end_to_end() -> None:
    """The Garruk, Savage Herald shape: an If-it's Conditional followed
    by an Otherwise continuation merges into one effect tree."""
    raw = _raw_card(
        "Otherwise Testcard",
        1,
        sentences=(
            "If it's a creature card, draw a card.",
            "Otherwise, mill a card.",
        ),
    )
    reg = TemplateRegistry()
    reg.register(
        _template(
            "r8-if-creature",
            r"^If it's a creature card, draw a card\.$",
            lambda m: EffectOutcome(effect=_conditional_bare()),
        )
    )
    reg.register(
        _template(
            "r8-otherwise-mill",
            r"^Otherwise, mill a card\.$",
            lambda m: EffectOutcome(effect=_mill_atom()),
        )
    )
    res = compile_card(raw, reg)
    assert res.unparsed == ()
    spell = res.card.abilities[0]
    assert isinstance(spell, at.SpellAbility)
    assert isinstance(spell.effect, at.Conditional)
    assert spell.effect.else_effect == _mill_atom()


def test_compile_otherwise_without_conditional_c13() -> None:
    """C13 end-to-end: an Otherwise with no preceding Conditional still
    compiles via the legacy optional-step merge (no parse failure)."""
    raw = _raw_card(
        "Orphan Otherwise",
        2,
        sentences=(
            "Draw a card.",
            "Otherwise, mill a card.",
        ),
    )
    reg = TemplateRegistry()
    reg.register(
        _template(
            "r8-draw",
            r"^Draw a card\.$",
            lambda m: EffectOutcome(effect=_draw_atom(1)),
        )
    )
    reg.register(
        _template(
            "r8-otherwise-mill",
            r"^Otherwise, mill a card\.$",
            lambda m: EffectOutcome(effect=_mill_atom()),
        )
    )
    res = compile_card(raw, reg)
    assert res.unparsed == ()
    spell = res.card.abilities[0]
    assert isinstance(spell, at.SpellAbility)
    assert spell.effect == at.Seq(
        steps=(_draw_atom(1), at.OptionalEffect(_mill_atom()))
    )


# ---- rejections ------------------------------------------------------------


def _rejection_cases() -> list[tuple[str, Callable[[], object]]]:
    return [
        # R7-1: CHOOSE role arity
        (
            "choose_missing_target",
            lambda: at.Atom(at.Verb.CHOOSE, at.AtomArgs(pairs=())),
        ),
        (
            "choose_extra_role",
            lambda: at.Atom(
                at.Verb.CHOOSE,
                at.AtomArgs(pairs=(("target", _pool_sel()), ("cards", _pool_sel()))),
            ),
        ),
        # R7-4: CHOOSE_NAME takes ONLY the optional name_filter
        (
            "choose_name_target_role",
            lambda: at.Atom(
                at.Verb.CHOOSE_NAME,
                at.AtomArgs(pairs=(("target", _target_sel()),)),
            ),
        ),
        (
            "choose_name_bad_filter_type",
            lambda: at.Atom(
                at.Verb.CHOOSE_NAME,
                at.AtomArgs(pairs=(("name_filter", "notabasic"),)),  # type: ignore[list-item]
            ),
        ),
        # R7-8: FIGHT requires target, takes nothing else
        (
            "fight_missing_target",
            lambda: at.Atom(at.Verb.FIGHT, at.AtomArgs(pairs=())),
        ),
        (
            "fight_extra_role",
            lambda: at.Atom(
                at.Verb.FIGHT,
                at.AtomArgs(
                    pairs=(("target", _target_sel()), ("amount", at.QConst(1)))
                ),
            ),
        ),
        # R9a: LOSE_ABILITY mirrors GRANT_ABILITY arity
        (
            "lose_ability_missing_ability",
            lambda: at.Atom(
                at.Verb.LOSE_ABILITY,
                at.AtomArgs(pairs=(("target", _target_sel()),)),
            ),
        ),
        (
            "lose_ability_extra_role",
            lambda: at.Atom(
                at.Verb.LOSE_ABILITY,
                at.AtomArgs(
                    pairs=(
                        ("target", _target_sel()),
                        ("ability", at.KeywordAbility(at.Keyword.INDESTRUCTIBLE)),
                        ("count", at.QConst(1)),
                    )
                ),
            ),
        ),
        # R7-2: DurationUntilLeaves referent vocabulary (C12)
        (
            "dur_leaves_english",
            lambda: at.DurationUntilLeaves(source="this creature"),
        ),
        (
            "dur_leaves_event_ok_but_int",
            lambda: at.DurationUntilLeaves(source=1),  # type: ignore[arg-type]
        ),
        # R7-7: ONE_OF is the TARGET count family
        (
            "one_of_unbounded",
            lambda: at.Selector(
                at.QUnbounded(), at.SelectorMode.ONE_OF, _UNIVERSAL, _BF_YOU
            ),
        ),
        # R7-7: referent selectors keep convention C2 (mode CHOOSE only)
        (
            "rest_referent_selector",
            lambda: at.Selector(
                at.QConst(1),
                at.SelectorMode.REST,
                _UNIVERSAL,
                _NEUTRAL,
                referent="result",
            ),
        ),
        # R7-1: FAtom.referent slot arity + vocabulary
        (
            "is_attached_missing_referent",
            lambda: at.FAtom(at.FAtomPred.IS_ATTACHED_TO),
        ),
        (
            "is_attached_bad_referent_str",
            lambda: at.FAtom(at.FAtomPred.IS_ATTACHED_TO, referent="that card"),
        ),
        (
            "is_attached_unrequested_count",
            lambda: at.FAtom(
                at.FAtomPred.IS_ATTACHED_TO, referent="source", count=at.QConst(1)
            ),
        ),
        (
            "name_chosen_any_slot",
            lambda: at.FAtom(at.FAtomPred.NAME_CHOSEN, referent="result"),
        ),
        # R7-1: "result" rejected outside the vocabulary check path
        (
            "fatom_referent_on_plain_pred",
            lambda: at.FAtom(at.FAtomPred.IS_TAPPED, referent="result"),
        ),
        # R7-5/6: THIS_WAY/THAT_MANY are event-coupled (AMOUNT family)
        (
            "this_way_source_referent",
            lambda: at.QProp(referent="source", field=at.QPropField.THIS_WAY_COUNT),
        ),
        (
            "that_many_result_referent",
            lambda: at.QProp(referent="result", field=at.QPropField.THAT_MANY_COUNT),
        ),
        # R9b: the relaxation is source-only — controller still raises
        (
            "cc_controller_referent",
            lambda: at.QProp(referent="controller", field=at.QPropField.COUNTER_COUNT),
        ),
        # R7-9b boundary: AMOUNT stays strictly event-coupled
        (
            "amount_source_referent",
            lambda: at.QProp(referent="source", field=at.QPropField.AMOUNT),
        ),
    ]


@pytest.mark.parametrize(
    "name,fn", _rejection_cases(), ids=[n for n, _ in _rejection_cases()]
)
def test_r8_rejections(name: str, fn: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        fn()
