"""Conditionals of the 19 sets (records applied) whose predicate reads only characteristics once
PT_LE, PT_GE, KEYWORD_HAS, NAME_CONTAINS and HAS_KICKER count as characteristic tests. Run on
the base (main 30736aba), whose set lacks them: no line printed = no Conditional changes reading.

    survey_cond_preds.py <checkout>
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from MTG_bot.core import ability_tree as at
from MTG_bot.core.compiler import card_records
from MTG_bot.core.compiler.compiler import compile_pool
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.errors import StateCorruptionError
from MTG_bot.core.executor import _CHARACTERISTIC_PREDS

EXTRA = {at.FAtomPred.PT_LE, at.FAtomPred.PT_GE, at.FAtomPred.KEYWORD_HAS, at.FAtomPred.NAME_CONTAINS,
         at.FAtomPred.HAS_KICKER}


def chars_only(pred, preds) -> bool:
    if isinstance(pred, (at.FAnd, at.FOr)):
        return bool(pred.children) and all(chars_only(c, preds) for c in pred.children)
    if isinstance(pred, at.FNot):
        return chars_only(pred.inner, preds)
    return isinstance(pred, at.FAtom) and pred.pred in preds


SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
registry = build_full_registry()
wide = set(_CHARACTERISTIC_PREDS) | EXTRA
for code in SETS:
    raw = ingest_pool(ROOT / "MTG_bot" / "data" / f"{code}.json")
    records = card_records.load_records(code)
    for oid, rc in raw.items():
        if rc.is_token or rc.is_emblem:
            continue
        try:
            res = compile_pool({oid: rc}, registry, records=records, require_verified=False).results[oid]
        except (StateCorruptionError, ValueError):
            continue
        ver = "VERIFIED" if card_records.is_verified(res, records.get(oid)) else "-"
        for n in at.walk(res.card):
            if isinstance(n, at.Conditional):
                old, new = chars_only(n.pred, _CHARACTERISTIC_PREDS), chars_only(n.pred, wide)
                if old != new:
                    print(code, "|", rc.identity.name, "|", ver, "|", repr(n.pred)[:150])
