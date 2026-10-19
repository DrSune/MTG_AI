"""Grammar round 9 / phase 9-A — nine additive items + the Do-merge (2026-09-28).

Round-9 scope (spec: KNOWLEDGE 2026-09-28/11; file-name offset is
intentional — round-9 grammar ships in the r10 file, following the
r6-in-r7 / r7-in-r8 / r8-in-r9 precedent):

- R9-1: ``ActivationWindow`` + ``ActivatedAbility.timing`` trailing
  optional (C20: "Activate only as a sorcery" — Steward class). The
  omit-when-None rule is DUAL-registered (_SPECS opt-tag + the NEW
  _OMIT_IF_EMPTY ActivatedAbility row {condition, timing}); the bare
  activation byte-shape pin below is the golden-storm guard.
- R9-2: ``FAtomPred.LIFE_LEAD_OVER_START_GE`` — count-only rule
  ({count}={count}), the net-life-lead predicate ("Speaker of the
  Heavens" class).
- R9-3: ``Verb.MANA_POLICY`` {scope, filter?} — the closed
  ``_MANA_POLICY_SCOPES`` vocabulary (C21: THIS_MANA event-anchored vs
  ALL_YOURS permission), AtomArgs validates scope strings against it.
- R9-4: ``Step.UNTAP`` + ``DurationUntilNextStep`` (owner_scoped, Frost
  Breath) + the PREVENT_EFFECT ``step`` role (R9-4 doc /10 pairing).
- R9-5: ``DelayedTrigger`` — a new Effect-union member living INSIDE its
  creator (C22: the duration is REQUIRED — a lifetime-less delayed
  trigger is just a TriggeredAbility).
- R9-6: ``QDistinctColorCount`` — distinct-colour count over a Selector
  (Orrery), QCount's registration shape mirrored.
- R9-7: ``Verb.GRANT_ACTIVATION`` {filter, window?} — the Teferi
  NAME_CONTAINS gate + the R9-1 window the extra activation joins.
- R9-8: REVEAL ``duration`` role (deferred-until reveals).
- R9-9: the "When you do" merge (compiler): the continuation joins the
  INSIDE of the prior cost-paying OptionalEffect (C24 — a sibling
  append would fabricate an independent optional); any other prior falls
  back to the default continuation merge (C13 discipline). Continuation
  rebuilds of ActivatedAbility preserve ``timing``.

Guards:
- every pre-round-9 pinned fingerprint (the r6 + r7 + r8 + r9 pin sets)
  stays byte-identical — all 9-A items are additive;
- the bare ActivatedAbility serializes WITHOUT the "timing" (and
  "condition") keys — pinned against explicit key-absence (dual-
  registration PITFALLS 2026-09-28: missing _OMIT_IF_EMPTY row = golden
  storm);
- DelayedTrigger with condition=None round-trips through the explicit
  null key (no omit row needed — opt:filter decodes null);
- round-9 constructs round-trip through ``to_dict``/``from_dict`` with
  pinned fingerprints; rejections at every new validation point.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest

import MTG_bot.core.ability_tree as at
import MTG_bot.core.test_ability_tree_r6 as R6
import MTG_bot.core.test_ability_tree_r7 as R7
import MTG_bot.core.test_ability_tree_r8 as R8
import MTG_bot.core.test_ability_tree_r9 as R9
from MTG_bot.core.compiler.compiler import (
    _CONTINUATION_PREFIXES,
    _append_optional_to_seq,
    _contains_pay_atom,
    _is_continuation,
    _merge_do_continuation,
    compile_card,
)
from MTG_bot.core.compiler.ingest import RawCard
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    Template,
    TemplateRegistry,
)
from MTG_bot.core.identity import CardIdentity

# ---- shared atoms / selectors ------------------------------------------------

_UNIVERSAL = at.FAnd(())
_BF_YOU = at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU)
_ANY_ZONE = at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY)
_LIB_ANY = at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.ANY)
_CREATURE = at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature")
_PERMANENT = at.FAtom(at.FAtomPred.IS_PERMANENT)
_TEFERI = at.FAtom(at.FAtomPred.NAME_CONTAINS, string_value="Teferi")


def _draw_atom(amount: int = 1) -> at.Atom:
    return at.Atom(
        at.Verb.DRAW,
        at.AtomArgs(
            pairs=(("controller", at.ControllerRef.YOU), ("amount", at.QConst(amount)))
        ),
    )


def _tap_target() -> at.Atom:
    return at.Atom(
        at.Verb.TAP,
        at.AtomArgs(
            pairs=(
                (
                    "target",
                    at.Selector(
                        at.QConst(1), at.SelectorMode.TARGET, _CREATURE, zones=(_BF_YOU,)
                    ),
                ),
            )
        ),
    )


def _pay_atom() -> at.Atom:
    """The R9-9 antecedent: "you may pay {1}" — the PAY verb the
    "When you do" search keys on."""
    return at.Atom(
        at.Verb.PAY,
        at.AtomArgs(
            pairs=(("cost", at.Cost(parts=(at.CostManaGeneric(at.QConst(1)),))),)
        ),
    )


# ---- builders for the round-9 constructs ------------------------------------


def _steward_activated() -> at.ActivatedAbility:
    """R9-1/C20: a Steward-class activation pinned to the sorcery window."""
    return at.ActivatedAbility(
        cost=at.Cost(parts=(at.CostManaGeneric(at.QConst(2)),)),
        effect=_draw_atom(1),
        timing=at.ActivationWindow.SORCERY,
    )


def _life_lead() -> at.FAtom:
    """R9-2: "you've gained 7 life more than you started with" style gate."""
    return at.FAtom(at.FAtomPred.LIFE_LEAD_OVER_START_GE, count=at.QConst(7))


def _vodalian_policy() -> at.Atom:
    """R9-3/C21: scope=THIS_MANA — the restriction anchors to THIS mana."""
    return at.Atom(
        at.Verb.MANA_POLICY,
        at.AtomArgs(pairs=(("scope", "THIS_MANA"),)),
    )


def _orrery_policy() -> at.Atom:
    """R9-3/C21: scope=ALL_YOURS with a filter over the spell shape —
    "you may spend mana as though it were mana of any color …"."""
    return at.Atom(
        at.Verb.MANA_POLICY,
        at.AtomArgs(pairs=(("scope", "ALL_YOURS"), ("filter", _UNIVERSAL))),
    )


def _frost_breath() -> at.Atom:
    """R9-4: PREVENT_EFFECT of the untap (TapStateEvent tapped=False)
    during Step.UNTAP under DurationUntilNextStep — the doc /10 pair."""
    return at.Atom(
        at.Verb.PREVENT_EFFECT,
        at.AtomArgs(
            pairs=(
                ("condition", _CREATURE),
                ("event", at.TapStateEvent(tapped=False, filter=_CREATURE)),
                ("step", at.Step.UNTAP),
                (
                    "duration",
                    at.DurationUntilNextStep(step=at.Step.UNTAP, owner_scoped=True),
                ),
            )
        ),
    )


def _dur_next_untap() -> at.DurationUntilNextStep:
    """R9-4: the bare duration node — owner-relative next untap step."""
    return at.DurationUntilNextStep(step=at.Step.UNTAP)


def _subira_delay() -> at.DelayedTrigger:
    """R9-5/C22: Subira's "When a creature you control enters this turn"
    — an ETB trigger created inside an effect, live for the turn."""
    return at.DelayedTrigger(
        duration=at.DurationEot(),
        event=at.ZoneChangeEvent(
            from_zone=_ANY_ZONE, to_zone=_BF_YOU, subject=_CREATURE
        ),
        condition=None,
        effect=_draw_atom(1),
    )


def _orrery_draw() -> at.Atom:
    """R9-6: Orrery's "Draw a card for each color among permanents you
    control" — DRAW counts through QDistinctColorCount."""
    return at.Atom(
        at.Verb.DRAW,
        at.AtomArgs(
            pairs=(
                ("controller", at.ControllerRef.YOU),
                (
                    "amount",
                    at.QDistinctColorCount(
                        at.Selector(
                            at.QUnbounded(), at.SelectorMode.ALL, _PERMANENT, zones=(_BF_YOU,)
                        )
                    ),
                ),
            )
        ),
    )


def _teferi_grant() -> at.Atom:
    """R9-7: "an additional loyalty ability of a Teferi planeswalker you
    control" — NAME_CONTAINS gate + the sorcery window joined."""
    return at.Atom(
        at.Verb.GRANT_ACTIVATION,
        at.AtomArgs(
            pairs=(("filter", _TEFERI), ("window", at.ActivationWindow.SORCERY))
        ),
    )


def _snoop_reveal() -> at.Atom:
    """R9-8: REVEAL under a duration — the card stays revealed until the
    anchoring object leaves (DurationUntilLeaves default "source")."""
    return at.Atom(
        at.Verb.REVEAL,
        at.AtomArgs(
            pairs=(
                ("controller", at.ControllerRef.YOU),
                ("count", at.QConst(1)),
                ("duration", at.DurationUntilLeaves()),
            )
        ),
    )


# ---- pinned fingerprints (captured after the round-9 edits) -----------------

_NEW_PINS: list[tuple[str, Callable[[], object], str]] = [
    (
        "steward_activated",
        _steward_activated,
        "e3e6878eab31979eb3a4b6f8f95df475772a6f573f548320ccaffc187e1d13a8",
    ),
    (
        "life_lead",
        _life_lead,
        "6aac79f21924e679f3744d5f5cb1e114b50967b37238a37c432d7eff07ecf1de",
    ),
    (
        "vodalian_policy",
        _vodalian_policy,
        "21de6876963f4b69b872921ff4a083fed7ae4e7ed3b6706b76dad7238ba9badb",
    ),
    (
        "orrery_policy",
        _orrery_policy,
        "b1c6969f6aa48a2ec66fe9302a68b192442618e8eefb290d75d2f53b40816205",
    ),
    (
        "frost_breath",
        _frost_breath,
        "75b2a5d13a0e60ce81c5f75debbe3cbe2b24f187090412deaa8e857f8cdac918",
    ),
    (
        "dur_next_untap",
        _dur_next_untap,
        "546f433020d4018c3a7bacb618c4a3aa15a646c5ed5d0a6491c7e8549ba601f6",
    ),
    (
        "subira_delay",
        _subira_delay,
        "9fe91755889a8816bb4d2573cf44aaaaec7914dad1262935611c738b50fc6605",
    ),
    (
        "orrery_draw",
        _orrery_draw,
        "e0a155e3be6966390d01c8ee6bcb8e19e26e1b232170dfbba196cdf8a0c38cca",
    ),
    (
        "teferi_grant",
        _teferi_grant,
        "7857e3264f086ad58f635cb15768cfc26bd9ff81269a1b6ff8c574cd97672f23",
    ),
    (
        "snoop_reveal",
        _snoop_reveal,
        "2beea645d8c8deb3e7d686f61acf598473591ece245e95c862d113d59f18002e",
    ),
    (
        "pay_atom",
        _pay_atom,
        "09c3fde9c2b10603f174c5e9965f90f50159b15f9084bc5f399a0f45ef949c4a",
    ),
]

_REJECTIONS: list[tuple[str, Callable[[], object]]] = [
    # R9-1: timing must be an ActivationWindow member, never a bare str.
    (
        "timing_str",
        lambda: at.ActivatedAbility(
            cost=at.Cost(parts=(at.CostManaGeneric(at.QConst(1)),)),
            effect=_draw_atom(1),
            timing="SORCERY",  # type: ignore[arg-type]
        ),
    ),
    (
        "timing_bool",
        lambda: at.ActivatedAbility(
            cost=at.Cost(parts=(at.CostManaGeneric(at.QConst(1)),)),
            effect=_draw_atom(1),
            timing=True,  # type: ignore[arg-type]
        ),
    ),
    # R9-2: the count-only rule rejects any other slot.
    (
        "life_lead_extra_slot",
        lambda: at.FAtom(at.FAtomPred.LIFE_LEAD_OVER_START_GE, string_value="seven"),
    ),
    # R9-3/C21: the scope vocabulary stays closed.
    (
        "mana_policy_bad_scope",
        lambda: at.Atom(
            at.Verb.MANA_POLICY,
            at.AtomArgs(pairs=(("scope", "BOGUS"),)),
        ),
    ),
    (
        "mana_policy_missing_scope",
        lambda: at.Atom(at.Verb.MANA_POLICY, at.AtomArgs(pairs=())),
    ),
    # R9-4: step must be a Step; owner_scoped must be a bool.
    (
        "dur_next_step_str",
        lambda: at.DurationUntilNextStep(step="UNTAP"),  # type: ignore[arg-type]
    ),
    (
        "dur_next_owner_scoped_int",
        lambda: at.DurationUntilNextStep(
            step=at.Step.UNTAP,
            owner_scoped=1,  # type: ignore[arg-type]
        ),
    ),
    (
        "prevent_step_str",
        lambda: at.Atom(
            at.Verb.PREVENT_EFFECT,
            at.AtomArgs(
                pairs=(
                    ("condition", _CREATURE),
                    ("event", at.TapStateEvent(tapped=False, filter=_CREATURE)),
                    ("step", "UNTAP"),  # type: ignore[arg-type]
                )
            ),
        ),
    ),
    # R9-5/C22: every DelayedTrigger slot is type-checked (None only for
    # condition).
    (
        "delay_bad_duration",
        lambda: at.DelayedTrigger(
            duration=at.QConst(1),  # type: ignore[arg-type]
            event=at.CardDrawnEvent(
                actor=at.FAtom(
                    pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU
                )
            ),
            condition=None,
            effect=_draw_atom(1),
        ),
    ),
    (
        "delay_bad_event",
        lambda: at.DelayedTrigger(
            duration=at.DurationEot(),
            event=_CREATURE,  # type: ignore[arg-type]
            condition=None,
            effect=_draw_atom(1),
        ),
    ),
    (
        "delay_bad_condition",
        lambda: at.DelayedTrigger(
            duration=at.DurationEot(),
            event=at.CardDrawnEvent(
                actor=at.FAtom(
                    pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU
                )
            ),
            condition="nope",  # type: ignore[arg-type]
            effect=_draw_atom(1),
        ),
    ),
    (
        "delay_bad_effect",
        lambda: at.DelayedTrigger(
            duration=at.DurationEot(),
            event=at.CardDrawnEvent(
                actor=at.FAtom(
                    pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU
                )
            ),
            condition=None,
            effect=_CREATURE,  # type: ignore[arg-type]
        ),
    ),
    # R9-6: the counted population must be a Selector.
    (
        "distinct_cc_not_selector",
        lambda: at.QDistinctColorCount(_CREATURE),  # type: ignore[arg-type]
    ),
    # R9-7: filter REQUIRED on GRANT_ACTIVATION; window must be an
    # ActivationWindow.
    (
        "grant_missing_filter",
        lambda: at.Atom(at.Verb.GRANT_ACTIVATION, at.AtomArgs(pairs=())),
    ),
    (
        "grant_window_str",
        lambda: at.Atom(
            at.Verb.GRANT_ACTIVATION,
            at.AtomArgs(pairs=(("filter", _TEFERI), ("window", "SORCERY"))),  # type: ignore[arg-type]
        ),
    ),
    (
        "grant_window_wrong_enum",
        lambda: at.Atom(
            at.Verb.GRANT_ACTIVATION,
            at.AtomArgs(pairs=(("filter", _TEFERI), ("window", at.Step.UNTAP))),  # type: ignore[arg-type]
        ),
    ),
    # R9-8: duration must be a Duration; unknown roles stay rejected.
    (
        "reveal_duration_bad_type",
        lambda: at.Atom(
            at.Verb.REVEAL,
            at.AtomArgs(
                pairs=(
                    ("controller", at.ControllerRef.YOU),
                    ("count", at.QConst(1)),
                    ("duration", at.QConst(2)),  # type: ignore[arg-type]
                )
            ),
        ),
    ),
    (
        "reveal_bogus_role",
        lambda: at.Atom(
            at.Verb.REVEAL,
            at.AtomArgs(
                pairs=(
                    ("controller", at.ControllerRef.YOU),
                    ("count", at.QConst(1)),
                    ("bogus_role", at.QConst(1)),
                )
            ),
        ),
    ),
]

# ---- re-pin: every pre-round-9 tree stays byte-identical --------------------


@pytest.mark.parametrize(
    "name,build,fp",
    R6._NEW_PINS + R7._NEW_PINS + R8._NEW_PINS + R9._NEW_PINS,
    ids=[n for n, _, _ in R6._NEW_PINS + R7._NEW_PINS + R8._NEW_PINS + R9._NEW_PINS],
)
def test_pinned_pre_r10_fingerprint(
    name: str, build: Callable[[], object], fp: str
) -> None:
    """Byte stability: every pre-round-9 pinned tree (the r6 + r7 + r8 +
    r9 pin sets) serializes identically — all 9-A items are additive, no
    template opts in yet."""
    node = build()
    assert at.fingerprint(node) == fp
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d


@pytest.mark.parametrize("name,build,fp", _NEW_PINS, ids=[n for n, _, _ in _NEW_PINS])
def test_r10_roundtrip(name: str, build: Callable[[], object], fp: str) -> None:
    node = build()
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d
    back = at.from_dict(d["tag"], d)
    assert back == node, f"{name}: from_dict(to_dict(x)) != x"
    assert at.canonical_json(back) == at.canonical_json(node)
    assert at.fingerprint(back) == at.fingerprint(node) == fp


@pytest.mark.parametrize("name,fn", _REJECTIONS, ids=[n for n, _ in _REJECTIONS])
def test_r10_rejections(name: str, fn: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        fn()


# ---- R9-1: ActivationWindow + the omit-when-None golden-storm guard ---------


def test_bare_activated_ability_omits_timing_and_condition() -> None:
    """The dual-registration guard (PITFALLS 2026-09-28): a pre-round-9
    activation (no timing, no condition) must serialize with NEITHER
    key — a missing _OMIT_IF_EMPTY row would golden-storm all 305."""
    bare = at.ActivatedAbility(
        cost=at.Cost(parts=(at.CostManaGeneric(at.QConst(1)),)), effect=_draw_atom(1)
    )
    d = at.to_dict(bare)
    assert isinstance(d, dict)
    assert "timing" not in d, f"bare activation gained a timing key: {d}"
    assert "condition" not in d, f"bare activation gained a condition key: {d}"


def test_timing_key_shape_and_roundtrip() -> None:
    d = at.to_dict(_steward_activated())
    # enums serialize as tagged dicts (ControllerRef precedent)
    assert isinstance(d, dict) and d.get("timing") == {
        "tag": "ActivationWindow",
        "name": "SORCERY",
    }
    back = at.from_dict(d["tag"], d)
    assert back == _steward_activated()
    assert at.fingerprint(back) == at.fingerprint(_steward_activated())


# ---- R9-2: the count-only life-lead rule (count enforcement OFF house rule) --


def test_life_lead_bare_count_builds_and_roundtrips() -> None:
    """House convention (ZONE_COUNT_GE precedent): FAtom required-slot
    enforcement excludes "count" — the bare predicate builds; the
    pinned count round-trips."""
    bare = at.FAtom(at.FAtomPred.LIFE_LEAD_OVER_START_GE)
    d = at.to_dict(bare)
    assert isinstance(d, dict) and d.get("pred") == {
        "tag": "FAtomPred",
        "name": "LIFE_LEAD_OVER_START_GE",
    }
    assert at.from_dict(d["tag"], d) == bare
    full = at.to_dict(_life_lead())
    assert isinstance(full, dict)
    assert at.from_dict(full["tag"], full) == _life_lead()


# ---- R9-5: DelayedTrigger's explicit-null condition --------------------------


def test_delayed_trigger_null_condition_roundtrip() -> None:
    """No _OMIT_IF_EMPTY row for the new class: condition=None serializes
    the explicit null key and opt:filter decodes it back."""
    dt = _subira_delay()
    d = at.to_dict(dt)
    assert isinstance(d, dict)
    assert "condition" in d and d["condition"] is None
    assert at.from_dict(d["tag"], d) == dt


def test_delayed_trigger_conditioned_roundtrip() -> None:
    dt = at.DelayedTrigger(
        duration=at.DurationEot(),
        event=at.CardDrawnEvent(
            actor=at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU)
        ),
        condition=_CREATURE,
        effect=_tap_target(),
    )
    d = at.to_dict(dt)
    assert isinstance(d, dict) and d.get("condition") is not None
    assert at.from_dict(d["tag"], d) == dt
    # DelayedTrigger is an Effect-union member: it nests anywhere an
    # effect goes and the parent still round-trips.
    seq = at.Seq(steps=(_draw_atom(1), dt))
    sd = at.to_dict(seq)
    assert isinstance(sd, dict)
    assert at.from_dict(sd["tag"], sd) == seq


# ---- R9-3/C21: the closed scope vocabulary -----------------------------------


def test_mana_policy_scope_vocab() -> None:
    assert at._MANA_POLICY_SCOPES == ("THIS_MANA", "ALL_YOURS")
    _vodalian_policy()
    _orrery_policy()
    assert at._ROLE_TYPES["scope"] == (str,)
    assert at.Verb.MANA_POLICY in at._VERB_ROLES
    assert at.Verb.GRANT_ACTIVATION in at._VERB_ROLES


# ---- registration-table membership -------------------------------------------


def test_r10_table_members() -> None:
    assert "ActivationWindow" in at._ENUMS
    assert at.QDistinctColorCount in at._DATACLASSES
    assert at.DurationUntilNextStep in at._DATACLASSES
    assert at.DelayedTrigger in at._DATACLASSES
    assert "QDistinctColorCount" in at._QUANTITY_TAGS
    assert "DurationUntilNextStep" in at._DURATION_TAGS
    assert "DelayedTrigger" in at._EFFECT_TAGS
    # the union tag literals that make embedded enum pairs decode
    assert "Step" in at._ATOM_VALUE_TAGS and "ActivationWindow" in at._ATOM_VALUE_TAGS
    # R9-2 rule row: count-only, both sides
    req, opt = at._FATOM_RULES[at.FAtomPred.LIFE_LEAD_OVER_START_GE]
    assert req == frozenset({"count"}) and opt == frozenset({"count"})
    # new role types
    assert at._ROLE_TYPES["filter"] == at._F_CLASSES
    assert at._ROLE_TYPES["step"] == (at.Step,)
    assert at._ROLE_TYPES["window"] == (at.ActivationWindow,)
    # the role deltas on the pre-existing verbs
    assert at._VERB_ROLES[at.Verb.PREVENT_EFFECT]["step"] is False
    assert at._VERB_ROLES[at.Verb.REVEAL]["duration"] is False
    assert at._VERB_ROLES[at.Verb.GRANT_ACTIVATION] == {
        "filter": True,
        "window": False,
    }
    assert at._VERB_ROLES[at.Verb.MANA_POLICY] == {"scope": True, "filter": False}
    # the dual-registration row (without it: golden storm)
    assert at._OMIT_IF_EMPTY["ActivatedAbility"] == frozenset({"condition", "timing"})
    assert at.Step.UNTAP in tuple(at.Step)
    assert at.ActivationWindow.SORCERY in tuple(at.ActivationWindow)
    # verb-count stays inside the global pin's range (test_ability_tree.py)
    assert 30 <= len(at.Verb) <= 50


# ---- R9-9 unit level: the Do-merge + the PAY search --------------------------


def test_do_prefix_registered() -> None:
    assert "When you do" in _CONTINUATION_PREFIXES
    assert _is_continuation("When you do, you may tap target creature.")


def test_merge_do_continuation_injects_inside_pay_optional() -> None:
    """C24: Tolarian Kraken — the continuation joins the INSIDE of the
    prior cost-paying optional, never a sibling step."""
    prior = at.OptionalEffect(inner=_pay_atom())
    cont = at.OptionalEffect(inner=_tap_target())
    merged = _merge_do_continuation(prior, cont)
    assert merged == at.OptionalEffect(
        inner=at.Seq(steps=(_pay_atom(), at.OptionalEffect(inner=_tap_target())))
    )


def test_merge_do_continuation_seq_inner_append() -> None:
    """PAY already inside an inner Seq: the continuation appends to THAT
    Seq, preserving the earlier steps."""
    inner = at.Seq(steps=(_pay_atom(), _draw_atom(1)))
    prior = at.OptionalEffect(inner=inner)
    cont = at.OptionalEffect(inner=_tap_target())
    merged = _merge_do_continuation(prior, cont)
    assert merged == at.OptionalEffect(
        inner=at.Seq(steps=(_pay_atom(), _draw_atom(1), cont))
    )


def test_merge_do_continuation_c13_fallbacks() -> None:
    """C13: no cost-paying optional prior (bare draw / un-optional PAY)
    falls back to the DEFAULT continuation merge — never a failure.
    (The default merge wraps the continuation in its own optional layer —
    existing house behaviour, r8 fallback pin.)"""
    cont = at.OptionalEffect(inner=_tap_target())
    fallback = _merge_do_continuation(_draw_atom(1), cont)
    assert fallback == _append_optional_to_seq(_draw_atom(1), cont)
    assert fallback == at.Seq(steps=(_draw_atom(1), at.OptionalEffect(inner=cont)))
    raw_pay = _merge_do_continuation(_pay_atom(), cont)
    assert raw_pay == at.Seq(steps=(_pay_atom(), at.OptionalEffect(inner=cont)))


def test_contains_pay_atom_nested_traversal() -> None:
    """The antecedent test walks the whole Effect union (the
    _fold_meta_filter traversal shape)."""
    pay_opt = at.OptionalEffect(inner=_pay_atom())
    assert _contains_pay_atom(pay_opt)
    assert _contains_pay_atom(at.Seq(steps=(_draw_atom(1), pay_opt)))
    assert _contains_pay_atom(
        at.Choose(count=at.QConst(1), options=(_draw_atom(1), pay_opt))
    )
    assert _contains_pay_atom(
        at.Conditional(pred=_CREATURE, then_effect=_draw_atom(1), else_effect=pay_opt)
    )
    assert _contains_pay_atom(at.Repeat(count=at.QConst(1), inner=pay_opt))
    assert _contains_pay_atom(at.EachPlayer(ref=at.ControllerRef.YOU, effect=pay_opt))
    assert _contains_pay_atom(
        at.DelayedTrigger(
            duration=at.DurationEot(),
            event=at.CardDrawnEvent(
                actor=at.FAtom(
                    pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU
                )
            ),
            condition=None,
            effect=pay_opt,
        )
    )
    assert not _contains_pay_atom(_draw_atom(1))
    assert not _contains_pay_atom(at.Seq(steps=(_draw_atom(1), _tap_target())))


# ---- E2E fixtures (r8 house style) -------------------------------------------


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


_PAY_SENT = "You may pay {1}."
_DO_TAP_SENT = "When you do, you may tap target creature."


def test_compile_do_continuation_end_to_end() -> None:
    """The Tolarian Kraken shape: the Do-continuation lands INSIDE the
    payment optional in the assembled SpellAbility."""
    raw = _raw_card("Do Merge Testcard", 1, sentences=(_PAY_SENT, _DO_TAP_SENT))
    reg = TemplateRegistry()
    reg.register(
        _template(
            "r10-may-pay",
            r"^You may pay \{1\}\.$",
            lambda m: EffectOutcome(effect=at.OptionalEffect(inner=_pay_atom())),
        )
    )
    reg.register(
        _template(
            "r10-do-tap",
            r"^When you do, you may tap target creature\.$",
            lambda m: EffectOutcome(effect=at.OptionalEffect(inner=_tap_target())),
        )
    )
    res = compile_card(raw, reg)
    assert res.unparsed == ()
    spell = res.card.abilities[0]
    assert isinstance(spell, at.SpellAbility)
    assert spell.effect == at.OptionalEffect(
        inner=at.Seq(steps=(_pay_atom(), at.OptionalEffect(inner=_tap_target())))
    )


def test_compile_do_continuation_without_pay_c13() -> None:
    """C13 end-to-end: a Do-continuation with no payment antecedent
    still compiles via the legacy optional-step merge."""
    raw = _raw_card("Orphan Do", 2, sentences=("Draw a card.", _DO_TAP_SENT))
    reg = TemplateRegistry()
    reg.register(
        _template(
            "r10-draw",
            r"^Draw a card\.$",
            lambda m: EffectOutcome(effect=_draw_atom(1)),
        )
    )
    reg.register(
        _template(
            "r10-do-tap",
            r"^When you do, you may tap target creature\.$",
            lambda m: EffectOutcome(effect=at.OptionalEffect(inner=_tap_target())),
        )
    )
    res = compile_card(raw, reg)
    assert res.unparsed == ()
    spell = res.card.abilities[0]
    assert isinstance(spell, at.SpellAbility)
    assert spell.effect == at.Seq(
        steps=(
            _draw_atom(1),
            at.OptionalEffect(inner=at.OptionalEffect(inner=_tap_target())),
        )
    )


def test_compile_do_continuation_preserves_timing() -> None:
    """R9-1 x R9-9: a Do-continuation merged into an ActivatedAbility
    must NOT drop the timing window (the rebuild passes timing=ab.timing
    — the whole point of the round-9 rebuild fix)."""
    raw = _raw_card("Steward Do", 3, sentences=("{2}: You may pay {1}.", _DO_TAP_SENT))
    reg = TemplateRegistry()
    reg.register(
        _template(
            "r10-steward",
            r"^\{2\}: You may pay \{1\}\.$",
            lambda m: AbilityOutcome(
                ability=at.ActivatedAbility(
                    cost=at.Cost(parts=(at.CostManaGeneric(at.QConst(2)),)),
                    effect=at.OptionalEffect(inner=_pay_atom()),
                    timing=at.ActivationWindow.SORCERY,
                )
            ),
        )
    )
    reg.register(
        _template(
            "r10-do-tap",
            r"^When you do, you may tap target creature\.$",
            lambda m: EffectOutcome(effect=at.OptionalEffect(inner=_tap_target())),
        )
    )
    res = compile_card(raw, reg)
    assert res.unparsed == ()
    assert len(res.card.abilities) == 1, "no SpellAbility: the only effect was consumed"
    ab = res.card.abilities[0]
    assert isinstance(ab, at.ActivatedAbility)
    assert ab.timing is at.ActivationWindow.SORCERY
    assert ab.effect == at.OptionalEffect(
        inner=at.Seq(steps=(_pay_atom(), at.OptionalEffect(inner=_tap_target())))
    )


def test_compile_do_continuation_into_triggered() -> None:
    """The Kraken's real carrier shape: the cost-paying optional lives in
    a TriggeredAbility and the Do-continuation joins its inside."""
    raw = _raw_card(
        "Kraken Do",
        4,
        sentences=(
            "When you draw a card, you may pay {1}.",
            _DO_TAP_SENT,
        ),
    )
    reg = TemplateRegistry()
    reg.register(
        _template(
            "r10-kraken",
            r"^When you draw a card, you may pay \{1\}\.$",
            lambda m: AbilityOutcome(
                ability=at.TriggeredAbility(
                    event=at.CardDrawnEvent(
                        actor=at.FAtom(
                            pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU
                        )
                    ),
                    condition=None,
                    effect=at.OptionalEffect(inner=_pay_atom()),
                )
            ),
        )
    )
    reg.register(
        _template(
            "r10-do-tap",
            r"^When you do, you may tap target creature\.$",
            lambda m: EffectOutcome(effect=at.OptionalEffect(inner=_tap_target())),
        )
    )
    res = compile_card(raw, reg)
    assert res.unparsed == ()
    trig = res.card.abilities[0]
    assert isinstance(trig, at.TriggeredAbility)
    assert trig.effect == at.OptionalEffect(
        inner=at.Seq(steps=(_pay_atom(), at.OptionalEffect(inner=_tap_target())))
    )
