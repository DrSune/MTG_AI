"""Bucket B9 — the ZND-4 flip-sweep (spec KNOWLEDGE/2026-10-19/115).

Fifteen templates clear 17 register rows: the Batch A carriers that could
not be widened in place (the widen would compile a DIFFERENT ability —
G-FM2's Sneaking Guide diagnosis generalized) plus the Batch B named-shape
tail. Every build is locally composed from the shared b6 anchors (FM6
shared-tail law: none of these effects is a ``_TAIL_BUILDERS`` key) and
mirrors a CARRIER THAT IS ALREADY EXECUTED elsewhere — each docstring
names the carrier whose executor falsifier covers the encoding shape
(spec /115 "WORLD-CANONICAL" rule).

Priority is PINNED 116 (G-FM3): the ladder is 100/110/112/114; a tie at
the b1 default would let the tid-asc tiebreak silently starve b9 rows.

Gap ledger (ZND-4 named defers — these rows stay UNPARSED, no silent
partials, no forced lanes):

* **ZND-4a** keyword-list continuations ("Flying, vigilance" / "Defender,
  reach" / "Flying, lifelink") — ``KeywordOutcome`` carries ONE enum and
  the compiler never merges outcomes (G-FM1); multi-keyword is a schema
  MECHANISM decision (Type-1), a named future round.
* **ZND-4b** "When this creature enters, if it was kicked, all creatures
  able to block target creature this turn do so." (Taunting Arbormage) —
  MANDATE_BLOCK is NOT a dispatched ``run_atom`` verb
  (executor/__init__.py:235; the ledger rides layers' static-ability
  records only, layers.py:390–453). A trigger-fired temporary mandate
  needs the engine lane; forcing it would mint a trigger that raises at
  resolve. G-FM4's conditional: the lane does NOT accept the effect —
  honest defer (engine files are OFF-LIMITS this wave).
* **ZND-4c** "Destroy all nonland permanents." (Ondu Inversion) — the
  named carrier b5a:2175 is EQUIPMENT-SCOPED (G-FM5); the all-permanent
  scope is a different selector family with no executed carrier. Pre-
  declared named defer (audit risk-1: do not force).
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    Atom,
    AtomArgs,
    Conditional,
    ControllerRef,
    Cost,
    CostManaGeneric,
    CostTap,
    CounterKind,
    DeclareBlockersEvent,
    DurationEot,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    LifeGainedEvent,
    PtDelta,
    PtDirection,
    QConst,
    QCount,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    SentenceOutcome,
    Template,
)
from MTG_bot.core.compiler.templates_b6 import (
    _draw_a_card,
    _etb_event,
    _scry,
    _self_selector,
)

_BUCKET: Final[str] = "B9"
_PRIORITY: Final[int] = 116  # G-FM3: ladder 100/110/112/114, b9 sits above all

# Keyword words the keyword-grant templates accept — the closed map of the
# b3 precedent (templates_b3._KW_MAP); an unmapped word never compiles.
_KW_MAP: dict[str, Keyword] = {
    "deathtouch": Keyword.DEATHTOUCH,
    "indestructible": Keyword.INDESTRUCTIBLE,
    "flying": Keyword.FLYING,
    "lifelink": Keyword.LIFELINK,
}


def _template(tid: str, name: str, pattern: str, build) -> Template:
    return Template(
        tid=tid,
        name=name,
        bucket=_BUCKET,
        pattern=re.compile(pattern),
        priority=_PRIORITY,
        build=build,
    )


# ---------------------------------------------------------------------------
# Selector helpers (mirror the named carriers' shapes exactly)
# ---------------------------------------------------------------------------


def _target_creature() -> Selector:
    """``target creature`` — the b5b-sacr-grant TARGET shape without the
    controller conjunct (Dauntless Survivor sees EVERY creature).

    R1a (ontology §6 V2′): the lone conjunct is emitted BARE — a one-child
    ``FAnd`` is a phantom wrapper, so the unwrap happens here at the
    emission site, not in the frozen node."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _target_creature_you_control() -> Selector:
    """``target creature you control`` — verbatim the executed
    B5b-sacr-grant selector (carrier: templates_b5b._build_sacr_grant)."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _target_creature_or_planeswalker() -> Selector:
    """``target creature or planeswalker`` — the executed two-branch
    ``_destroy_cw_pw`` target narrowed to the permanent kinds
    (carrier: templates_b6._destroy_cw_pw)."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FOr(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _you_control_a_class(cls: str, *, exclude_self: bool) -> Filter:
    """``you control (another) <Class>`` as a WORLD-COUNT condition —
    the executed Basri ``CONTROLLER_COUNT_GE`` shape (carrier:
    templates_b2a._build_basri_condition, b2a:1688), with the
    ``FNot(IS_SOURCE)`` "another" primitive (templates_b2a:591) inside
    the per-candidate inner filter.

    FINDING (2026-10-19, ZND-4 executor falsifier): the per-card
    conjunct filter (TYPE/SUBTYPE/CONTROLLER_IS/FNot-IS_SOURCE) is NOT
    a valid static gate. The attached-static registration path
    (layers.py ~514) carries ONLY ``StaticAbility.condition`` into the
    LayerRecord and silently drops the atom's ``duration`` role, so a
    DurationWhileCondition placed there leaves the layer EVER-LIVE
    (B4-modify-pt-while-garruk / B4-grant-lifelink-while-counter are
    affected — pre-existing engine gap, executor lane, NOT editable
    here). The condition must be handle-free and world-evaluable:
    CONTROLLER_COUNT_GE counts the battlefield population under
    ctx.controller and evaluates ``inner_filter`` per candidate with
    ctx.source = the layer anchor, so the "another" exclusion is exact
    (G-FM2: the carrier never opens its own gate)."""
    children: list[Filter] = [
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value=cls),
        FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
    ]
    if exclude_self:
        children.append(FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)))
    return FAtom(
        pred=FAtomPred.CONTROLLER_COUNT_GE,
        inner_filter=FAnd(children=tuple(children)),
        count=QConst(1),
    )


def _creatures_you_control_all() -> Selector:
    """POPULATION census axis for QCount — the executed ``_shrine_count``
    idiom (QUnbounded × ALL, carrier: templates_b2a._shrine_count)."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _creatures_opponents_control() -> Selector:
    """``creatures your opponents control`` — verbatim the executed b4
    anthem-scope selector (carrier: templates_b4._creatures_opponents_control)."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _equipped_creature() -> Selector:
    """``Equipped creature`` = the attachment target — the executed
    IS_ATTACHED_TO_SOURCE shape (carrier: templates_b5a._enchanted_creature)."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.IS_ATTACHED_TO_SOURCE),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _keyword_atom(verb: Verb, kw: Keyword, target: Selector, **extra: object) -> Atom:
    pairs = [
        ("target", target),
        ("ability", KeywordAbility(keyword=kw)),
    ]
    pairs.extend(extra.items())
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(pairs)))


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _build_etb_gain_life(m: re.Match[str]) -> SentenceOutcome:
    # CARRIER: B2a-faiths-fetters (executor-executed; templates_b2a:2426)
    # and its land twin B2b-temple-etb-gain-life (templates_b2b:2313).
    # The carrier regex only reads "Aura"/"land"; "creature" is the SAME
    # class-A self anchor (IS_SOURCE) + GAIN_LIFE atom.
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_etb_event(),
            condition=None,
            effect=Atom(
                verb=Verb.GAIN_LIFE,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", QConst(int(m.group("n")))),
                    )
                ),
            ),
        )
    )


def _build_pt_while_another_class(m: re.Match[str]) -> SentenceOutcome:
    # G-FM1 Batch-A T4. Static gate on ``StaticAbility.condition`` — the
    # ONLY filter the attached-static registration path reads (see
    # _you_control_a_class's FINDING: the atom duration-role while is
    # silently dropped by the engine, ever-live).
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _self_selector()),
                ("power", PtDelta(PtDirection.INCREASE, QConst(int(m.group("p"))))),
                ("toughness", PtDelta(PtDirection.INCREASE, QConst(int(m.group("t"))))),
            )
        ),
    )
    return AbilityOutcome(
        ability=StaticAbility(
            atom,
            condition=_you_control_a_class(m.group("cls"), exclude_self=True),
        )
    )


def _build_kw_while_another_class(m: re.Match[str]) -> SentenceOutcome:
    # Same static lane as _build_pt_while_another_class (StaticAbility
    # GRANT payload, condition-gated); the payload verb is GRANT_ABILITY
    # exactly like the executor-executed B4-grant-kw-static-you carrier.
    atom = _keyword_atom(
        Verb.GRANT_ABILITY,
        _KW_MAP[m.group("kw")],
        _self_selector(),
    )
    return AbilityOutcome(
        ability=StaticAbility(
            atom,
            condition=_you_control_a_class(m.group("cls"), exclude_self=True),
        )
    )


def _build_destroy_artifact_enchantment_flying(m: re.Match[str]) -> SentenceOutcome:
    # CARRIER: B5c-cost-sacrifice-destroy's DESTROY selector (executor-
    # executed, templates_b5c:1407) widened with the third FOr branch
    # creature-with-flying (KEYWORD_HAS, executed b2a:1557 conjunct).
    atom = Atom(
        verb=Verb.DESTROY,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FOr(
                            children=(
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Artifact"),
                                FAtom(
                                    pred=FAtomPred.TYPE_EQ,
                                    string_value="Enchantment",
                                ),
                                FAnd(
                                    children=(
                                        FAtom(
                                            pred=FAtomPred.TYPE_EQ,
                                            string_value="Creature",
                                        ),
                                        FAtom(
                                            pred=FAtomPred.KEYWORD_HAS,
                                            keyword=Keyword.FLYING,
                                        ),
                                    )
                                ),
                            )
                        ),
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_etb_put_counter_target(m: re.Match[str]) -> SentenceOutcome:
    # CARRIER: PUT_COUNTER executed on a NON-self selector by
    # B8's _put_two_counters_each_you_control (templates_b6:470) and on a
    # TARGET selector by the executor's Dryad shape (binding.py:750);
    # ETB trigger = the class-A self anchor.
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_etb_event(),
            condition=None,
            effect=Atom(
                verb=Verb.PUT_COUNTER,
                args=AtomArgs(
                    pairs=(
                        ("target", _target_creature()),
                        ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                        ("count", QConst(1)),
                    )
                ),
            ),
        )
    )


def _build_etb_target_gains_indestructible(m: re.Match[str]) -> SentenceOutcome:
    # CARRIER: B5b-sacr-grant (executor-executed TARGET-mode GRANT
    # INDESTRUCTIBLE UET, templates_b5b._build_sacr_grant); only the head
    # differs (sacrifice cost -> this creature's ETB).
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_etb_event(),
            condition=None,
            effect=_keyword_atom(
                Verb.GRANT_ABILITY,
                Keyword.INDESTRUCTIBLE,
                _target_creature_you_control(),
                duration=DurationEot(),
            ),
        )
    )


def _build_equipped_keyword(m: re.Match[str]) -> SentenceOutcome:
    # CARRIER: the static GRANT lane B4-grant-kw-static-you (executor-
    # executed) over the executed B5a-equipped-pt attachment selector
    # (templates_b5a:1299 _equipped_creature).
    atom = _keyword_atom(
        Verb.GRANT_ABILITY, _KW_MAP[m.group("kw")], _equipped_creature()
    )
    return AbilityOutcome(ability=StaticAbility(atom))


def _build_gain_life_each_opponent_loses(m: re.Match[str]) -> SentenceOutcome:
    # CARRIER: B2b-gain-life-target-opponent (executor-executed
    # LifeGainedEvent head, templates_b2b:2624). "each opponent" is the
    # ALL_OPPONENTS life-reference idiom (templates_b2b module law, line 67).
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=LifeGainedEvent(
                actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
            ),
            condition=None,
            effect=Atom(
                verb=Verb.LOSE_LIFE,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.ALL_OPPONENTS),
                        ("amount", QConst(int(m.group("n")))),
                    )
                ),
            ),
        )
    )


def _build_gain_life_counter_self(m: re.Match[str]) -> SentenceOutcome:
    # CARRIER: same LifeGainedEvent head (B2b-gain-life-target-opponent);
    # the self-counter tail is the executed b6 anchor _put_counter_self
    # recomposed here (FM6: not a _TAIL_BUILDERS key).
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=LifeGainedEvent(
                actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
            ),
            condition=None,
            effect=Atom(
                verb=Verb.PUT_COUNTER,
                args=AtomArgs(
                    pairs=(
                        ("target", _self_selector()),
                        ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                        ("count", QConst(1)),
                    )
                ),
            ),
        )
    )


def _build_census_damage(m: re.Match[str]) -> SentenceOutcome:
    # CARRIER: the QCount census is the executed _shrine_count idiom
    # (templates_b2a:199, resolve-pin like b8's X arithmetic); the
    # cw/pw TARGET is the executed _destroy_cw_pw branch pair.
    atom = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _target_creature_or_planeswalker()),
                ("amount", QCount(_creatures_you_control_all())),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_scry_then_draw(m: re.Match[str]) -> SentenceOutcome:
    # CARRIERS: both tails are executed b6 anchors (_scry = the b5b SCR
    # shape, _draw_a_card); Seq sequencing is the executed b5a
    # gnarled-sage cast-effect Seq idiom.
    return EffectOutcome(effect=Seq(steps=(_scry(int(m.group("n"))), _draw_a_card())))


def _build_opponents_get_pm_eot(m: re.Match[str]) -> SentenceOutcome:
    # CARRIERS: the opponents-scope anthem selector
    # (B4-modify-pt-static-opponents, executor-executed layers anthem) +
    # the DurationEot payload shape of B4-modify-pt-eot-you (executor-
    # executed cast anthem). G-FM5: Beyeen Veil rides the REAL anthem
    # lane (the compiled "get ±P/±T UET" tids), not b3:1047.
    p, t = int(m.group("p")), int(m.group("t"))
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _creatures_opponents_control()),
                ("power", PtDelta(PtDirection.DECREASE, QConst(p))),
                ("toughness", PtDelta(PtDirection.DECREASE, QConst(t))),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_if_wizard_draw(m: re.Match[str]) -> SentenceOutcome:
    # CARRIER: the spell-level Conditional is executor-executed (Coveted
    # Prize, templates_b8); the count condition is the executed Basri
    # CONTROLLER_COUNT_GE shape (templates_b2a:1688).
    return EffectOutcome(
        effect=Conditional(
            pred=_you_control_a_class("Wizard", exclude_self=False),
            then_effect=_draw_a_card(),
        )
    )


def _build_counter_noncreature(m: re.Match[str]) -> SentenceOutcome:
    # CARRIER: B5a-counter-spell (executor-executed, templates_b5a:276 —
    # the STACK-zone TARGET selector); "noncreature" adds the executed
    # FNot(TYPE_EQ) negation primitive (FNot class, ability_tree:1302).
    atom = Atom(
        verb=Verb.COUNTER_SPELL,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    # R1a (ontology §6 V2′): lone negation emitted BARE — a
                    # one-child FAnd is a phantom wrapper (unwrap at emission).
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FNot(
                            inner=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
                        ),
                        zones=(Zone(kind=ZoneKind.STACK, controller=ControllerRef.ANY),),
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_cant_be_blocked_self_ok(m: re.Match[str]) -> SentenceOutcome:
    # CARRIER: B3-target-cant-be-blocked (executor-executed PREVENT of the
    # DeclareBlockers event, templates_b3._build_target_cant_be_blocked).
    # G-FM2 (Sneaking Guide): the carrier BAKES FNot(IS_SOURCE) ("another")
    # — a regex-only widen would compile a DIFFERENT ability. This row
    # prints "Target creature…" with no "another": the self may be its own
    # target, so the blocked-side filter drops the IS_SOURCE negation and
    # keeps the printed POWER_LE bound.
    blocked = FAnd(
        children=(
            FAtom(pred=FAtomPred.IS_ANY_TARGET),
            FAtom(pred=FAtomPred.POWER_LE, count=QConst(2)),
        )
    )
    effect = Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(
                ("condition", FAtom(pred=FAtomPred.IS_ANY_TARGET)),
                ("event", DeclareBlockersEvent(FAnd(children=()), blocked=blocked)),
                ("duration", DurationEot()),
            )
        ),
    )
    cost = Cost(
        parts=(CostManaGeneric(QConst(2)), CostTap()),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=effect))


# ---------------------------------------------------------------------------
# The registry tuple
# ---------------------------------------------------------------------------

TEMPLATES: tuple[Template, ...] = (
    _template(
        "B9-etb-gain-life",
        "when this creature enters, you gain N life",
        r"^When this creature enters, you gain (?P<n>\d+) life\.$",
        _build_etb_gain_life,
    ),
    _template(
        "B9-pt-while-another-class",
        "this creature gets +P/+T as long as you control another <class>",
        r"^This creature gets \+(?P<p>\d+)/\+(?P<t>\d+) "
        r"as long as you control another (?P<cls>[A-Z][a-z]+)\.$",
        _build_pt_while_another_class,
    ),
    _template(
        "B9-kw-while-another-class",
        "this creature has <keyword> as long as you control another <class>",
        r"^This creature has (?P<kw>deathtouch|indestructible|flying|lifelink) "
        r"as long as you control another (?P<cls>[A-Z][a-z]+)\.$",
        _build_kw_while_another_class,
    ),
    _template(
        "B9-destroy-artifact-enchantment-flying",
        "destroy target artifact, enchantment, or creature with flying",
        r"^Destroy target artifact, enchantment, or creature with flying\.$",
        _build_destroy_artifact_enchantment_flying,
    ),
    _template(
        "B9-etb-put-counter-target",
        "when this creature enters, put a +1/+1 counter on target creature",
        r"^When this creature enters, put a \+1/\+1 counter on target creature\.$",
        _build_etb_put_counter_target,
    ),
    _template(
        "B9-etb-target-gains-indestructible-eot",
        "when this creature enters, target creature you control gains "
        "indestructible until end of turn",
        r"^When this creature enters, target creature you control gains "
        r"indestructible until end of turn\.$",
        _build_etb_target_gains_indestructible,
    ),
    _template(
        "B9-equipped-keyword",
        "equipped creature has <keyword>",
        r"^Equipped creature has (?P<kw>deathtouch|indestructible|flying|lifelink)\.$",
        _build_equipped_keyword,
    ),
    _template(
        "B9-gain-life-each-opponent-loses",
        "whenever you gain life, each opponent loses N life",
        r"^Whenever you gain life, each opponent loses (?P<n>\d+) life\.$",
        _build_gain_life_each_opponent_loses,
    ),
    _template(
        "B9-gain-life-counter-self",
        "whenever you gain life, put a +1/+1 counter on this creature",
        r"^Whenever you gain life, put a \+1/\+1 counter on this creature\.$",
        _build_gain_life_counter_self,
    ),
    _template(
        "B9-census-damage-kabira",
        "Kabira Takedown deals damage equal to the number of creatures you "
        "control to target creature or planeswalker",
        r"^Kabira Takedown deals damage equal to the number of creatures you "
        r"control to target creature or planeswalker\.$",
        _build_census_damage,
    ),
    _template(
        "B9-scry-then-draw",
        "scry N, then draw a card",
        r"^Scry (?P<n>\d+), then draw a card\.$",
        _build_scry_then_draw,
    ),
    _template(
        "B9-opponents-get-pm-eot",
        "creatures your opponents control get -P/-T until end of turn",
        r"^Creatures your opponents control get -(?P<p>\d+)/-(?P<t>\d+) "
        r"until end of turn\.$",
        _build_opponents_get_pm_eot,
    ),
    _template(
        "B9-if-wizard-draw",
        "if you control a Wizard, draw a card",
        r"^If you control a Wizard, draw a card\.$",
        _build_if_wizard_draw,
    ),
    _template(
        "B9-counter-noncreature-spell",
        "counter target noncreature spell",
        r"^Counter target noncreature spell\.$",
        _build_counter_noncreature,
    ),
    _template(
        "B9-target-cant-be-blocked-self-ok",
        "target creature with power 2 or less can't be blocked this turn "
        "(self as legal target, G-FM2)",
        r"^\{2\}, \{T\}: Target creature with power 2 or less "
        r"can't be blocked this turn\.$",
        _build_cant_be_blocked_self_ok,
    ),
)
