"""T3 round 5 — five additive grammar items (2026-09-24).

Round-5 scope (spec: KNOWLEDGE/2026-09-24/05-grammar-round4-decision.md):

- R4-1: ``CardDrawnEvent.ordinal: int | None = None`` — "whenever you draw
  your second card each turn" (Jolrael, Mwonvuli Recluse; Mystic Skyfish);
  ``opt:int`` + omit-if-empty; mirrors ``CastSpellEvent.ordinal``.
- R4-2: new event ``LoyaltyActivatedEvent(filter, actor)`` — "whenever
  you activate a loyalty ability of a Chandra planeswalker" (Keral Keep
  Disciples); added to the ``EventSpec`` union + serialization tag; filter
  required; convention C5 (the loyalty trigger compiles as the effect of the
  ActivatedAbility whose cost is the loyalty part).
- R4-3: ``CastSpellEvent.from_zone_not: Zone | None = None`` — "from anywhere
  other than their hand" (Ghostly Pilferer); mutually exclusive with
  ``from_zone``; omit-if-None.
- R4-4: three new ``FAtomPred``s, each with a closed per-predicate slot set —
  ``ENTERED_THIS_TURN_FROM`` {zone}, ``CAST_THIS_TURN_FROM`` {zone, who},
  ``MOVED_TO_ZONE_THIS_TURN`` {from_zone, to_zone, who}.
- R4-5: object anaphora (one closed vocabulary, ``_QPROP_STR_REFERENTS``) —
  (a) ``Selector.referent: str | None`` (convention C2: mode CHOOSE +
  count QConst(1) + the neutral zone + empty zones); (b)
  ``_ROLE_TYPES["controller"]`` widened to ``(ControllerRef, Selector)``;
  (c) ``CONTROLLER_IS`` ``who`` widened to accept a referent Selector.

Guards:
- every pre-round-5 pinned fingerprint (the round-4 pin set) stays
  byte-identical — all five items are additive optional slots/events/enums;
- bare constructs (ordinal=None / from_zone_not=None / referent=None / no
  zone slots) serialize WITHOUT the new keys;
- round-5 constructs round-trip through ``to_dict``/``from_dict`` with
  pinned fingerprints;
- rejections at every new or widened validation point (``ValueError``,
  per the module-wide convention).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

import MTG_bot.core.ability_tree as at
import MTG_bot.core.test_ability_tree_r4 as R4

# ---- builders for the round-5 constructs -----------------------------------

_BF_YOU = at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU)
_GY_YOU = at.Zone(at.ZoneKind.GRAVEYARD, at.ControllerRef.YOU)
_HAND_YOU = at.Zone(at.ZoneKind.HAND, at.ControllerRef.YOU)
_NEUTRAL = at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY)
_CREATURE = at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature")
_UNIVERSAL = at.FAnd(())


def _chandra_filter() -> at.FAnd:
    """Subtype Chandra + type Planeswalker (Keral Keep Disciples)."""
    return at.FAnd(
        (
            at.FAtom(at.FAtomPred.SUBTYPE_EQ, string_value="Chandra"),
            at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Planeswalker"),
        )
    )


def _cd_bare() -> at.CardDrawnEvent:
    """Pre-round-5 shape: no ordinal key in the serialization."""
    return at.CardDrawnEvent(
        at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU)
    )


def _cd_second() -> at.CardDrawnEvent:
    """R4-1: 'your second card each turn' (Jolrael, Mystic Skyfish)."""
    return at.CardDrawnEvent(
        at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU), ordinal=2
    )


def _loyalty() -> at.LoyaltyActivatedEvent:
    """R4-2: 'you activate a loyalty ability of a Chandra planeswalker'."""
    return at.LoyaltyActivatedEvent(
        _chandra_filter(),
        actor=at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
    )


def _cast_bare() -> at.CastSpellEvent:
    """Pre-round-5 shape: no from_zone_not key in the serialization."""
    return at.CastSpellEvent(_UNIVERSAL)


def _cast_from_hand() -> at.CastSpellEvent:
    """Pre-round-5 shape: the affirmative from_zone scope."""
    return at.CastSpellEvent(
        _UNIVERSAL,
        actor=at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.OPPONENT),
        from_zone=_HAND_YOU,
    )


def _cast_not_hand() -> at.CastSpellEvent:
    """R4-3: 'an opponent casts a spell from anywhere other than their hand'."""
    return at.CastSpellEvent(
        _UNIVERSAL,
        actor=at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.OPPONENT),
        from_zone_not=_HAND_YOU,
    )


def _fatom_entered_gy() -> at.FAtom:
    """R4-4(1): 'entered from your graveyard' (Archfiend's Vessel)."""
    return at.FAtom(at.FAtomPred.ENTERED_THIS_TURN_FROM, zone=_GY_YOU)


def _fatom_cast_gy() -> at.FAtom:
    """R4-4(2): 'you cast it from your graveyard' (Archfiend's Vessel)."""
    return at.FAtom(
        at.FAtomPred.CAST_THIS_TURN_FROM, zone=_GY_YOU, who=at.ControllerRef.YOU
    )


def _fatom_moved() -> at.FAtom:
    """R4-4(3): 'a permanent was put into your hand from the battlefield
    this turn' (Barrin, Tolarian Archmage)."""
    return at.FAtom(
        at.FAtomPred.MOVED_TO_ZONE_THIS_TURN,
        from_zone=_BF_YOU,
        to_zone=_HAND_YOU,
        who=at.ControllerRef.YOU,
    )


def _sel_event() -> at.Selector:
    """R4-5(a): the triggering event's subject object (Gloom Sower /
    Double Vision)."""
    return at.Selector(
        at.QConst(1), at.SelectorMode.CHOOSE, _UNIVERSAL, zones=(_NEUTRAL,), referent="event"
    )


def _sel_controller() -> at.Selector:
    """R4-5(c): 'that player controls' (Feline Sovereign) — the who slot
    of CONTROLLER_IS takes a referent Selector."""
    return at.Selector(
        at.QConst(1),
        at.SelectorMode.CHOOSE,
        _CREATURE,
        zones=(_NEUTRAL,),
        referent="controller",
    )


def _gloom_sower() -> at.Atom:
    """R4-5(b): 'its controller loses N' — the controller role takes the
    referent Selector bound to the triggering event's subject."""
    return at.Atom(
        at.Verb.LOSE_LIFE,
        at.AtomArgs(pairs=(("controller", _sel_event()), ("amount", at.QConst(3)))),
    )


def _feline_controller_is() -> at.FAtom:
    """R4-5(c): 'that player controls' — CONTROLLER_IS with a referent who."""
    return at.FAtom(at.FAtomPred.CONTROLLER_IS, who=_sel_controller())


# ---- pinned fingerprints (captured after the round-5 edits) ----------------

_NEW_PINS: list[tuple[str, Callable[[], object], str]] = [
    (
        "cd_bare",
        _cd_bare,
        "33fcfb2b9b961b3518a12e1a413b25ab16f05d038d0e93961058bf6e7d1635dc",
    ),
    (
        "cd_second",
        _cd_second,
        "88d96d8de636ca82d3978353101531bf7e5449f6856650c295ca764cec350431",
    ),
    (
        "loyalty",
        _loyalty,
        "a91d56dd470a01e979e6bdfecbf77b81fae89ef0c15cfd0dfc01b0a3af2ffd82",
    ),
    (
        "cast_bare",
        _cast_bare,
        "128db1cd57746ac9fbcf2264ac774d78fc60a86ec5cf9c7f459618e988f35a5e",
    ),
    (
        "cast_from_hand",
        _cast_from_hand,
        "9cfd6e70171a0e232e733e292776109af5cfb28dd46f0bcb8896037c954088fa",
    ),
    (
        "cast_not_hand",
        _cast_not_hand,
        "e7911664ff47fa0acc257d7ee4b39597304d808599fb676fa3e342022c5463e5",
    ),
    (
        "fatom_entered_gy",
        _fatom_entered_gy,
        "659d17b82ac3909805ac20f5d5072befdde2fcb941246493e506a326c3ee8452",
    ),
    (
        "fatom_cast_gy",
        _fatom_cast_gy,
        "91d2371202a374f10f293e027dd7d3d9a451422b0387e898d97c51a830123cf5",
    ),
    (
        "fatom_moved",
        _fatom_moved,
        "85c3aaebd5cf05b38cc962da79b8c28369a3ed792e224d6117f92be0b7429fbd",
    ),
    (
        "sel_event",
        _sel_event,
        "70cd76cc40df3d5a35a93d5b816d57c00b9328266b99cd722c9fb93148843794",
    ),
    (
        "sel_controller",
        _sel_controller,
        "70d138ffd4e1dd0780d5ea113fb09eda05826f98be02dec4960d020df4681e88",
    ),
    (
        "gloom_sower",
        _gloom_sower,
        "a5312ea8193952b2f7b5e35203346c43497d8aa867dc774601c915aa95782e3f",
    ),
    (
        "feline_controller_is",
        _feline_controller_is,
        "a271c8eb44cf0ad7f69a40ca910eda20e266609ab13e1a19f272c1f5b24de40a",
    ),
]


# ---- tests ----------------------------------------------------------------


@pytest.mark.parametrize(
    "name,build,fp", R4._NEW_PINS, ids=[n for n, _, _ in R4._NEW_PINS]
)
def test_pinned_pre_r5_fingerprint(
    name: str, build: Callable[[], object], fp: str
) -> None:
    """Byte stability: every pre-round-5 pinned tree (the round-4 pin set)
    serializes identically — all five round-5 items are additive."""
    node = build()
    assert at.fingerprint(node) == fp
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d


@pytest.mark.parametrize("name,build,fp", _NEW_PINS, ids=[n for n, _, _ in _NEW_PINS])
def test_r5_roundtrip(name: str, build: Callable[[], object], fp: str) -> None:
    node = build()
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d
    back = at.from_dict(d["tag"], d)
    assert back == node, f"{name}: from_dict(to_dict(x)) != x"
    assert at.canonical_json(back) == at.canonical_json(node)
    assert at.fingerprint(back) == at.fingerprint(node) == fp


def test_carddrawn_omits_ordinal_when_none() -> None:
    d = at.to_dict(_cd_bare())
    assert set(d.keys()) == {"tag", "actor"}, (
        f"bare CardDrawnEvent must omit 'ordinal': {sorted(d)}"
    )
    d = at.to_dict(_cd_second())
    assert d["ordinal"] == 2


def test_carddrawn_explicit_none_equals_default() -> None:
    explicit = at.CardDrawnEvent(
        at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
        ordinal=None,
    )
    default = _cd_bare()
    assert explicit == default
    assert at.to_dict(explicit) == at.to_dict(default)
    assert at.fingerprint(explicit) == at.fingerprint(default)
    back = at.from_dict("CardDrawnEvent", at.to_dict(default))
    assert back.ordinal is None


def test_castspell_omits_from_zone_not_when_none() -> None:
    d = at.to_dict(_cast_bare())
    assert "from_zone_not" not in d, (
        f"bare CastSpellEvent must omit 'from_zone_not': {sorted(d)}"
    )
    d = at.to_dict(_cast_from_hand())
    assert "from_zone" in d and "from_zone_not" not in d
    d = at.to_dict(_cast_not_hand())
    assert "from_zone_not" in d and "from_zone" not in d


def test_selector_omits_referent_when_none() -> None:
    bare = at.Selector(at.QConst(1), at.SelectorMode.TARGET, _CREATURE, zones=(_BF_YOU,))
    d = at.to_dict(bare)
    assert "referent" not in d, f"bare Selector must omit 'referent': {sorted(d)}"
    d = at.to_dict(_sel_event())
    assert d["referent"] == "event"


def test_fatom_omits_zone_slots_when_absent() -> None:
    d = at.to_dict(_CREATURE)
    for key in ("zone", "from_zone", "to_zone"):
        assert key not in d, (
            f"bare FAtom must omit the round-5 zone slot {key!r}: {sorted(d)}"
        )
    d = at.to_dict(_fatom_entered_gy())
    assert "zone" in d and "from_zone" not in d and "to_zone" not in d
    d = at.to_dict(_fatom_moved())
    assert "from_zone" in d and "to_zone" in d and "zone" not in d


def test_r5_enum_and_table_members() -> None:
    assert at.FAtomPred.ENTERED_THIS_TURN_FROM.value == "ENTERED_THIS_TURN_FROM"
    assert at.FAtomPred.CAST_THIS_TURN_FROM.value == "CAST_THIS_TURN_FROM"
    assert at.FAtomPred.MOVED_TO_ZONE_THIS_TURN.value == "MOVED_TO_ZONE_THIS_TURN"
    assert at._FATOM_RULES[at.FAtomPred.ENTERED_THIS_TURN_FROM] == (
        frozenset({"zone"}),
        frozenset({"zone"}),
    )
    assert at._FATOM_RULES[at.FAtomPred.CAST_THIS_TURN_FROM] == (
        frozenset({"zone", "who"}),
        frozenset({"zone", "who"}),
    )
    assert at._FATOM_RULES[at.FAtomPred.MOVED_TO_ZONE_THIS_TURN] == (
        frozenset({"from_zone", "to_zone", "who"}),
        frozenset({"from_zone", "to_zone", "who"}),
    )
    assert at._ROLE_TYPES["controller"] == (at.ControllerRef, at.Selector)
    # "result" appended by grammar round 7, R7-1 (anaphora to the object(s)
    # the previous sentence acted on); the pre-round-7 four are order-pinned.
    assert at._QPROP_STR_REFERENTS == (
        "source",
        "controller",
        "target",
        "event",
        "result",
    )


def test_loyalty_activated_event_union_membership() -> None:
    """R4-2: LoyaltyActivatedEvent is registered as a legal event spec and
    carries its own serialization tag."""
    node = _loyalty()
    assert type(node) in at._DATACLASSES
    assert type(node) in at._EV_CLASSES
    assert "LoyaltyActivatedEvent" in at._EVENT_TAGS
    d = at.to_dict(node)
    assert d["tag"] == "LoyaltyActivatedEvent"
    assert at.from_dict("LoyaltyActivatedEvent", d) == node


def test_role_union_controller_selector_roundtrip() -> None:
    """R4-5(b): the controller role accepts a referent Selector; the
    pre-round-5 ControllerRef value still round-trips alongside it."""
    node = _gloom_sower()
    d = at.to_dict(node)
    back = at.from_dict(d["tag"], d)
    assert back == node
    controller_value = dict(back.args.pairs)["controller"]
    assert isinstance(controller_value, at.Selector)
    assert controller_value.referent == "event"
    # the plain-ControllerRef spelling of the same role still works
    plain = at.Atom(
        at.Verb.LOSE_LIFE,
        at.AtomArgs(
            pairs=(("controller", at.ControllerRef.YOU), ("amount", at.QConst(3)))
        ),
    )
    assert at.from_dict("Atom", at.to_dict(plain)) == plain


def _rejection_cases() -> list[tuple[str, Callable[[], object]]]:
    return [
        # R4-1: CardDrawnEvent.ordinal validation
        (
            "cd_ordinal_zero",
            lambda: at.CardDrawnEvent(
                at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
                ordinal=0,
            ),
        ),
        (
            "cd_ordinal_negative",
            lambda: at.CardDrawnEvent(
                at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
                ordinal=-1,
            ),
        ),
        (
            "cd_ordinal_bool",
            lambda: at.CardDrawnEvent(
                at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
                ordinal=True,
            ),  # type: ignore[arg-type]
        ),
        (
            "cd_ordinal_str",
            lambda: at.CardDrawnEvent(
                at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
                ordinal="2",
            ),  # type: ignore[arg-type]
        ),
        # R4-2: LoyaltyActivatedEvent validation (E1: actor slot)
        (
            "loyalty_bad_actor",
            lambda: at.LoyaltyActivatedEvent(_chandra_filter(), "you"),  # type: ignore[arg-type]
        ),
        (
            "loyalty_bad_filter",
            lambda: at.LoyaltyActivatedEvent(
                "Chandra",
                actor=at.FAtom(
                    pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU
                ),
            ),  # type: ignore[arg-type]
        ),
        # R4-3: CastSpellEvent.from_zone_not mutual exclusion
        (
            "cast_both_from_zones",
            lambda: at.CastSpellEvent(
                _UNIVERSAL, from_zone=_HAND_YOU, from_zone_not=_HAND_YOU
            ),
        ),
        (
            "cast_from_zone_not_not_zone",
            lambda: at.CastSpellEvent(
                _UNIVERSAL,
                from_zone_not="hand",  # type: ignore[arg-type]
            ),
        ),
        # R4-4: the three new FAtomPred slot arities
        (
            "fatom_entered_missing_zone",
            lambda: at.FAtom(at.FAtomPred.ENTERED_THIS_TURN_FROM),
        ),
        (
            "fatom_cast_missing_zone",
            lambda: at.FAtom(
                at.FAtomPred.CAST_THIS_TURN_FROM, who=at.ControllerRef.YOU
            ),
        ),
        (
            "fatom_cast_missing_who",
            lambda: at.FAtom(at.FAtomPred.CAST_THIS_TURN_FROM, zone=_GY_YOU),
        ),
        (
            "fatom_moved_missing_from_zone",
            lambda: at.FAtom(
                at.FAtomPred.MOVED_TO_ZONE_THIS_TURN,
                to_zone=_HAND_YOU,
                who=at.ControllerRef.YOU,
            ),
        ),
        (
            "fatom_moved_missing_to_zone",
            lambda: at.FAtom(
                at.FAtomPred.MOVED_TO_ZONE_THIS_TURN,
                from_zone=_BF_YOU,
                who=at.ControllerRef.YOU,
            ),
        ),
        (
            "fatom_moved_unrequested_zone",
            lambda: at.FAtom(
                at.FAtomPred.MOVED_TO_ZONE_THIS_TURN,
                from_zone=_BF_YOU,
                to_zone=_HAND_YOU,
                who=at.ControllerRef.YOU,
                zone=_GY_YOU,
            ),
        ),
        (
            "fatom_entered_unrequested_who",
            lambda: at.FAtom(
                at.FAtomPred.ENTERED_THIS_TURN_FROM,
                zone=_GY_YOU,
                who=at.ControllerRef.YOU,
            ),
        ),
        (
            "fatom_cast_unrequested_count",
            lambda: at.FAtom(
                at.FAtomPred.CAST_THIS_TURN_FROM,
                zone=_GY_YOU,
                who=at.ControllerRef.YOU,
                count=at.QConst(1),
            ),
        ),
        # R4-5: referent Selector convention C2 + vocabulary
        (
            "sel_referent_bad_vocab",
            lambda: at.Selector(
                at.QConst(1),
                at.SelectorMode.CHOOSE,
                _UNIVERSAL,
                zones=(_NEUTRAL,),
                referent="bogus",
            ),
        ),
        (
            "sel_referent_bad_mode",
            lambda: at.Selector(
                at.QConst(1),
                at.SelectorMode.TARGET,
                _UNIVERSAL,
                zones=(_NEUTRAL,),
                referent="event",
            ),
        ),
        (
            "sel_referent_bad_count",
            lambda: at.Selector(
                at.QConst(2),
                at.SelectorMode.CHOOSE,
                _UNIVERSAL,
                zones=(_NEUTRAL,),
                referent="event",
            ),
        ),
        (
            "sel_referent_non_neutral_zone",
            lambda: at.Selector(
                at.QConst(1),
                at.SelectorMode.CHOOSE,
                _UNIVERSAL,
                zones=(_BF_YOU,),
                referent="event",
            ),
        ),
        (
            "sel_referent_nonempty_zones",
            lambda: at.Selector(
                at.QConst(1),
                at.SelectorMode.CHOOSE,
                _UNIVERSAL,
                zones=(_NEUTRAL, *(_BF_YOU,)),
                referent="event",
            ),
        ),
        # R4-5(c): CONTROLLER_IS must reject a Selector that is NOT a referent
        (
            "controller_is_non_referent_selector",
            lambda: at.FAtom(
                at.FAtomPred.CONTROLLER_IS,
                who=at.Selector(
                    at.QConst(1), at.SelectorMode.CHOOSE, _CREATURE, zones=(_BF_YOU,)
                ),
            ),
        ),
    ]


@pytest.mark.parametrize(
    "name,fn", _rejection_cases(), ids=[n for n, _ in _rejection_cases()]
)
def test_r5_rejections(name: str, fn: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        fn()
