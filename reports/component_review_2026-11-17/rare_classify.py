"""Measure 1, last part: the tokens 1-2 verified cards use, and which of them could be an existing
token plus a parameter, or a composition of existing tokens. The reviewer's reading, one line per
component (``READING``); face values and string values are classed by rule.

    .venv/bin/python reports/component_review_2026-11-17/rare_classify.py > reports/component_review_2026-11-17/rare_classify.txt
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

COMP, PARAM, KEEP, PART = "composition of existing tokens", "existing token + a parameter", "a distinct primitive or value: keep", "a field or role that goes with its node"

#: token -> (class, how; the proposal it falls under)
READING = {
    "FAtomPred.CARDS_DRAWN_THIS_TURN_GE": (COMP, "EVENT_THIS_TURN over CardDrawnEvent (I2)"),
    "FAtomPred.CAST_THIS_TURN_FROM": (COMP, "EVENT_THIS_TURN over CastSpellEvent from a zone (I2)"),
    "FAtomPred.ENTERED_THIS_TURN_FROM": (COMP, "SUBJECT_OF_EVENT_THIS_TURN over ZoneChangeEvent (I2)"),
    "FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN": (COMP, "EVENT_THIS_TURN over CastSpellEvent(instant or sorcery) (I2)"),
    "FAtomPred.NOT_FIRST_DRAW_THIS_STEP": (COMP, "CardDrawnEvent's ordinal within the draw step (I2)"),
    "FAtomPred.CONTROLLER_COUNT_GT": (COMP, "QTY_GE(QCount A, QCount B + 1) (I1)"),
    "QPropField.CARDS_IN_GRAVEYARD": (COMP, "QCount over a graveyard selector"),
    "QPropField.CARDS_IN_HAND": (COMP, "QCount over a hand selector"),
    "QThisTurn": (COMP, "a quantity over this turn's events (I2)"),
    "ThisTurnKind.NONCOMBAT_DAMAGE": (COMP, "the amounts of this turn's DamageDealtEvent(combat False) (I2)"),
    "BecomesBlockedEvent": (COMP, "candidate: DeclareBlockersEvent(blocked=subject), once per creature (CR 509.3c); needs a CR reading"),
    "FAtomPred.CMC_GE": (PARAM, "QTY_GE over QProp MANA_VALUE (I1)"),
    "FAtomPred.COLOR_COUNT_GE": (PARAM, "QTY_GE over QDistinctColorCount (I1)"),
    "FAtomPred.LIFE_LEAD_OVER_START_GE": (PARAM, "QTY_GE over life minus starting life (I1, ledger F11)"),
    "FAtomPred.LIFE_TOTAL_GE": (PARAM, "QTY_GE over QProp(controller, LIFE) (I1)"),
    "FAtomPred.POWER_LE": (PARAM, "FNot(QTY_GE over QProp POWER) (I1)"),
    "FAtomPred.NAME_PARTITION_COUNT_GE": (PARAM, "QTY_GE over a largest-same-name-group quantity (I1)"),
    "QDistinctColorCount": (PARAM, "a distinct count with a property slot (colour, mana value, name)"),
    "Verb.ATTACK_POLICY": (PARAM, "POLICY with a scope (I6)"),
    "Verb.DAMAGE_ASSIGN_POLICY": (PARAM, "POLICY with a scope (I6)"),
    "Verb.GRANT_ACTIVATION": (PARAM, "POLICY with a scope: activation timing (I6)"),
    "Verb.MANDATE_BLOCK": (PARAM, "MANDATE with a scope (I6)"),
    "FAtomPred.IS_ATTACHED_TO": (PARAM, "the general form of IS_ATTACHED_TO_SOURCE (125 trees): fold the frequent one into it only with a re-bake"),
    "PhasingEvent": (PARAM, "a status-change event with a status slot, beside TapStateEvent (ledger F10)"),
    "FAtomPred.FLIP_WON": (KEEP, "a coin flip's result"),
    "FAtomPred.IS_EXILED_WITH_SOURCE": (KEEP, "linked abilities (CR 607)"),
    "FAtomPred.IS_RESULT": (KEEP, "the result anaphora as a filter"),
    "FAtomPred.SUBJECT_OF_EVENT_THIS_TURN": (KEEP, "the general turn-history form (I2's target)"),
    "FAtomPred.WAS_CAST_THIS_TURN": (KEEP, "B-44: only it follows the spell onto the battlefield (CR 400.7c)"),
    "Verb.ADD_LAND_PLAY": (KEEP, "a rules action"), "Verb.CAST": (KEEP, "a rules action"),
    "Verb.END_TURN": (KEEP, "a rules action"), "Verb.EXTRA_TURN": (KEEP, "a rules action"),
    "Verb.FLIP_COIN": (KEEP, "a rules action"), "Verb.LOSE_GAME": (KEEP, "a rules action"),
    "Verb.PHASE_OUT": (KEEP, "a rules action"), "Verb.TRIGGER_ADDITIONAL": (KEEP, "a rules action"),
    "Verb.REMOVE_COUNTER": (KEEP, "a rules action (removing is not putting a negative number, CR 122)"),
    "QAgg.MAX": (KEEP, "a value"), "QAgg.SUM": (KEEP, "a value"), "QBinOp.DIV": (KEEP, "a value"),
    "Rounding.CEIL": (KEEP, "a value"), "QPropField.LIFE": (KEEP, "a value"), "QPropField.MANA_VALUE": (KEEP, "a value"),
    "QPropField.THIS_WAY_COUNT": (KEEP, "a value"),
    "AbilityActivatedEvent": (KEEP, "an event"), "AbilityKind.LOYALTY": (KEEP, "a value"),
    "AbilityKind.NON_MANA": (KEEP, "a value"), "AbilityTriggerEvent": (KEEP, "an event"),
    "Phase.UPKEEP": (KEEP, "a value"), "SacrificeEvent": (KEEP, "an event (CR 701.21)"),
    "Step.UNTAP": (KEEP, "a value"), "TargetingEvent": (KEEP, "an event"),
    "CostDeltaIncreaseLife": (KEEP, "a cost delta"), "CostDeltaReduceMana": (KEEP, "a cost delta"),
    "CostLife": (KEEP, "a cost part (F3 ruled)"), "CostPutCounter": (KEEP, "a cost part (F3 ruled)"),
    "CounterKind.INCARNATION": (KEEP, "a value"), "CounterKind.PAGE": (KEEP, "a value"), "CounterKind.SOUL": (KEEP, "a value"),
    "DurationUntilEndOfNextTurn": (KEEP, "a duration"), "DurationUntilNextStep": (KEEP, "a duration"),
    "DurationUntilNextTurn": (KEEP, "a duration"), "ControllerRef.DEFENDING_PLAYER": (KEEP, "a value"),
    "ActivationWindow.INSTANT": (PART, "GRANT_ACTIVATION's window"),
    "@extra_deltas": (PART, ""), "@from_zone_not": (PART, ""), "@owner_scoped": (PART, ""), "@phased_in": (PART, ""),
    "@right_inner_filter": (PART, "goes with CONTROLLER_COUNT_GT (I1)"), "@rounding": (PART, ""), "@step": (PART, ""),
    "role:name_filter": (PART, ""), "role:source": (PART, ""), "role:step": (PART, ""), "role:window": (PART, ""),
}
SCOPES = {"ACTIVATED", "TRIGGERED", "ALL_YOURS", "AS_NO_DEFENDER", "AS_UNBLOCKED", "THIS_MANA", "COLOR",
          "CREATURE_TYPE"}


def main() -> None:
    rows = C.load()
    ver, allc = C.verified_home(rows), C.compiled_all(rows)
    dv, da = C.doc_freq(ver), C.doc_freq(allc)
    names = {r["name"] for r in rows} | {p for r in rows for p in r["name"].split(" // ")}
    face_vals = {t.split(":", 1)[1] for r in allc for t in r["face"] if t.startswith(("type:", "sub:"))}
    str_vals = {t[4:] for r in allc for t in r["tokens"] if t.startswith("str:")}
    rare = sorted(t for t, n in dv.items() if n <= 2)
    groups = defaultdict(list)
    for t in rare:
        k = C.kind(t)
        if k == "face":
            v = t.split(":", 1)[1]
            cls = ("a face value with a filter twin (str:): shared under N3" if v in str_vals
                   else "a face value (a type or subtype): data, not a component")
            groups[cls].append(t)
        elif k == "string":
            v = t[4:]
            if v in names:
                cls = "a card name (a reference: I5/N2)"
            elif v in SCOPES:
                cls = "a scope or quality value of an existing verb"
            elif v in face_vals:
                cls = "a type or subtype in a filter, with a face twin (type:/sub:): shared under N3"
            else:
                cls = "another string value"
            groups[cls].append(t)
        else:
            cls, how = READING.get(t, ("UNREAD", ""))
            groups[cls].append(f"{t} [{how}]" if how else t)
    print(f"# The {len(rare)} tokens 1-2 verified cards use, by what they are")
    order = [COMP, PARAM, KEEP, PART]
    for cls in order + sorted(set(groups) - set(order)):
        if cls not in groups:
            continue
        print(f"\n## {cls}: {len(groups[cls])}")
        for t in groups[cls]:
            base = t.split(" [")[0]
            print(f"  {t}   (verified {dv.get(base, 0)}, 19 sets {da.get(base, 0)})")
    comp_param = [t for c in (COMP, PARAM) for t in groups.get(c, [])]
    print(f"\nnon-value components among them: {sum(len(groups[c]) for c in order if c in groups)}; "
          f"composition {len(groups.get(COMP, []))}, existing + parameter {len(groups.get(PARAM, []))}, "
          f"keep {len(groups.get(KEEP, []))}, structural {len(groups.get(PART, []))}")


if __name__ == "__main__":
    main()
