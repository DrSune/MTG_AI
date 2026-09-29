"""Grammar round 10 / phase 10-A — four additive items (2026-09-29).

Round-10 scope (spec: KNOWLEDGE 2026-09-29/02; file-name offset is
intentional — round-10 grammar ships in the r11 file, following the
r6-in-r7 / r7-in-r8 / r8-in-r9 / r9-in-r10 precedent):

- R10-1: ``ActivationGateOutcome`` gains a trailing-style ``window``
  slot and ``condition`` becomes optional; ``__post_init__`` rejects a
  both-None gate. The compiler attaches slot-disjointly (convention
  C25): a window candidate requires ``timing is None``, a condition
  candidate requires ``condition is None``, a both-set gate requires
  both free; StateCorruptionError when nothing is attachable.
- R10-2: ``FAtomPred.NAME_PARTITION_COUNT_GE`` {inner_filter, count}
  (C26: largest exact-name group over the controller's inner_filter
  objects >= count — Chrome Anchor's Replicator gate).
- R10-3: ``DeclareAttackersEvent.attacked`` trailing optional (dual-
  registered: _SPECS opt-tag + the NEW _OMIT_IF_EMPTY
  DeclareAttackersEvent row; the bare-event byte pin below is the
  golden-storm guard) + ``FAtomPred.ATTACK_AGAINST_COUNT_GE``
  {count, inner_filter} (Mangara).
- R10-4: ``Verb.DAMAGE_ASSIGN_POLICY`` {scope, filter?} with the closed
  ``_DAMAGE_ASSIGN_SCOPES`` vocabulary (C28: the "You may" vertex lives
  OUTSIDE the atom — the granted StaticAbility holds OptionalEffect);
  AtomArgs validates the scope UNION, the enclosing Atom enforces the
  verb's own vocabulary via ``_SCOPE_VOCAB_BY_VERB``.

Guards:
- every pre-round-10 pinned fingerprint (the r6..r10 pin sets) stays
  byte-identical — all 10-A items are additive;
- the bare DeclareAttackersEvent serializes WITHOUT the "attacked" key
  (pinned against the exact canonical JSON);
- round-10 constructs round-trip through ``to_dict``/``from_dict`` with
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
import MTG_bot.core.test_ability_tree_r10 as R10
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.ingest import RawCard
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    ActivationGateOutcome,
    Template,
    TemplateRegistry,
)
from MTG_bot.core.identity import CardIdentity

# ---- shared atoms / selectors ------------------------------------------------

_UNIVERSAL = at.FAnd(())
_TWO = at.QConst(2)
_GATE_COND = at.FAtom(at.FAtomPred.DIED_THIS_TURN)
_ACT_SENT = "{T}: Draw a card."
_ACT_TIMED_SENT = "{2}, Tap: Draw a card."
_GATE_SORCERY_SENT = "Activate only as a sorcery."


def _draw_atom() -> at.Atom:
    return at.Atom(
        at.Verb.DRAW,
        at.AtomArgs(
            pairs=(("controller", at.ControllerRef.YOU), ("amount", at.QConst(1)))
        ),
    )


def _activated(
    cost: at.Cost, timing: at.ActivationWindow | None = None
) -> at.ActivatedAbility:
    return at.ActivatedAbility(
        cost=cost,
        effect=_draw_atom(),
        timing=timing,
    )


_T_TAP = at.Cost(parts=(at.CostTap(),))
_T_2TAP = at.Cost(parts=(at.CostManaGeneric(at.QConst(2)), at.CostTap()))


# ---- pinned round-10 fingerprints (captured after the round-10 edits) --------

_NEW_PINS: list[tuple[str, Callable[[], object], str]] = [
    (
        "name_partition",
        lambda: at.FAtom(
            at.FAtomPred.NAME_PARTITION_COUNT_GE, count=_TWO, inner_filter=_UNIVERSAL
        ),
        "60de197a7971203ed4ac3b8aea1299a864fac97d88579404442f63cfe88dccc8",
    ),
    (
        "attack_against",
        lambda: at.FAtom(
            at.FAtomPred.ATTACK_AGAINST_COUNT_GE, count=_TWO, inner_filter=_UNIVERSAL
        ),
        "dd56bda68fd925a2f9d5b252b60d5ed4817a8b0d76a27f46568743508af2a6a6",
    ),
    (
        "declare_attackers_bare",
        lambda: at.DeclareAttackersEvent(filter=_UNIVERSAL),
        "3e7adeb5c805ac4ddd80d1bced0d36bc8ebcd8d9c1fa8da8bb2a919465b6ec11",
    ),
    (
        "declare_attackers_attacked",
        lambda: at.DeclareAttackersEvent(filter=_UNIVERSAL, attacked=_UNIVERSAL),
        "1536f37bac888e7dc7d32eca318013d1e59360f12b1621d3dfee172cbb689810",
    ),
    (
        "damage_assign_policy",
        lambda: at.Atom(
            at.Verb.DAMAGE_ASSIGN_POLICY,
            at.AtomArgs(pairs=(("scope", "AS_UNBLOCKED"),)),
        ),
        "566813d7625caefea02af847b7e044dc5c22b9d3f24abde4b9adde1636a51169",
    ),
]

_REJECTIONS: list[tuple[str, Callable[[], object]]] = [
    # R10-1: the both-None gate is a template bug.
    ("gate_both_none", lambda: ActivationGateOutcome()),
    # R10-2: inner_filter required, no other slots (CONTROLLER_COUNT_GE
    # twin — the count requirement is carried by the template, like the
    # pre-existing "count unsetness is not enforced" FAtom convention).
    (
        "name_partition_missing_inner",
        lambda: at.FAtom(at.FAtomPred.NAME_PARTITION_COUNT_GE, count=_TWO),
    ),
    (
        "name_partition_extra_slot",
        lambda: at.FAtom(
            at.FAtomPred.NAME_PARTITION_COUNT_GE,
            count=_TWO,
            inner_filter=_UNIVERSAL,
            string_value="Chrome Anchor",
        ),
    ),
    # R10-3: same rule shape on ATTACK_AGAINST_COUNT_GE; the attacked
    # slot must be a Filter.
    (
        "attacked_not_a_filter",
        lambda: at.DeclareAttackersEvent(
            filter=_UNIVERSAL,
            attacked="you",  # type: ignore[arg-type]
        ),
    ),
    # R10-4/C28: the scope vocabularies stay closed and verb-tight.
    (
        "damage_policy_bogus_scope",
        lambda: at.Atom(
            at.Verb.DAMAGE_ASSIGN_POLICY, at.AtomArgs(pairs=(("scope", "BOGUS"),))
        ),
    ),
    (
        "mana_policy_cross_verb_scope",
        lambda: at.Atom(
            at.Verb.MANA_POLICY, at.AtomArgs(pairs=(("scope", "AS_UNBLOCKED"),))
        ),
    ),
    (
        "damage_policy_missing_scope",
        lambda: at.Atom(at.Verb.DAMAGE_ASSIGN_POLICY, at.AtomArgs()),
    ),
]


# ---- byte stability -----------------------------------------------------------


@pytest.mark.parametrize(
    "name,build,fp",
    R6._NEW_PINS + R7._NEW_PINS + R8._NEW_PINS + R9._NEW_PINS + R10._NEW_PINS,
    ids=[
        n
        for n, _, _ in R6._NEW_PINS
        + R7._NEW_PINS
        + R8._NEW_PINS
        + R9._NEW_PINS
        + R10._NEW_PINS
    ],
)
def test_pinned_pre_r11_fingerprint(
    name: str, build: Callable[[], object], fp: str
) -> None:
    """Byte stability: every pre-round-10 pinned tree stays identical —
    all 10-A items are additive, no template opts in yet."""
    node = build()
    assert at.fingerprint(node) == fp
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d


@pytest.mark.parametrize("name,build,fp", _NEW_PINS, ids=[n for n, _, _ in _NEW_PINS])
def test_r11_roundtrip(name: str, build: Callable[[], object], fp: str) -> None:
    node = build()
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d
    back = at.from_dict(d["tag"], d)
    assert back == node, f"{name}: from_dict(to_dict(x)) != x"
    assert at.canonical_json(back) == at.canonical_json(node)
    assert at.fingerprint(back) == at.fingerprint(node) == fp


@pytest.mark.parametrize("name,fn", _REJECTIONS, ids=[n for n, _ in _REJECTIONS])
def test_r11_rejections(name: str, fn: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        fn()


# ---- R10-1: the gate outcome dataclass (unit — no compiler) -------------------


def test_gate_outcome_window_only() -> None:
    gate = ActivationGateOutcome(window=at.ActivationWindow.SORCERY)
    assert gate.window is at.ActivationWindow.SORCERY
    assert gate.condition is None


def test_gate_outcome_condition_only() -> None:
    gate = ActivationGateOutcome(condition=_GATE_COND)
    assert gate.window is None
    assert gate.condition == _GATE_COND


def test_gate_outcome_both() -> None:
    gate = ActivationGateOutcome(
        window=at.ActivationWindow.SORCERY, condition=_GATE_COND
    )
    assert gate.window is at.ActivationWindow.SORCERY
    assert gate.condition == _GATE_COND


def test_gate_outcome_both_none_raises() -> None:
    with pytest.raises(ValueError, match="at least one"):
        ActivationGateOutcome()


# ---- R10-1: compiler slot-disjoint attach (C25) --------------------------------


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


def _r11_registry() -> TemplateRegistry:
    """Mini-registry: plain + pre-timed activated abilities, plus the
    window-only, condition-only and compound gate sentences."""
    reg = TemplateRegistry()
    reg.register(
        _template(
            "r11-act-tap-draw",
            r"^\{T\}: Draw a card\.$",
            lambda m: AbilityOutcome(ability=_activated(_T_TAP)),
        )
    )
    reg.register(
        _template(
            "r11-act-timed",
            r"^\{2\}, Tap: Draw a card\.$",
            lambda m: AbilityOutcome(
                ability=_activated(_T_2TAP, timing=at.ActivationWindow.SORCERY)
            ),
        )
    )
    reg.register(
        _template(
            "r11-gate-sorcery",
            r"^Activate only as a sorcery\.$",
            lambda m: ActivationGateOutcome(window=at.ActivationWindow.SORCERY),
        )
    )
    reg.register(
        _template(
            "r11-gate-cond",
            r"^Activate only if a creature died this turn\.$",
            lambda m: ActivationGateOutcome(condition=_GATE_COND),
        )
    )
    reg.register(
        _template(
            "r11-gate-both",
            r"^Activate only if a creature died this turn and only as a sorcery\.$",
            lambda m: ActivationGateOutcome(
                window=at.ActivationWindow.SORCERY, condition=_GATE_COND
            ),
        )
    )
    return reg


def test_window_gate_attaches_timing_condition_stays_free() -> None:
    """(a) The Steward shape: a window-only gate fills ``timing`` and
    leaves ``condition`` None."""
    raw = _raw_card("Window Gate", 1, sentences=(_ACT_SENT, _GATE_SORCERY_SENT))
    res = compile_card(raw, _r11_registry())
    assert res.unparsed == ()
    ab = res.card.abilities[0]
    assert isinstance(ab, at.ActivatedAbility)
    assert ab.timing is at.ActivationWindow.SORCERY
    assert ab.condition is None


def test_condition_gate_preserves_existing_printed_timing() -> None:
    """C25 asymmetry: a condition-only gate qualifies for an ability whose
    ``timing`` is already printed (only the condition slot matters)."""
    raw = _raw_card(
        "Cond Gate",
        2,
        sentences=(_ACT_TIMED_SENT, "Activate only if a creature died this turn."),
    )
    res = compile_card(raw, _r11_registry())
    assert res.unparsed == ()
    ab = res.card.abilities[0]
    assert isinstance(ab, at.ActivatedAbility)
    assert ab.timing is at.ActivationWindow.SORCERY
    assert ab.condition == _GATE_COND


def test_compound_gate_attaches_both_slots() -> None:
    """The Speaker's compound gate sets window AND condition in one
    attach."""
    raw = _raw_card(
        "Compound Gate",
        3,
        sentences=(
            _ACT_SENT,
            "Activate only if a creature died this turn and only as a sorcery.",
        ),
    )
    res = compile_card(raw, _r11_registry())
    assert res.unparsed == ()
    ab = res.card.abilities[0]
    assert isinstance(ab, at.ActivatedAbility)
    assert ab.timing is at.ActivationWindow.SORCERY
    assert ab.condition == _GATE_COND


def test_window_gate_falls_through_to_free_candidate() -> None:
    """(c1) The nearest preceding ability has ``timing`` pre-filled, so
    the window gate falls through to the earlier free candidate (C25
    slot-disjoint pairing), NOT onto the timed ability."""
    raw = _raw_card(
        "Fallthrough Gate",
        4,
        sentences=(_ACT_SENT, _ACT_TIMED_SENT, _GATE_SORCERY_SENT),
    )
    res = compile_card(raw, _r11_registry())
    assert res.unparsed == ()
    acts = [a for a in res.card.abilities if isinstance(a, at.ActivatedAbility)]
    assert len(acts) == 2
    plain, timed = acts
    assert plain.timing is at.ActivationWindow.SORCERY  # gate landed here
    assert timed.timing is at.ActivationWindow.SORCERY  # its own printed one
    assert plain.condition is None and timed.condition is None


def test_window_gate_all_slots_busy_raises() -> None:
    """(c2) Every preceding ability's window slot is already filled →
    StateCorruptionError (existing orphan-gate semantics preserved)."""
    from MTG_bot.core.compiler.compiler import StateCorruptionError

    raw = _raw_card(
        "Busy Gate",
        5,
        sentences=(_ACT_TIMED_SENT, _GATE_SORCERY_SENT),
    )
    with pytest.raises(StateCorruptionError):
        compile_card(raw, _r11_registry())


# ---- R10-3: the attacked omit-when-None byte pin (golden-storm guard) ---------


def test_bare_declare_attackers_omits_attacked_byte_pin() -> None:
    """Dual-registration guard (PITFALLS 2026-09-28): a missing
    _OMIT_IF_EMPTY row would add an "attacked": null key to EVERY
    existing attack trigger — the bare event must serialize WITHOUT the
    key."""
    node = at.DeclareAttackersEvent(filter=_UNIVERSAL)
    assert at.canonical_json(node) == (
        '{"filter":{"children":[],"tag":"FAnd"},"tag":"DeclareAttackersEvent"}'
    )
    d = at.to_dict(node)
    assert "attacked" not in d


def test_attacked_full_roundtrip() -> None:
    node = at.DeclareAttackersEvent(
        filter=at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature"),
        attacked=at.FAtom(at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
    )
    d = at.to_dict(node)
    assert d["attacked"]["tag"] == "FAtom"
    assert at.from_dict(d["tag"], d) == node
    assert at.canonical_json(at.from_dict(d["tag"], d)) == at.canonical_json(node)


# ---- R10-2/3/4: table membership pins ------------------------------------------


def test_r11_table_members() -> None:
    assert at._DAMAGE_ASSIGN_SCOPES == ("AS_UNBLOCKED",)
    assert at._ROLE_TYPES["scope"] == (str,)
    assert at.Verb.DAMAGE_ASSIGN_POLICY in at._VERB_ROLES
    assert at._VERB_ROLES[at.Verb.DAMAGE_ASSIGN_POLICY] == {
        "scope": True,
        "filter": False,
    }
    assert at._SCOPE_VOCAB_BY_VERB[at.Verb.MANA_POLICY] is at._MANA_POLICY_SCOPES
    assert (
        at._SCOPE_VOCAB_BY_VERB[at.Verb.DAMAGE_ASSIGN_POLICY]
        is at._DAMAGE_ASSIGN_SCOPES
    )
    assert at._FATOM_RULES[at.FAtomPred.NAME_PARTITION_COUNT_GE] == (
        frozenset({"inner_filter", "count"}),
        frozenset({"inner_filter", "count"}),
    )
    assert at._FATOM_RULES[at.FAtomPred.ATTACK_AGAINST_COUNT_GE] == (
        frozenset({"count", "inner_filter"}),
        frozenset({"count", "inner_filter"}),
    )
    assert at._OMIT_IF_EMPTY["DeclareAttackersEvent"] == frozenset({"attacked"})
    assert ("attacked", "opt:filter") in at._SPECS["DeclareAttackersEvent"]


def test_damage_policy_optional_filter_slot() -> None:
    """filter is OPTIONAL on DAMAGE_ASSIGN_POLICY (roles {scope:True,
    filter:False}) — scope-only atoms build and round-trip."""
    node = at.Atom(
        at.Verb.DAMAGE_ASSIGN_POLICY,
        at.AtomArgs(
            pairs=(
                ("scope", "AS_UNBLOCKED"),
                ("filter", at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature")),
            )
        ),
    )
    d = at.to_dict(node)
    assert at.from_dict(d["tag"], d) == node
