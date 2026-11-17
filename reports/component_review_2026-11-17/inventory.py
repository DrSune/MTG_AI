"""Measure 3's inventory: every closed-vocabulary component (verbs, filter predicates, quantity
fields, events, durations, cost parts, keywords, counter kinds, selector modes, player refs), with
the number of cards using it among the verified cards of M21, M20 and FDN and among the compiled
trees of the 19 sets, and the enum members no tree uses.

    .venv/bin/python reports/component_review_2026-11-17/inventory.py > reports/component_review_2026-11-17/inventory.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import common as C

from MTG_bot.core import ability_tree as at

FAMILIES = (
    ("Verb", at.Verb), ("FAtomPred", at.FAtomPred), ("QPropField", at.QPropField),
    ("ThisTurnKind", at.ThisTurnKind), ("QAgg", at.QAgg), ("QBinOp", at.QBinOp),
    ("Keyword", at.Keyword), ("CounterKind", at.CounterKind), ("SelectorMode", at.SelectorMode),
    ("ControllerRef", at.ControllerRef), ("ZoneKind", at.ZoneKind), ("SpellKind", at.SpellKind),
    ("Phase", at.Phase), ("Step", at.Step), ("AbilityKind", at.AbilityKind),
)
CLASS_TOKENS = (
    "Quantity: QConst(num:*) QX QUnbounded QCount QPartyCount QDistinctColorCount QProp QBin QThisTurn "
    "QAtLeast QAtMost",
    "Event: ZoneChangeEvent CastSpellEvent DeclareAttackersEvent DeclareBlockersEvent CounterPlacedEvent "
    "CreatureDiesEvent BecomesBlockedEvent TapStateEvent PhasingEvent AbilityTriggerEvent TurnPhaseEvent "
    "StepEvent DamageDealtEvent TargetingEvent CardDrawnEvent LifeGainedEvent LifeLostEvent CounteredEvent "
    "SacrificeEvent AbilityActivatedEvent",
    "Duration: DurationEot DurationPermanent DurationUntilNextTurn DurationUntilEndOfNextTurn "
    "DurationWhileCondition DurationUntilNextStep DurationUntilLeaves",
    "Cost: CostTap CostManaColor CostManaGeneric CostManaHybrid CostLife CostSacrifice CostDiscard "
    "CostPutCounter CostExile CostRemoveCounter CostLoyalty CostDeltaReduceGeneric CostDeltaIncreaseGeneric "
    "CostDeltaReduceMana CostDeltaIncreaseLife CostDeltaWaiveMana",
    "Effect node: Atom Seq Choose OptionalEffect Conditional Repeat EachPlayer DelayedTrigger",
    "Ability: StaticAbility TriggeredAbility ActivatedAbility SpellAbility KeywordAbility "
    "ReplacementAbility CostModifier EtBState KickerAbility BackFace",
    "Filter: FAnd FOr FNot FAtom",
    "Value: TokenSpec EmblemSpec PtDelta LiteralName",
)


def main() -> None:
    rows = C.load()
    ver, allc = C.verified_home(rows), C.compiled_all(rows)
    dv, da = C.doc_freq(ver), C.doc_freq(allc)
    print(f"# Component inventory: cards using each (verified M21+M20+FDN {len(ver)} | compiled 19 sets {len(allc)})")
    unused = []
    for fam, enum in FAMILIES:
        print(f"\n## {fam} ({len(enum)} members)")
        items = sorted(enum, key=lambda m: (-da.get(f'{fam}.{m.name}', 0), m.name))
        for m in items:
            tok = f"{fam}.{m.name}"
            v, a = dv.get(tok, 0), da.get(tok, 0)
            flag = "" if a else "   <- no tree"
            if not a:
                unused.append(tok)
            print(f"  {m.name:36s} {v:5d} | {a:5d}{flag}")
    for line in CLASS_TOKENS:
        title, names = line.split(": ", 1)
        print(f"\n## {title} classes")
        for name in names.split():
            tok = name.split("(")[0]
            v, a = dv.get(tok, 0), da.get(tok, 0)
            print(f"  {tok:36s} {v:5d} | {a:5d}" + ("" if a else "   <- no tree"))
    print("\n## num tokens (QConst values and other integers, bucketed)")
    for b in ("num:0", "num:1", "num:2", "num:3", "num:4", "num:5", "num:6+", "num:neg", "num:?"):
        print(f"  {b:10s} {dv.get(b, 0):5d} | {da.get(b, 0):5d}")
    print(f"\nenum members no tree of the 19 sets uses ({len(unused)}): " + ", ".join(unused))


if __name__ == "__main__":
    main()
