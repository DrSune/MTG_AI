"""B10 bucket: "Whenever you cast an instant, sorcery, or Wizard spell, ..." and a counterspell.

The cast head is ``CastSpellEvent(filter=FOr(TYPE_EQ Instant, TYPE_EQ Sorcery, SUBTYPE_EQ
Wizard), actor=CONTROLLER_IS YOU)``; each tail reuses an encoding an earlier template already
executes. "Wizard" is a subtype, so it is SUBTYPE_EQ. The engine tests TYPE_EQ, SUBTYPE_EQ and
SUPERTYPE_EQ as one type-line word test today, so TYPE_EQ would fire too; SUBTYPE_EQ stays right
if the predicates split.

These rows match no template (test_templates_b10 pins them):

* Lithoform Engine's "Copy target instant or sorcery spell you control.": ``Verb.COPY`` has no
  executor dispatch, and a copy that never copies must not compile.
* Next-spell windows (Sea Gate Stormcaller's "copy the next instant or sorcery spell", Kaza,
  Roil Chaser's cost reduction): no replacement-duration mechanics.
* Base Camp's "Spend this mana only to ...": no mana restrictions.
* Myriad Construct's "When this creature becomes the target of a spell": no targeted-by event.
* Anticognition's "If an opponent has eight or more cards in their graveyard, instead counter
  that spell, then scry 2." (its first sentence compiles here).
* Master of Winds' "base power and toughness become 4/1 or 1/4": a choice between two P/T pairs.
* Relic Amulet's "Remove all charge counters ...: It deals that much damage": no quantity for
  the removed counters.
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CastSpellEvent,
    ControllerRef,
    Cost,
    CostManaGeneric,
    CounterKind,
    DurationEot,
    FAtom,
    FAtomPred,
    Filter,
    FOr,
    Keyword,
    KeywordAbility,
    OptionalEffect,
    PtDelta,
    PtDirection,
    QConst,
    Selector,
    SelectorMode,
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
from MTG_bot.core.compiler.templates_b6 import _draw_a_card, _self_selector

_BUCKET: Final[str] = "B10"
_PRIORITY: Final[int] = 118  # above every other bucket (test_templates_b10 checks it)

# The keywords the keyword-grant template accepts (as templates_b9._KW_MAP); an unmapped word
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
# Head + shared-shape helpers
# ---------------------------------------------------------------------------


def _instant_sorcery_or_wizard() -> Filter:
    """The cast head's spell filter: an instant or a sorcery (card types, TYPE_EQ) or a Wizard
    spell (a subtype, SUBTYPE_EQ). The executor's ``_match_cast`` judges it on the spell card."""
    return FOr(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Instant"),
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Sorcery"),
            FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Wizard"),
        )
    )


def _you_cast_event() -> CastSpellEvent:
    """``Whenever you cast an instant, sorcery, or Wizard spell``: actor YOU."""
    return CastSpellEvent(
        filter=_instant_sorcery_or_wizard(),
        actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
    )


def _any_target() -> Selector:
    """``any target`` (as templates_b2a._any_target). The Player branch never matches a card:
    it marks the shape for the engine's any-target widening."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FOr(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Player"),
            )
        ),
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _build_cast_kw_eot_self(m: re.Match[str]) -> SentenceOutcome:
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_you_cast_event(),
            condition=None,
            effect=Atom(
                verb=Verb.GRANT_ABILITY,
                args=AtomArgs(
                    pairs=(
                        ("target", _self_selector()),
                        ("ability", KeywordAbility(keyword=_KW_MAP[m.group("kw")])),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )


def _build_cast_may_draw(m: re.Match[str]) -> SentenceOutcome:
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_you_cast_event(),
            condition=None,
            effect=OptionalEffect(inner=_draw_a_card()),
        )
    )


def _build_cast_charge_self(m: re.Match[str]) -> SentenceOutcome:
    # The executor's _v_put_counter takes any counter kind, so CHARGE needs nothing new.
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_you_cast_event(),
            condition=None,
            effect=Atom(
                verb=Verb.PUT_COUNTER,
                args=AtomArgs(
                    pairs=(
                        ("target", _self_selector()),
                        ("counter_kind", CounterKind.CHARGE),
                        ("count", QConst(1)),
                    )
                ),
            ),
        )
    )


def _build_cast_self_damage_any(m: re.Match[str]) -> SentenceOutcome:
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_you_cast_event(),
            condition=None,
            effect=Atom(
                verb=Verb.DEAL_DAMAGE,
                args=AtomArgs(
                    pairs=(
                        ("target", _any_target()),
                        ("amount", QConst(int(m.group("n")))),
                    )
                ),
            ),
        )
    )


def _build_cast_self_pt_eot(m: re.Match[str]) -> SentenceOutcome:
    p, t = int(m.group("p")), int(m.group("t"))
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_you_cast_event(),
            condition=None,
            effect=Atom(
                verb=Verb.MODIFY_PT,
                args=AtomArgs(
                    pairs=(
                        ("target", _self_selector()),
                        ("power", PtDelta(PtDirection.INCREASE, QConst(p))),
                        (
                            "toughness",
                            PtDelta(PtDirection.INCREASE, QConst(t)),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )


def _build_counter_unless_cw_pw(m: re.Match[str]) -> SentenceOutcome:
    # The unless cost is a flat {N}: the spell's controller decides PAY or PASS and pays from
    # their own pool. (An unless amount that scales with a quantity would be counted in the
    # payer's seat; see Concerted Defense in templates_b8.)
    filter_ = FOr(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
        )
    )
    return EffectOutcome(
        effect=Atom(
            verb=Verb.COUNTER_SPELL,
            args=AtomArgs(
                pairs=(
                    # target_spell ANDs STACK_KIND_EQ SPELL with the type restriction.
                    ("target", target_spell(filter_)),
                    (
                        "unless",
                        Cost(
                            parts=(CostManaGeneric(amount=QConst(int(m.group("n")))),)
                        ),
                    ),
                )
            ),
        )
    )


# ---------------------------------------------------------------------------
# The registry tuple
# ---------------------------------------------------------------------------

_CAST_HEAD = r"Whenever you cast an instant, sorcery, or Wizard spell, "

TEMPLATES: tuple[Template, ...] = (
    _template(
        "B10-cast-kw-eot-self",
        "whenever you cast an instant, sorcery, or Wizard spell, this "
        "creature gains <keyword> until end of turn",
        r"^" + _CAST_HEAD + r"this creature gains "
        r"(?P<kw>deathtouch|indestructible|flying|lifelink) "
        r"until end of turn\.$",
        _build_cast_kw_eot_self,
    ),
    _template(
        "B10-cast-may-draw",
        "whenever you cast an instant, sorcery, or Wizard spell, you may draw a card",
        r"^" + _CAST_HEAD + r"you may draw a card\.$",
        _build_cast_may_draw,
    ),
    _template(
        "B10-cast-charge-self",
        "whenever you cast an instant, sorcery, or Wizard spell, put a "
        "charge counter on this artifact",
        r"^" + _CAST_HEAD + r"put a charge counter on this artifact\.$",
        _build_cast_charge_self,
    ),
    _template(
        "B10-cast-self-damage-any",
        "whenever you cast an instant, sorcery, or Wizard spell, this "
        "creature deals N damage to any target",
        r"^" + _CAST_HEAD + r"this creature deals (?P<n>\d+) damage "
        r"to any target\.$",
        _build_cast_self_damage_any,
    ),
    _template(
        "B10-cast-self-pt-eot",
        "whenever you cast an instant, sorcery, or Wizard spell, this "
        "creature gets +P/+T until end of turn",
        r"^" + _CAST_HEAD + r"this creature gets \+(?P<p>\d+)/\+(?P<t>\d+) "
        r"until end of turn\.$",
        _build_cast_self_pt_eot,
    ),
    _template(
        "B10-counter-unless-cw-pw",
        "counter target creature or planeswalker spell unless its controller pays {N}",
        r"^Counter target creature or planeswalker spell unless its "
        r"controller pays \{(?P<n>\d+)\}\.$",
        _build_counter_unless_cw_pw,
    ),
)
