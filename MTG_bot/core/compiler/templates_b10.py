"""Bucket B10 — the ZND-5 spell-kind round (spec KNOWLEDGE/2026-10-19/121).

Six templates clear six register rows. Every build composes the
CONJUNCTIVE CAST head ("Whenever you cast an instant, sorcery, or Wizard
spell, ...") — ``CastSpellEvent(filter=FOr(TYPE_EQ Instant,
TYPE_EQ Sorcery, SUBTYPE_EQ Wizard), actor=CONTROLLER_IS YOU)`` — with
tail builders that REUSE already-executed carriers (FM6 shared-tail law:
each docstring names the executed carrier its executor falsifier covers).

Head vocabulary (spec /121, gate-verified [G-A1], CORRECTED same night
by the diff gate — TYPE_EQ/SUBTYPE_EQ/SUPERTYPE_EQ are ONE shared
type-line word-test in the engine (quantity.py:726), so the atom-kind
choice is BEHAVIORALLY NEUTRAL today; TYPE_EQ("Wizard") would also
fire. SUBTYPE_EQ stays mandated because it is the CR-correct IR
("Wizard" is a SUBTYPE) and survives a future strict TYPE_EQ; the
encoding is pinned by the structural IR test, and the executor
falsifiers pin the behavior axes that DO matter — never-fire /
always-fire (matching-kind positive AND non-matching-cast negative
per trigger board — the P0 shape of this round).
* The OR composition is the executed b5a precedent FOr(TYPE_EQ Instant,
  TYPE_EQ Sorcery) (templates_b5a._build_counter_unless_sps, b5a:396);
  the third type∪subtype branch is structurally trivial per the gate.

Priority is PINNED 118 (spec /121 [G-A7]): the ladder is
100/110/112/114/116; b10 heads must run BEFORE b2b's Cat/Dog/noncreature
cast-trigger heads and never co-claim them (regex-disjointness probe in
test_templates_b10.py + templates.py:227 sorts (−priority, tid)).

Gap ledger (ZND-5 named defers — these rows stay UNPARSED, no silent
partials, no forced lanes — spec /121 SPEC-GATE REVISIONS):

* **ZND-5a** "Copy target instant or sorcery spell you control."
  (Lithoform Engine) — ``Verb.COPY`` has NO executor dispatch at all
  (executor/__init__.py:228–237) and the stack vocab-gate EXCLUDES
  COPY-bearing cards from executable resolution (stack.py:510–538).
  Compile-emitting a copy that never copies is the FM2 sin — engine
  lane, never a template job.
* **ZND-5b** next-spell replacement windows (Sea Gate Stormcaller's
  "copy the next instant or sorcery spell … when you cast it"; Kaza,
  Roil Chaser's cost-waiver window) — replacement-duration mechanics
  absent; the kicked-twin row is additionally cross-sentence anaphora.
* **ZND-5c** Base Camp "Spend this mana only to …" — mana-restriction
  lane absent.
* **ZND-5d** Myriad Construct "When this creature becomes the target
  of a spell" — targeted-BY event absent (register volume 1–2).
* **ZND-5e** Anticognition s2 "If an opponent has eight or more cards
  in their graveyard, instead counter that spell, then scry 2." —
  threshold + "instead" replacement window; s1 (this bucket) compiles,
  so Anticognition is a 2-row residue feeding PC-2, NOT a flip.
* **ZND-5f** Master of Winds "… base power and toughness become 4/1 or
  1/4 …" — may + TWO-WAY PT-PAIR CHOICE FORK, not a tail reuse.
* Carried: ZND-3d/e/f/g, ZND-4a/b/c, anaphora rows (incl. Relic
  Amulet's "{2}, {T}, Remove all charge counters … It deals that much
  damage" activation row — quantity-of-removed-counters damage has no
  lane, so Relic Amulet is a 2-row residue feeding PC-2, not a flip).
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
_PRIORITY: Final[int] = 118  # G-A7: ladder 100/110/112/114/116, b10 sits above all

# Keyword words the keyword-grant template accepts — the closed b3/b9 map
# (templates_b9._KW_MAP); an unmapped word never compiles.
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
    """The conjunctive cast head's spell filter: an instant, a sorcery
    (CARD TYPES → TYPE_EQ) or a Wizard spell (SUBTYPE → SUBTYPE_EQ).
    ``_match_cast`` (executor/binding.py:957–990) evaluates this filter
    over the SPELL card. Atom-kind note (diff gate, corrected): the
    engine word-tests TYPE_EQ/SUBTYPE_EQ/SUPERTYPE_EQ identically
    (quantity.py:726) — SUBTYPE_EQ is the CR-correct IR (and survives a
    strict-predicate future), pinned by the structural IR test; the
    executor tests pin the firing BEHAVIOR axes (positive per branch,
    negative for non-matching casts)."""
    return FOr(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Instant"),
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Sorcery"),
            FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Wizard"),
        )
    )


def _you_cast_event() -> CastSpellEvent:
    """``Whenever you cast an instant, sorcery, or Wizard spell`` —
    actor = YOU (E1 merged direction axis), the b2b builder pattern
    (templates_b2b._cast_subtype_token_builder, b2b:1222)."""
    return CastSpellEvent(
        filter=_instant_sorcery_or_wizard(),
        actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
    )


def _any_target() -> Selector:
    """``any target`` — verbatim the executed r17-2 idiom (carrier:
    templates_b2a._any_target, b2a:227; the third Player branch is the
    engine-widening discriminator, NEVER a card match)."""
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
# Builders — every tail mirrors an EXECUTED carrier
# ---------------------------------------------------------------------------


def _build_cast_kw_eot_self(m: re.Match[str]) -> SentenceOutcome:
    # TAIL CARRIER: B4-grant-kw-eot-self idiom executed through the same
    # GRANT_ABILITY + DurationEot payload over _self_selector as the
    # executor-executed B5b-sacr-grant TARGET grant (templates_b5b) and
    # b9's ETB self/indestructible twin — here the self gains <kw> UET.
    # Head CARRIER: CastSpellEvent feed executed by the Quirion Dryad
    # filter falsifier (test_executor_stack.TestCastTriggerFeed).
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
    # TAIL CARRIER: the executed OptionalEffect(DRAW YOU 1) of
    # B2a-solemn-simulacrum (templates_b2a:1123 — "you may draw a card"),
    # recomposed over the b6 _draw_a_card anchor (FM6).
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_you_cast_event(),
            condition=None,
            effect=OptionalEffect(inner=_draw_a_card()),
        )
    )


def _build_cast_charge_self(m: re.Match[str]) -> SentenceOutcome:
    # TAIL CARRIER: the executed PUT_COUNTER self shape of
    # B9-gain-life-counter-self / the Dryad PUT_COUNTER
    # (executor/binding.py:750); the counter kind is CHARGE — the
    # executor's _v_put_counter is kind-agnostic (verbs.py ~715:
    # counters[kind.name] += n), so the artifact host needs no lane.
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
    # TAIL CARRIER: the executed DEAL_DAMAGE + _any_target shape of
    # B2a-meteorite / B2a-pitchburn-devils (templates_b2a:2437/2461 —
    # "it deals N damage to any target", dealer = the trigger's source).
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
    # TAIL CARRIER: the executed MODIFY_PT self + DurationEot shape of
    # B2b-draw-self-boost (templates_b2b._build_burlfist_oak_draw_boost,
    # b2b:1405) — only the event head differs.
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
    # CARRIER: B5a-counter-unless executed lane — the STACK-zone TARGET
    # selector + "unless" Cost atom (templates_b5a._counter_unless_atom,
    # b5a:356), with the executed two-branch FOr TYPE_EQ idiom
    # (b5a._build_counter_unless_sps, b5a:396; here Creature ∪
    # Planeswalker).
    # PAYER-SEAT SAFETY (spec /121 G-A5): the unless cost is a FLAT
    # {2}, so the counter's PAY/PAYMENT decision seats on the spell's
    # CONTROLLER through the executed kickback path
    # (executor/verbs.py:1926 — payer = frame.controller, the PAY/PASS
    # digest decision). ZND-3d is the QUANTITY-scaling unless class
    # only — a flat amount is not that class.
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
                    # R5-10: STACK_KIND_EQ SPELL ANDed with the type restriction.
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
