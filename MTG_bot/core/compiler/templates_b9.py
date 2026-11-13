"""B9 bucket: single ZNR rows that no earlier template claims.

Each build reuses an encoding an earlier template already executes, from the shared b6 anchors;
none of these effects is a ``templates_b6._TAIL_BUILDERS`` key. A nearby earlier template is not
widened instead when the widening would compile a different ability (see
``_build_cant_be_blocked_self_ok``).

These rows match no template (test_templates_b9 pins them): keyword lists such as "Flying,
vigilance." (a ``KeywordOutcome`` carries one keyword), Taunting Arbormage's kicked "all
creatures able to block target creature this turn do so", and "Destroy all nonland permanents."
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
    LifeLostEvent,
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
from MTG_bot.core.compiler.templates_b5a import target_spell
from MTG_bot.core.compiler.templates_b6 import (
    _draw_a_card,
    _etb_event,
    _scry,
    _self_selector,
)

_BUCKET: Final[str] = "B9"
_PRIORITY: Final[int] = 116  # above B8 (114)

# The keywords the keyword-grant templates accept (as templates_b3._KW_MAP); an unmapped word
# never compiles.
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
# Selector helpers
# ---------------------------------------------------------------------------


def _target_creature() -> Selector:
    """``target creature``: any creature. The lone filter is emitted bare, never wrapped in a
    one-child ``FAnd``."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _target_creature_you_control() -> Selector:
    """``target creature you control`` (templates_b5b._build_sacr_grant's selector without
    "another")."""
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
    """``target creature or planeswalker``."""
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
    """``you control (another) <Class>``: CONTROLLER_COUNT_GE 1 over creatures of that class you
    control (as templates_b2a._build_adherent_of_hope). A world count, judged without a subject:
    it walks the battlefield under ctx.controller and judges ``inner_filter`` per candidate with
    ctx.source = the static's source, so ``FNot(IS_SOURCE)`` ("another") excludes the card
    itself."""
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
    """Creatures you control, ALL mode: the population a QCount counts (as
    templates_b2a._shrine_count)."""
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
    """``creatures your opponents control`` (as templates_b4._creatures_opponents_control)."""
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
    """``Equipped creature``: the creature this source is attached to."""
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
    # The tree of B2a-faiths-fetters and B2b-temple-etb-gain-life, whose patterns read only
    # "Aura" and "land".
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
    # The "as long as" gate is the StaticAbility condition, not an atom duration role.
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
    # As _build_pt_while_another_class, with a GRANT_ABILITY payload.
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
    # B5c-cost-sacrifice-destroy's DESTROY selector plus a creature-with-flying branch.
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
    # B5b-sacr-grant's effect under an ETB head instead of the sacrifice cost.
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
    atom = _keyword_atom(
        Verb.GRANT_ABILITY, _KW_MAP[m.group("kw")], _equipped_creature()
    )
    return AbilityOutcome(ability=StaticAbility(atom))


def _build_gain_life_each_opponent_loses(m: re.Match[str]) -> SentenceOutcome:
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


#: "When(ever) you gain|lose life [for the first time each turn | for the first time during each
#: of your turns]": the trigger head :func:`life_event` reads (frames.py's life frame shares it).
LIFE_TRIGGER_RE: Final[str] = (
    r"(?:When|Whenever) you (?P<life>gain|lose) life"
    r"(?: for the first time (?P<first>each turn|during each of your turns))?"
)


def life_event(m: re.Match[str]) -> LifeGainedEvent | LifeLostEvent:
    """The event of a :data:`LIFE_TRIGGER_RE` head. "For the first time each turn" is the
    turn's first such event, ``ordinal=1``, whenever the permanent arrived (Vengeful Warchief's
    ruling); "during each of your turns" adds TURN_OF YOU, a qualifier that reads no subject, in
    the event's one slot for it, ``actor`` (DESIGN_ATOM_ONTOLOGY §11 R6-2)."""
    you = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
    actor = you
    if m.group("first") == "during each of your turns":
        actor = FAnd(children=(you, FAtom(pred=FAtomPred.TURN_OF, who=ControllerRef.YOU)))
    ordinal = 1 if m.group("first") else None
    if m.group("life") == "gain":
        return LifeGainedEvent(actor=actor, ordinal=ordinal)
    return LifeLostEvent(actor=actor, ordinal=ordinal)


def _build_gain_life_counter_self(m: re.Match[str]) -> SentenceOutcome:
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=life_event(m),
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
    return EffectOutcome(effect=Seq(steps=(_scry(int(m.group("n"))), _draw_a_card())))


def _build_opponents_get_pm_eot(m: re.Match[str]) -> SentenceOutcome:
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
    return EffectOutcome(
        effect=Conditional(
            pred=_you_control_a_class("Wizard", exclude_self=False),
            then_effect=_draw_a_card(),
        )
    )


def _build_counter_noncreature(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.COUNTER_SPELL,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    # target_spell ANDs STACK_KIND_EQ SPELL with the negation.
                    target_spell(
                        FNot(inner=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"))
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_cant_be_blocked_self_ok(m: re.Match[str]) -> SentenceOutcome:
    # B3-target-cant-be-blocked's PREVENT of the DeclareBlockers event, which builds in
    # FNot(IS_SOURCE) for "another". This row prints "Target creature…": the source may be
    # its own target, so the blocked side keeps only the printed POWER_LE bound.
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
        "whenever you gain|lose life [for the first time each turn], put a +1/+1 counter on "
        "this creature",
        rf"^{LIFE_TRIGGER_RE}, put a \+1/\+1 counter on this creature\.$",
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
