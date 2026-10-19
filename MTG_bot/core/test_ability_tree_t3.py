"""Tests for the T3 round-1 grammar additions (KNOWLEDGE/2026-09-19/02).

Items A..N of the binding decision doc:

  A) FAtomPred.POWER_LE / POWER_GE   (power-only comparisons)
  B) FAtomPred.NAME_CONTAINS         (name substring)
  C) Selector.zones                  (additive multi-zone)
  D) Verb.CAST                       (source zone + optional cost role)
  E) QThisTurn + ThisTurnKind        (turn-scoped quantities)
  F) event scoping + CardDrawn / LifeGained / Sacrifice events
  G) Verb.LOSE_GAME                  (no roles)
  H) ZonePosition + Zone.position    (top/bottom of a zone)
  I) EachPlayer                      (per-player effect)
  J) EtBState                        (entered state: tapped/counters)
  K) CostModifier + CostDelta family (continuous cost changes)
  L) EmblemAbility                   (embedded emblem ability)
  M) Verb.PAY                        (pay a cost as an effect)
  N) ControllerRef.OWNER             (owner-scoped zones)

Covers, per the task:

- a PINNED table of pre-T3 tree fingerprints (the byte-stability
  constraint: every tree constructible before this round must keep a
  byte-identical canonical JSON — PC-4/PC-9 rail);
- round-trip (to_dict / from_dict / canonical_json / fingerprint) for
  every new construct;
- the omit-if-empty serialization rule for the new optional fields
  (None / () serializes by omitting the key; non-empty serializes it);
- at least two rejection cases per new construct;
- the verb-role table and FAtom-rule table pins for the new verbs.

PITFALLS observed: assertIs on freshly built frozen dataclasses always
fails — use assertEqual everywhere except enum singletons; PtDelta uses
`magnitude`, not `amount`; repeated `atom.args.get(...)` results are not
pyright-narrowed — bind them to a local first.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

import MTG_bot.core.ability_tree as at
import MTG_bot.core.test_ability_tree as T

# ---- small shared builders (local; T's builders serve the pinned trees) ----

_BF_YOU = at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU)
_BF_ANY = at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.ANY)
_LIB_YOU = at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.YOU)
_LIB_ANY = at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY)
_SRC = at.FAtom(at.FAtomPred.IS_SOURCE)
_PERM = at.FAtom(at.FAtomPred.IS_PERMANENT)
_CREATURE = at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature")


def _src_sel() -> at.Selector:
    return at.Selector(at.QConst(1), at.SelectorMode.ALL, _SRC, zones=(_BF_YOU,))


def _atom_mill() -> at.Atom:
    return at.Atom(
        at.Verb.MILL,
        at.AtomArgs(
            pairs=(("controller", at.ControllerRef.YOU), ("amount", at.QConst(1)))
        ),
    )


# ---- pinned pre-T3 fingerprints (captured before any T3 edit) ----

_PINNED: list[tuple[str, Callable[[], object], str]] = [
    (
        "simple_card",
        T._simple_card,
        "9bd3f0e185eb0f51ca7a99e64f472a22bab2acd4b8cb24582904cc163ffb6a39",
    ),
    (
        "tarmogoyf",
        T._tarmogoyf_like,
        "33c7a673d56fb484966ad1ae25efb1f1ae199c495b02ed44b67c5a11fa3f2679",
    ),
    (
        "planeswalker_emblem",
        T._pw_with_emblem,
        "dd59119e6b0280be53fcaaf8147f15f5d2ea3447ab3a04c44e065182d3ea913c",
    ),
    (
        "token_creator",
        T._token_creator,
        "e0f8c4901870a5f82238fb81b9ed0ac07324e5009b9fb258ce3b0f461b411f4d",
    ),
    (
        "walk_sample",
        T._walk_sample,
        "13e2c77c7d60a54c074aea253f3346db119dec1c91c3d237389ca42da211280b",
    ),
    (
        "src_selector",
        T._src_sel,
        "4ac90dbd56e4a9bfd2722dd000be01ed1e2d0c5b183976744ad6bc8d92b730f8",
    ),
    (
        "cost_empty_tap",
        lambda: at.Cost(parts=(at.CostTap(),)),
        "e0abdee55340cf3c0e076c6a117f03f1ed3deb0b7cc567e8e3d51de39beb98c7",
    ),
    (
        "damage_dealt_event",
        lambda: at.DamageDealtEvent(at.QConst(2), _SRC),
        "2726feecd915cee242244b207e59cb1f05865209dc1ed557e03fa1d18904b23f",
    ),
    (
        "cast_spell_event",
        lambda: at.CastSpellEvent(
            at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Enchantment")
        ),
        "d4f83da545fdf3bdad3de08dbf85237e61e67586d41e33b9538709784a5debb9",
    ),
    (
        "kw_protection",
        lambda: at.KeywordAbility(
            at.Keyword.PROTECTION,
            (at.FAtom(at.FAtomPred.SUBTYPE_EQ, string_value="Demon"),),
        ),
        "d1a1eaf5a54f8af5b59ce70d8e55b189ba8723aeadbff4f4d97d68d49637c19d",
    ),
    (
        "selector_target_battlefield",
        lambda: at.Selector(
            at.QConst(2), at.SelectorMode.TARGET, _PERM, zones=(_BF_ANY,)
        ),
        "74cc8b8b11341e97eddf805d7439ce92cf4b2b97fd5341ecc315468c332d12a5",
    ),
    (
        "fatom_ctrl_count_ge",
        lambda: at.FAtom(
            at.FAtomPred.CONTROLLER_COUNT_GE,
            inner_filter=at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Artifact"),
            count=at.QConst(4),
        ),
        "277d2a43f9017c7e2abff604c07987e83486f5f063b80867d562ddedca821aa3",
    ),
    (
        "triggered_combat_damage",
        lambda: at.TriggeredAbility(
            at.CombatDamageEvent(_SRC),
            None,
            at.OptionalEffect(
                at.Atom(
                    at.Verb.MILL,
                    at.AtomArgs(
                        pairs=(
                            ("controller", at.ControllerRef.YOU),
                            ("amount", at.QConst(2)),
                        )
                    ),
                )
            ),
        ),
        "e7275e247c3ed049f61f6de0e758cf435f272cdc44efda2229c772e14fc695ed",
    ),
    (
        "zone_library_you",
        lambda: at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.YOU),
        "3054a4270f1217312b14d494f65889b1d01fc574556fac88386ccb3ae23f342b",
    ),
]

# The new optional fields that must be ABSENT from every pre-T3 tree's
# serialization (the omit-if-empty rule).
# R0 zone-fold (/129 §1): Selector.zones is NO LONGER omit-if-empty — the
# zones SET is required and always serializes; the amendment below asserts
# the NEW law (Selector carries `zones`, never the deleted `zone` key).
_OMIT_KEYS: dict[str, tuple[str, ...]] = {
    "Zone": ("position",),
    "ZoneChangeEvent": ("subject",),
    "CastSpellEvent": ("actor", "from_zone", "ordinal"),
    "DamageDealtEvent": ("source", "combat"),
}


def _assert_no_t3_keys(d: Any, path: str = "root") -> None:
    """Recursively assert no T3-omittable key appears in a pre-T3 tree.

    R0 zone-fold amendment (/129): every Selector dict carries the ONE
    required `zones` set key and NEVER the deleted scalar `zone` key."""
    if isinstance(d, dict):
        tag = d.get("tag")
        if tag == "Selector":
            assert "zone" not in d, f"R0: {path} carries the deleted 'zone' key"
            assert isinstance(d.get("zones"), list) and d["zones"], (
                f"R0: {path} Selector must carry a non-empty zones set"
            )
        if isinstance(tag, str) and tag in _OMIT_KEYS:
            for key in _OMIT_KEYS[tag]:
                assert key not in d, f"pre-T3 tree {path} carries new key {key!r}"
        for value in d.values():
            _assert_no_t3_keys(value, f"{path}.{tag}")
    elif isinstance(d, list):
        for i, item in enumerate(d):
            _assert_no_t3_keys(item, f"{path}[{i}]")


# ---- round-trip catalogue for every new construct ----


def _multi_zone_two() -> at.Selector:
    """Target player OR planeswalker: PLAYER ∪ BATTLEFIELD."""
    return at.Selector(
        at.QConst(1),
        at.SelectorMode.TARGET,
        at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Player"),
        zones=(at.Zone(at.ZoneKind.PLAYER, at.ControllerRef.ANY), *(_BF_ANY,)),
    )


def _multi_zone_three() -> at.Selector:
    """Library-and-graveyard search: LIBRARY ∪ GRAVEYARD."""
    return at.Selector(
        at.QConst(2),
        at.SelectorMode.CHOOSE,
        at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature"),
        zones=(
            _LIB_ANY,
            *(
                at.Zone(at.ZoneKind.GRAVEYARD, at.ControllerRef.ANY),
                at.Zone(at.ZoneKind.EXILE, at.ControllerRef.ANY),
            ),
        ),
    )


def _cast_top_library() -> at.Atom:
    """CAST the top creature card of your library (Zone.position)."""
    top = at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.YOU, at.ZonePosition.TOP)
    src = at.Selector(at.QConst(1), at.SelectorMode.CHOOSE, _CREATURE, zones=(top,))
    return at.Atom(at.Verb.CAST, at.AtomArgs(pairs=(("source", src),)))


def _cast_waiver() -> at.Atom:
    """CAST with an empty cost = the cost-waiver reading."""
    top = at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.YOU, at.ZonePosition.TOP)
    src = at.Selector(at.QConst(1), at.SelectorMode.CHOOSE, _PERM, zones=(top,))
    return at.Atom(
        at.Verb.CAST,
        at.AtomArgs(pairs=(("source", src), ("cost", at.Cost()))),
    )


def _cast_extra_cost() -> at.Atom:
    """CAST paying an additional 2 life beyond the spell's own cost."""
    src = at.Selector(at.QConst(1), at.SelectorMode.CHOOSE, _PERM, zones=(_LIB_YOU,))
    return at.Atom(
        at.Verb.CAST,
        at.AtomArgs(
            pairs=(
                ("source", src),
                ("cost", at.Cost(parts=(at.CostLife(at.QConst(2)),))),
            )
        ),
    )


def _pay_generic() -> at.Atom:
    """PAY {2} as an effect ("you may pay {2}")."""
    cost = at.Cost(parts=(at.CostManaGeneric(at.QConst(2)),))
    return at.Atom(at.Verb.PAY, at.AtomArgs(pairs=(("cost", cost),)))


def _emblem_triggered() -> at.EmblemAbility:
    emb = at.TriggeredAbility(
        at.TurnPhaseEvent(
            at.Phase.END_TURN,
            at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
        ),
        None,
        _atom_mill(),
    )
    return at.EmblemAbility(emb)


_NEW_NODES: list[tuple[str, Callable[[], object]]] = [
    # A) power-only comparisons
    ("fatom_power_le", lambda: at.FAtom(at.FAtomPred.POWER_LE, count=at.QConst(3))),
    ("fatom_power_ge", lambda: at.FAtom(at.FAtomPred.POWER_GE, count=at.QConst(3))),
    (
        "fatom_power_ge_dynamic",
        lambda: at.FAtom(at.FAtomPred.POWER_GE, count=at.QX()),
    ),
    # B) name substring
    (
        "fatom_name_contains",
        lambda: at.FAtom(at.FAtomPred.NAME_CONTAINS, string_value="Teferi"),
    ),
    # C) additive multi-zone
    ("selector_two_zones", _multi_zone_two),
    ("selector_three_zones", _multi_zone_three),
    # D) Verb.CAST
    ("cast_top_library", _cast_top_library),
    ("cast_waiver", _cast_waiver),
    ("cast_extra_cost", _cast_extra_cost),
    # E) QThisTurn
    (
        "qthisturn_life_gained_you",
        lambda: at.QThisTurn(at.ThisTurnKind.LIFE_GAINED, at.ControllerRef.YOU),
    ),
    (
        "qthisturn_cards_drawn_opp",
        lambda: at.QThisTurn(at.ThisTurnKind.CARDS_DRAWN, at.ControllerRef.OPPONENT),
    ),
    (
        "qthisturn_cards_drawn_all",
        lambda: at.QThisTurn(
            at.ThisTurnKind.CARDS_DRAWN, at.ControllerRef.ALL_OPPONENTS
        ),
    ),
    # F) event extensions + new events
    (
        "cast_evt_controller",
        lambda: at.CastSpellEvent(
            _PERM,
            at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.OPPONENT),
        ),
    ),
    (
        "cast_evt_full",
        lambda: at.CastSpellEvent(
            _PERM,
            at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
            at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY),
            2,
        ),
    ),
    ("cast_evt_ordinal_only", lambda: at.CastSpellEvent(_PERM, ordinal=3)),
    (
        "dd_evt_source_combat",
        lambda: at.DamageDealtEvent(at.QConst(2), _SRC, _PERM, True),
    ),
    (
        "dd_evt_combat_false",
        lambda: at.DamageDealtEvent(at.QConst(1), _SRC, None, False),
    ),
    (
        "zce_subject",
        lambda: at.ZoneChangeEvent(
            at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY),
            _BF_YOU,
            at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature"),
        ),
    ),
    (
        "card_drawn_you",
        lambda: at.CardDrawnEvent(
            at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU)
        ),
    ),
    (
        "card_drawn_opp",
        lambda: at.CardDrawnEvent(
            at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.OPPONENT)
        ),
    ),
    (
        "life_gained_opp",
        lambda: at.LifeGainedEvent(
            at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.OPPONENT)
        ),
    ),
    ("sacrifice_any", lambda: at.SacrificeEvent()),
    (
        "triggered_card_drawn",
        lambda: at.TriggeredAbility(
            at.CardDrawnEvent(
                at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU)
            ),
            None,
            _atom_mill(),
        ),
    ),
    # G) Verb.LOSE_GAME
    (
        "lose_game_atom",
        lambda: at.Atom(at.Verb.LOSE_GAME, at.AtomArgs(pairs=())),
    ),
    (
        "lose_game_in_optional",
        lambda: at.OptionalEffect(at.Atom(at.Verb.LOSE_GAME, at.AtomArgs(pairs=()))),
    ),
    # H) ZonePosition + Zone.position
    (
        "zone_top",
        lambda: at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.YOU, at.ZonePosition.TOP),
    ),
    (
        "zone_bottom",
        lambda: at.Zone(
            at.ZoneKind.GRAVEYARD, at.ControllerRef.OPPONENT, at.ZonePosition.BOTTOM
        ),
    ),
    # I) EachPlayer
    (
        "each_player_opp",
        lambda: at.EachPlayer(at.ControllerRef.ALL_OPPONENTS, _atom_mill()),
    ),
    (
        "each_player_seq",
        lambda: at.EachPlayer(
            at.ControllerRef.ALL_OPPONENTS,
            at.Seq(steps=(_atom_mill(), _atom_mill())),
        ),
    ),
    # J) EtBState
    ("etb_tapped", lambda: at.EtBState(tapped=True)),
    (
        "etb_counters",
        lambda: at.EtBState(
            initial_counters=(
                (at.CounterKind.PLUS_1_PLUS_1, at.QConst(3)),
                (at.CounterKind.SOUL, at.QConst(1)),
            )
        ),
    ),
    (
        "etb_both",
        lambda: at.EtBState(
            tapped=True,
            initial_counters=((at.CounterKind.SOUL, at.QConst(2)),),
        ),
    ),
    # K) CostModifier + the five CostDelta variants
    (
        "costmod_reduce_generic",
        lambda: at.CostModifier(
            at.FAtom(at.FAtomPred.KEYWORD_HAS, keyword=at.Keyword.FLYING),
            at.ControllerRef.YOU,
            at.CostDeltaReduceGeneric(at.QConst(2)),
        ),
    ),
    (
        "costmod_increase_dynamic",
        lambda: at.CostModifier(
            _CREATURE,
            at.ControllerRef.ANY,
            at.CostDeltaIncreaseGeneric(at.QX()),
        ),
    ),
    (
        "costmod_reduce_mana",
        lambda: at.CostModifier(
            _CREATURE,
            at.ControllerRef.YOU,
            at.CostDeltaReduceMana("U", at.QConst(2)),
        ),
    ),
    (
        "costmod_increase_life",
        lambda: at.CostModifier(
            _CREATURE,
            at.ControllerRef.OPPONENT,
            at.CostDeltaIncreaseLife(at.QConst(2)),
        ),
    ),
    (
        "costmod_waive",
        lambda: at.CostModifier(
            at.FAnd(()),
            at.ControllerRef.ANY,
            at.CostDeltaWaiveMana(),
        ),
    ),
    # L) EmblemAbility
    ("emblem_triggered", _emblem_triggered),
    (
        "emblem_static",
        lambda: at.EmblemAbility(at.StaticAbility(_atom_mill())),
    ),
    (
        "emblem_activated",
        lambda: at.EmblemAbility(at.ActivatedAbility(at.Cost(), _atom_mill())),
    ),
    # M) Verb.PAY
    ("pay_generic", _pay_generic),
    ("pay_in_optional", lambda: at.OptionalEffect(_pay_generic())),
    # N) ControllerRef.OWNER
    (
        "zone_owner_hand",
        lambda: at.Zone(at.ZoneKind.HAND, at.ControllerRef.OWNER),
    ),
    (
        "move_to_owner_hand",
        lambda: at.Atom(
            at.Verb.MOVE_ZONE,
            at.AtomArgs(
                pairs=(
                    ("cards", _src_sel()),
                    ("destination", at.Zone(at.ZoneKind.HAND, at.ControllerRef.OWNER)),
                )
            ),
        ),
    ),
]


# ---- rejection catalogue (>= 2 per new construct) ----


def _rejection_cases() -> list[tuple[str, Callable[[], object]]]:
    flying = at.FAtom(at.FAtomPred.KEYWORD_HAS, keyword=at.Keyword.FLYING)
    return [
        # A) POWER_LE / POWER_GE
        (
            "power_le_string_slot",
            lambda: at.FAtom(at.FAtomPred.POWER_LE, string_value="Bird"),
        ),
        (
            "power_ge_color_slot",
            lambda: at.FAtom(at.FAtomPred.POWER_GE, color="B"),
        ),
        # B) NAME_CONTAINS
        ("name_contains_no_arg", lambda: at.FAtom(at.FAtomPred.NAME_CONTAINS)),
        (
            "name_contains_extra_count",
            lambda: at.FAtom(
                at.FAtomPred.NAME_CONTAINS,
                string_value="Teferi",
                count=at.QConst(1),
            ),
        ),
        # C) Selector.zones
        (
            "selector_zones_list",
            lambda: at.Selector(
                at.QConst(1),
                at.SelectorMode.ALL,
                _PERM,
                zones=[_BF_YOU],  # type: ignore[arg-type]  # R0: not a tuple
            ),
        ),
        (
            "selector_zones_empty",
            lambda: at.Selector(
                at.QConst(1),
                at.SelectorMode.ALL,
                _PERM,
                zones=(),  # R0 zone-fold: the set is REQUIRED non-empty
            ),
        ),
        (
            "selector_zones_non_zone",
            lambda: at.Selector(
                at.QConst(1),
                at.SelectorMode.ALL,
                _PERM,
                zones=(_BF_YOU, *(_BF_YOU, "library")),  # type: ignore[arg-type]
            ),
        ),
        # D) Verb.CAST
        ("cast_missing_source", lambda: at.Atom(at.Verb.CAST, at.AtomArgs(pairs=()))),
        (
            "cast_extra_role",
            lambda: at.Atom(
                at.Verb.CAST,
                at.AtomArgs(pairs=(("source", _src_sel()), ("target", _src_sel()))),
            ),
        ),
        # E) QThisTurn
        (
            "qthisturn_kind_str",
            lambda: at.QThisTurn(
                "LIFE_GAINED",  # type: ignore[arg-type]
                at.ControllerRef.YOU,
            ),
        ),
        (
            "qthisturn_referent_str",
            lambda: at.QThisTurn(
                at.ThisTurnKind.LIFE_GAINED,
                "you",  # type: ignore[arg-type]
            ),
        ),
        # F) event extensions + new events
        (
            "cast_evt_ordinal_zero",
            lambda: at.CastSpellEvent(_PERM, ordinal=0),
        ),
        ("cast_evt_ordinal_bool", lambda: at.CastSpellEvent(_PERM, ordinal=True)),
        (
            "cast_evt_from_zone_str",
            lambda: at.CastSpellEvent(_PERM, from_zone="any"),  # type: ignore[arg-type]
        ),
        (
            "dd_evt_combat_str",
            lambda: at.DamageDealtEvent(
                at.QConst(2),
                _SRC,
                None,
                "yes",  # type: ignore[arg-type]
            ),
        ),
        (
            "dd_evt_source_str",
            lambda: at.DamageDealtEvent(
                at.QConst(2),
                _SRC,
                "x",  # type: ignore[arg-type]
                None,
            ),
        ),
        (
            "zce_subject_str",
            lambda: at.ZoneChangeEvent(_LIB_ANY, _BF_YOU, "x"),  # type: ignore[arg-type]
        ),
        ("card_drawn_raw", lambda: at.CardDrawnEvent("you")),  # type: ignore[arg-type]
        (
            "sacrifice_zone",
            lambda: at.SacrificeEvent(_BF_YOU),  # type: ignore[arg-type]
        ),
        # G) Verb.LOSE_GAME
        (
            "lose_game_extra_role",
            lambda: at.Atom(
                at.Verb.LOSE_GAME,
                at.AtomArgs(pairs=(("target", _src_sel()),)),
            ),
        ),
        # H) Zone.position
        (
            "zone_position_str",
            lambda: at.Zone(
                at.ZoneKind.LIBRARY,
                at.ControllerRef.YOU,
                "TOP",  # type: ignore[arg-type]
            ),
        ),
        (
            "zone_position_none_explicit_ok",
            lambda: at.Zone(
                at.ZoneKind.LIBRARY, at.ControllerRef.YOU, None
            ),  # legal: None == the zone as a whole
        ),
        # I) EachPlayer
        (
            "each_player_ref_str",
            lambda: at.EachPlayer("you", _atom_mill()),  # type: ignore[arg-type]
        ),
        (
            "each_player_effect_str",
            lambda: at.EachPlayer(
                at.ControllerRef.ALL_OPPONENTS,
                "mill",  # type: ignore[arg-type]
            ),
        ),
        # J) EtBState
        ("etb_noop", lambda: at.EtBState()),
        (
            "etb_tapped_str",
            lambda: at.EtBState(
                tapped="yes",  # type: ignore[arg-type]
            ),
        ),
        (
            "etb_bad_entry_len",
            lambda: at.EtBState(
                initial_counters=("SOUL",),  # type: ignore[arg-type]
            ),
        ),
        (
            "etb_bad_count_type",
            lambda: at.EtBState(
                initial_counters=((at.CounterKind.SOUL, "3"),),  # type: ignore[arg-type]
            ),
        ),
        (
            "etb_counters_list",
            lambda: at.EtBState(
                initial_counters=[(at.CounterKind.SOUL, at.QConst(1))],  # type: ignore[arg-type]
            ),
        ),
        # K) CostModifier + CostDelta
        (
            "costmod_delta_quantity",
            lambda: at.CostModifier(
                flying,
                at.ControllerRef.YOU,
                at.QConst(1),  # type: ignore[arg-type]
            ),
        ),
        (
            "costmod_ref_str",
            lambda: at.CostModifier(
                flying,
                "you",  # type: ignore[arg-type]
                at.CostDeltaWaiveMana(),
            ),
        ),
        (
            "deltamana_bad_color",
            lambda: at.CostDeltaReduceMana("Q", at.QConst(1)),
        ),
        (
            "deltalife_bad_amount",
            lambda: at.CostDeltaIncreaseLife(
                "2",  # type: ignore[arg-type]
            ),
        ),
        # L) EmblemAbility
        (
            "emblem_not_ability",
            lambda: at.EmblemAbility(
                _atom_mill(),  # type: ignore[arg-type]
            ),
        ),
        (
            "emblem_str",
            lambda: at.EmblemAbility(
                "x",  # type: ignore[arg-type]
            ),
        ),
        # M) Verb.PAY
        ("pay_missing_cost", lambda: at.Atom(at.Verb.PAY, at.AtomArgs(pairs=()))),
        (
            "pay_cost_wrong_type",
            lambda: at.Atom(
                at.Verb.PAY,
                at.AtomArgs(pairs=(("cost", at.QConst(2)),)),
            ),
        ),
        # serialization strictness on the new tags
        (
            "fromdict_qthisturn_missing",
            lambda: at.from_dict(
                "QThisTurn",
                {
                    "tag": "QThisTurn",
                    "referent": {"tag": "ControllerRef", "name": "YOU"},
                },
            ),
        ),
        (
            "fromdict_castevt_missing_filter",
            lambda: at.from_dict("CastSpellEvent", {"tag": "CastSpellEvent"}),
        ),
        (
            "fromdict_etb_missing_counters",
            lambda: at.from_dict("EtBState", {"tag": "EtBState", "tapped": True}),
        ),
        (
            "fromdict_etb_bad_placement",
            lambda: at.from_dict(
                "EtBState",
                {"tag": "EtBState", "tapped": False, "initial_counters": [["SOUL"]]},
            ),
        ),
        (
            "fromdict_selector_bad_zone_in_zones",
            lambda: at.from_dict(
                "Selector",
                {
                    **at.to_dict(_src_sel()),
                    "zones": [
                        {
                            "tag": "Zone",
                            "kind": {"tag": "ZoneKind", "name": "LIBRARY"},
                            "controller": "you",
                        }
                    ],
                },
            ),
        ),
    ]


# ---- tests ----


@pytest.mark.parametrize("name,build,fp", _PINNED, ids=[n for n, _, _ in _PINNED])
def test_pinned_pre_t3_fingerprint(
    name: str, build: Callable[[], object], fp: str
) -> None:
    node = build()
    assert at.fingerprint(node) == fp
    _assert_no_t3_keys(at.to_dict(node))


@pytest.mark.parametrize("name,build", _NEW_NODES, ids=[n for n, _ in _NEW_NODES])
def test_t3_roundtrip(name: str, build: Callable[[], object]) -> None:
    node = build()
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d, (
        f"{name}: to_dict must yield a tagged dict"
    )
    back = at.from_dict(str(d["tag"]), d)
    assert back == node, f"{name}: from_dict(to_dict(x)) != x"
    assert at.canonical_json(back) == at.canonical_json(node)
    assert at.fingerprint(back) == at.fingerprint(node)


@pytest.mark.parametrize(
    "name,fn", _rejection_cases(), ids=[n for n, _ in _rejection_cases()]
)
def test_t3_rejections(name: str, fn: Callable[[], object]) -> None:
    # zone_position_none_explicit_ok is the one legal edge in the list
    if name == "zone_position_none_explicit_ok":
        node = fn()
        assert isinstance(node, at.Zone) and node.position is None
        return
    with pytest.raises(ValueError):
        fn()


def test_omit_keys_present_when_set() -> None:
    d = at.to_dict(_multi_zone_two())
    # R0 zone-fold: PLAYER ∪ BATTLEFIELD is ONE set of two (was primary
    # + one extra); membership form — canonical order is schema-enforced.
    assert "zones" in d and len(d["zones"]) == 2
    by_json = lambda z: json.dumps(z, sort_keys=True)  # noqa: E731
    assert sorted(d["zones"], key=by_json) == sorted(
        [
            at.to_dict(at.Zone(at.ZoneKind.PLAYER, at.ControllerRef.ANY)),
            at.to_dict(at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.ANY)),
        ],
        key=by_json,
    )
    assert sorted(at.to_dict(_multi_zone_three())["zones"], key=by_json) == sorted(
        [
            # NOTE: the fixture's first member is the ANY-kind zone
            # (_LIB_ANY = Zone(ANY, ANY)), not LIBRARY — assert truth.
            at.to_dict(at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY)),
            at.to_dict(at.Zone(at.ZoneKind.GRAVEYARD, at.ControllerRef.ANY)),
            at.to_dict(at.Zone(at.ZoneKind.EXILE, at.ControllerRef.ANY)),
        ],
        key=by_json,
    )
    assert at.to_dict(
        at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.YOU, at.ZonePosition.TOP)
    )["position"] == {"tag": "ZonePosition", "name": "TOP"}
    d = at.to_dict(
        at.CastSpellEvent(
            _PERM,
            at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
            None,
            2,
        )
    )
    assert d["ordinal"] == 2
    assert d["actor"]["who"] == {"tag": "ControllerRef", "name": "YOU"}
    assert "from_zone" not in d
    d = at.to_dict(at.DamageDealtEvent(at.QConst(2), _SRC, None, False))
    assert d["combat"] is False
    assert "source" not in d


def test_omit_keys_absent_by_default() -> None:
    d = at.to_dict(_src_sel())
    # R0 zone-fold: zones is REQUIRED (always serialized) and the deleted
    # scalar must stay deleted on every path.
    assert "zone" not in d and d["zones"]
    assert "position" not in at.to_dict(_BF_YOU)
    assert "subject" not in at.to_dict(at.ZoneChangeEvent(_LIB_ANY, _BF_YOU))
    d = at.to_dict(at.CastSpellEvent(_PERM))
    assert "controller" not in d and "from_zone" not in d and "ordinal" not in d
    d = at.to_dict(at.DamageDealtEvent(at.QConst(2), _SRC))
    assert "source" not in d and "combat" not in d


def test_explicit_empty_omit_fields_decode() -> None:
    # A hand-built tagged dict that spells the empty defaults out loud
    # must decode to the same node as the omitted form (value equality).
    # R0 zone-fold: zones left the omit table — the explicit EMPTY form
    # now FAILS LOUD (no silent migration of pre-R0 bytes).
    sel = _src_sel()
    d = at.to_dict(sel)
    d["zones"] = []
    with pytest.raises(ValueError, match="non-empty"):
        at.from_dict("Selector", d)
    z = _BF_YOU
    d2 = at.to_dict(z)
    d2["position"] = None
    assert at.from_dict("Zone", d2) == z


def test_new_verb_roles() -> None:
    assert at._VERB_ROLES[at.Verb.CAST] == {"source": True, "cost": False}
    assert at._VERB_ROLES[at.Verb.PAY] == {"cost": True}
    assert at._VERB_ROLES[at.Verb.LOSE_GAME] == {}


def test_new_fatom_rule_rows() -> None:
    rules = at._FATOM_RULES
    assert rules[at.FAtomPred.POWER_LE] == (
        frozenset({"count"}),
        frozenset({"count"}),
    )
    assert rules[at.FAtomPred.POWER_GE] == (
        frozenset({"count"}),
        frozenset({"count"}),
    )
    assert rules[at.FAtomPred.NAME_CONTAINS] == (
        frozenset({"string_value"}),
        frozenset({"string_value"}),
    )


def test_new_enum_members() -> None:
    assert at.ZonePosition.TOP.value == "TOP"
    assert at.ZonePosition.BOTTOM.value == "BOTTOM"
    assert at.ThisTurnKind.LIFE_GAINED.value == "LIFE_GAINED"
    assert at.ThisTurnKind.CARDS_DRAWN.value == "CARDS_DRAWN"
    assert at.ControllerRef.OWNER.value == "OWNER"
    assert {v.name for v in at.Verb} >= {"CAST", "PAY", "LOSE_GAME"}


def test_fingerprint_sensitivity_new_fields() -> None:
    base = at.Selector(at.QConst(1), at.SelectorMode.TARGET, _PERM, zones=(_BF_ANY,))
    widened = at.Selector(
        at.QConst(1),
        at.SelectorMode.TARGET,
        _PERM,
        zones=(_BF_ANY, *(at.Zone(at.ZoneKind.STACK, at.ControllerRef.ANY),)),
    )
    assert at.fingerprint(base) != at.fingerprint(widened)
    assert at.fingerprint(
        at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.YOU, at.ZonePosition.TOP)
    ) != at.fingerprint(
        at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.YOU, at.ZonePosition.BOTTOM)
    )
    assert at.fingerprint(
        at.QThisTurn(at.ThisTurnKind.LIFE_GAINED, at.ControllerRef.YOU)
    ) != at.fingerprint(at.QThisTurn(at.ThisTurnKind.CARDS_DRAWN, at.ControllerRef.YOU))
    assert at.fingerprint(at.EtBState(tapped=True)) != at.fingerprint(
        at.EtBState(
            tapped=False,
            initial_counters=((at.CounterKind.SOUL, at.QConst(1)),),
        )
    )


def test_walk_visits_etb_counters() -> None:
    etb = at.EtBState(initial_counters=((at.CounterKind.SOUL, at.QConst(2)),))
    visited = list(at.walk(etb))
    assert visited[0] is etb
    assert any(isinstance(v, at.QConst) and v.value == 2 for v in visited)


def test_cast_source_role_is_selector() -> None:
    atom = _cast_top_library()
    src = atom.args.get("source")
    assert isinstance(src, at.Selector)
    assert src.zones[0] == at.Zone(
        at.ZoneKind.LIBRARY, at.ControllerRef.YOU, at.ZonePosition.TOP
    )
    # the optional cost role decodes as a Cost when present
    cost = _cast_waiver().args.get("cost")
    assert isinstance(cost, at.Cost) and cost.parts == ()


def test_new_nodes_in_closed_tables() -> None:
    specs = at._SPECS
    for tag in (
        "QThisTurn",
        "CardDrawnEvent",
        "LifeGainedEvent",
        "SacrificeEvent",
        "CostDeltaReduceGeneric",
        "CostDeltaIncreaseGeneric",
        "CostDeltaReduceMana",
        "CostDeltaIncreaseLife",
        "CostDeltaWaiveMana",
        "EachPlayer",
        "CostModifier",
        "EtBState",
        "EmblemAbility",
    ):
        assert tag in specs, f"{tag} missing from _SPECS"
    assert at._TAG[at.QThisTurn] == "QThisTurn"
    assert at._TAG[at.EmblemAbility] == "EmblemAbility"
