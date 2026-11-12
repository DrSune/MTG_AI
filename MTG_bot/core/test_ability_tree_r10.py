"""Grammar pins: activation timing windows, the life-lead predicate, mana
policies, the untap-step prevention, delayed triggers, distinct-colour counts,
granted activations, revealed-until durations, and the compiler's "When you
do" merge.

- ``ActivatedAbility.timing`` (``ActivationWindow``, "Activate only as a
  sorcery") is omit-when-None, registered in both _SPECS and _OMIT_IF_EMPTY:
  a bare activation serializes WITHOUT "timing" and "condition";
- ``DelayedTrigger`` is an Effect-union member living INSIDE its creator;
  a delayed one carries its duration and event (a delayed trigger with no
  lifetime is just a TriggeredAbility), and condition=None round-trips as an
  explicit null;
- the "When you do" continuation is a reflexive trigger (CR 603.12): the
  "If you do" gate ``Conditional(MAY_DONE, ...)`` around a DelayedTrigger
  with no duration and no event, after whatever step it follows (its targets
  are its own, chosen after the action); an ActivatedAbility rebuild keeps
  its ``timing``;
- the constructs here round-trip with pinned fingerprints, and every
  validation point rejects bad input.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

import MTG_bot.core.ability_tree as at
from MTG_bot.core.compiler.compiler import (
    _CONTINUATION_PREFIXES,
    _is_continuation,
    _merge_if_do_continuation,
    compile_card,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    TemplateRegistry,
)
from MTG_bot.core.test_ability_tree_r8 import _raw_card, _template

# ---- shared atoms / selectors ------------------------------------------------

_UNIVERSAL = at.FAnd(())
_BF_YOU = at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU)
_ANY_ZONE = at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY)
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
    """The "When you do" antecedent of Tolarian Kraken: "you may pay {1}"."""
    return at.Atom(
        at.Verb.PAY,
        at.AtomArgs(
            pairs=(("cost", at.Cost(parts=(at.CostManaGeneric(at.QConst(1)),))),)
        ),
    )


# ---- builders ----------------------------------------------------------------


def _steward_activated() -> at.ActivatedAbility:
    """A Steward-class activation pinned to the sorcery window."""
    return at.ActivatedAbility(
        cost=at.Cost(parts=(at.CostManaGeneric(at.QConst(2)),)),
        effect=_draw_atom(1),
        timing=at.ActivationWindow.SORCERY,
    )


def _life_lead() -> at.FAtom:
    """A "you've gained 7 life more than you started with" style gate."""
    return at.FAtom(at.FAtomPred.LIFE_LEAD_OVER_START_GE, count=at.QConst(7))


def _vodalian_policy() -> at.Atom:
    """scope=THIS_MANA — the restriction anchors to THIS mana."""
    return at.Atom(
        at.Verb.MANA_POLICY,
        at.AtomArgs(pairs=(("scope", "THIS_MANA"),)),
    )


def _orrery_policy() -> at.Atom:
    """scope=ALL_YOURS with a filter over the spell shape —
    "you may spend mana as though it were mana of any color …"."""
    return at.Atom(
        at.Verb.MANA_POLICY,
        at.AtomArgs(pairs=(("scope", "ALL_YOURS"), ("filter", _UNIVERSAL))),
    )


def _frost_breath() -> at.Atom:
    """Frost Breath: PREVENT_EFFECT of the untap (TapStateEvent
    tapped=False) during Step.UNTAP under DurationUntilNextStep."""
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
    """The bare duration node — owner-relative next untap step."""
    return at.DurationUntilNextStep(step=at.Step.UNTAP)


def _subira_delay() -> at.DelayedTrigger:
    """Subira's "When a creature you control enters this turn"
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
    """Orrery's "Draw a card for each color among permanents you
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
    """Teferi: "an additional loyalty ability of a Teferi planeswalker you
    control" — NAME_CONTAINS gate + the sorcery window joined."""
    return at.Atom(
        at.Verb.GRANT_ACTIVATION,
        at.AtomArgs(
            pairs=(("filter", _TEFERI), ("window", at.ActivationWindow.SORCERY))
        ),
    )


def _snoop_reveal() -> at.Atom:
    """REVEAL under a duration — the card stays revealed until the
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


# ---- pinned fingerprints -----------------------------------------------------

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
    # timing must be an ActivationWindow member, never a bare str.
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
    # The count-only rule rejects any other slot.
    (
        "life_lead_extra_slot",
        lambda: at.FAtom(at.FAtomPred.LIFE_LEAD_OVER_START_GE, string_value="seven"),
    ),
    # The scope vocabulary stays closed.
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
    # step must be a Step; owner_scoped must be a bool.
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
    # Every DelayedTrigger slot is type-checked (None only for condition).
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
    # The counted population must be a Selector.
    (
        "distinct_cc_not_selector",
        lambda: at.QDistinctColorCount(_CREATURE),  # type: ignore[arg-type]
    ),
    # filter REQUIRED on GRANT_ACTIVATION; window must be an
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
    # duration must be a Duration; unknown roles stay rejected.
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


# ---- ActivationWindow + the omit-when-None guard -----------------------------


def test_bare_activated_ability_omits_timing_and_condition() -> None:
    """The dual-registration guard: an activation with no timing and no
    condition serializes with NEITHER key; a missing _OMIT_IF_EMPTY row
    would change the bytes of every golden activated ability."""
    bare = at.ActivatedAbility(
        cost=at.Cost(parts=(at.CostManaGeneric(at.QConst(1)),)), effect=_draw_atom(1)
    )
    d = at.to_dict(bare)
    assert isinstance(d, dict)
    assert "timing" not in d, f"bare activation gained a timing key: {d}"
    assert "condition" not in d, f"bare activation gained a condition key: {d}"


def test_timing_key_shape_and_roundtrip() -> None:
    d = at.to_dict(_steward_activated())
    # enums serialize as tagged dicts
    assert isinstance(d, dict) and d.get("timing") == {
        "tag": "ActivationWindow",
        "name": "SORCERY",
    }
    back = at.from_dict(d["tag"], d)
    assert back == _steward_activated()
    assert at.fingerprint(back) == at.fingerprint(_steward_activated())


# ---- the count-only life-lead rule -------------------------------------------


def test_life_lead_bare_count_builds_and_roundtrips() -> None:
    """FAtom required-slot enforcement excludes "count" (as for
    ZONE_COUNT_GE): the bare predicate builds; the pinned count
    round-trips."""
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


# ---- DelayedTrigger's explicit-null condition --------------------------------


def test_delayed_trigger_null_condition_roundtrip() -> None:
    """DelayedTrigger's condition is not in its _OMIT_IF_EMPTY row:
    condition=None serializes the explicit null key and opt:filter decodes it
    back."""
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


# ---- the closed scope vocabulary ---------------------------------------------


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
    # LIFE_LEAD_OVER_START_GE rule row: count-only, both sides
    req, opt = at._FATOM_RULES[at.FAtomPred.LIFE_LEAD_OVER_START_GE]
    assert req == frozenset({"count"}) and opt == frozenset({"count"})
    # role types
    assert at._ROLE_TYPES["filter"] == at._F_CLASSES
    assert at._ROLE_TYPES["step"] == (at.Step,)
    assert at._ROLE_TYPES["window"] == (at.ActivationWindow,)
    # the roles this file's constructs add to existing verbs
    assert at._VERB_ROLES[at.Verb.PREVENT_EFFECT]["step"] is False
    assert at._VERB_ROLES[at.Verb.REVEAL]["duration"] is False
    assert at._VERB_ROLES[at.Verb.GRANT_ACTIVATION] == {
        "filter": True,
        "window": False,
    }
    assert at._VERB_ROLES[at.Verb.MANA_POLICY] == {"scope": True, "filter": False}
    # the dual-registration row (without it every golden activation gains keys)
    assert at._OMIT_IF_EMPTY["ActivatedAbility"] == frozenset({"condition", "timing"})
    assert at.Step.UNTAP in tuple(at.Step)
    assert at.ActivationWindow.SORCERY in tuple(at.ActivationWindow)


# ---- unit level: the "When you do" merge -------------------------------------

_PAY_SENT = "You may pay {1}."
_DO_TAP_SENT = "When you do, you may tap target creature."


def _when_you_do(effect: at.Effect) -> at.Conditional:
    """CR 603.12: the reflexive trigger, gated on the step before it (MAY_DONE)."""
    return at.Conditional(
        pred=at.FAtom(at.FAtomPred.MAY_DONE),
        then_effect=at.DelayedTrigger(duration=None, event=None, condition=None, effect=effect),
    )


def test_do_prefix_registered() -> None:
    assert "When you do" in _CONTINUATION_PREFIXES
    assert _is_continuation("When you do, you may tap target creature.")


def test_merge_when_you_do_is_the_if_you_do_gate_around_a_reflexive_trigger() -> None:
    """Tolarian Kraken: the continuation follows the payment as a gated reflexive trigger, never
    inside the payment's optional, where its target would be chosen before the payment. "If you
    do" is the same gate with the effect inline."""
    prior = at.OptionalEffect(inner=_pay_atom())
    cont = at.OptionalEffect(inner=_tap_target())
    merged = _merge_if_do_continuation(prior, cont, _DO_TAP_SENT)
    assert merged == at.Seq(steps=(prior, _when_you_do(cont)))
    if_do = _merge_if_do_continuation(prior, cont, "If you do, you may tap target creature.")
    assert if_do == at.Seq(
        steps=(prior, at.Conditional(pred=at.FAtom(at.FAtomPred.MAY_DONE), then_effect=cont))
    )


def test_merge_when_you_do_appends_to_a_sequence_and_follows_a_mandatory_step() -> None:
    """The gate joins a prior Seq as its last step, and a mandatory antecedent ("Create two
    Faeries. When you do, ...", FDN Faebloom Trick) is gated the same way (CR 118.12)."""
    cont = at.OptionalEffect(inner=_tap_target())
    seq = at.Seq(steps=(_draw_atom(1), at.OptionalEffect(inner=_pay_atom())))
    assert _merge_if_do_continuation(seq, cont, _DO_TAP_SENT) == at.Seq(
        steps=(*seq.steps, _when_you_do(cont))
    )
    assert _merge_if_do_continuation(_draw_atom(1), cont, _DO_TAP_SENT) == at.Seq(
        steps=(_draw_atom(1), _when_you_do(cont))
    )


# ---- end to end --------------------------------------------------------------


def _do_tap_registry(first: tuple[str, str, Callable[[object], object]]) -> TemplateRegistry:
    reg = TemplateRegistry()
    reg.register(_template(*first))
    reg.register(
        _template(
            "r10-do-tap",
            r"^When you do, you may tap target creature\.$",
            lambda m: EffectOutcome(effect=at.OptionalEffect(inner=_tap_target())),
        )
    )
    return reg


def test_compile_do_continuation_end_to_end() -> None:
    """The spell shape: the reflexive trigger follows the payment optional."""
    raw = _raw_card("Do Merge Testcard", 1, sentences=(_PAY_SENT, _DO_TAP_SENT))
    reg = _do_tap_registry(
        ("r10-may-pay", r"^You may pay \{1\}\.$",
         lambda m: EffectOutcome(effect=at.OptionalEffect(inner=_pay_atom())))
    )
    res = compile_card(raw, reg)
    assert res.unparsed == ()
    spell = res.card.abilities[0]
    assert isinstance(spell, at.SpellAbility)
    assert spell.effect == at.Seq(
        steps=(at.OptionalEffect(inner=_pay_atom()), _when_you_do(at.OptionalEffect(inner=_tap_target())))
    )


def test_compile_do_continuation_after_a_mandatory_step() -> None:
    """A "When you do" after a mandatory step ("Draw a card.") is gated on that step."""
    raw = _raw_card("Orphan Do", 2, sentences=("Draw a card.", _DO_TAP_SENT))
    reg = _do_tap_registry(
        ("r10-draw", r"^Draw a card\.$", lambda m: EffectOutcome(effect=_draw_atom(1)))
    )
    res = compile_card(raw, reg)
    assert res.unparsed == ()
    spell = res.card.abilities[0]
    assert isinstance(spell, at.SpellAbility)
    assert spell.effect == at.Seq(
        steps=(_draw_atom(1), _when_you_do(at.OptionalEffect(inner=_tap_target())))
    )


def test_compile_do_continuation_preserves_timing() -> None:
    """A "When you do" merged into an ActivatedAbility must NOT drop the timing window (the
    rebuild passes timing=ab.timing)."""
    raw = _raw_card("Steward Do", 3, sentences=("{2}: You may pay {1}.", _DO_TAP_SENT))
    reg = _do_tap_registry(
        (
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
    res = compile_card(raw, reg)
    assert res.unparsed == ()
    assert len(res.card.abilities) == 1, "no SpellAbility: the only effect was consumed"
    ab = res.card.abilities[0]
    assert isinstance(ab, at.ActivatedAbility)
    assert ab.timing is at.ActivationWindow.SORCERY
    assert ab.effect == at.Seq(
        steps=(at.OptionalEffect(inner=_pay_atom()), _when_you_do(at.OptionalEffect(inner=_tap_target())))
    )


def test_compile_do_continuation_into_triggered() -> None:
    """The Kraken's carrier shape: the payment optional lives in a TriggeredAbility and the
    reflexive trigger follows it there."""
    raw = _raw_card(
        "Kraken Do", 4, sentences=("When you draw a card, you may pay {1}.", _DO_TAP_SENT)
    )
    reg = _do_tap_registry(
        (
            "r10-kraken",
            r"^When you draw a card, you may pay \{1\}\.$",
            lambda m: AbilityOutcome(
                ability=at.TriggeredAbility(
                    event=at.CardDrawnEvent(
                        actor=at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU)
                    ),
                    condition=None,
                    effect=at.OptionalEffect(inner=_pay_atom()),
                )
            ),
        )
    )
    res = compile_card(raw, reg)
    assert res.unparsed == ()
    trig = res.card.abilities[0]
    assert isinstance(trig, at.TriggeredAbility)
    assert trig.effect == at.Seq(
        steps=(at.OptionalEffect(inner=_pay_atom()), _when_you_do(at.OptionalEffect(inner=_tap_target())))
    )
