"""Census of the 19 sets' trees (records applied, verified or not) for IS_ATTACKING / IS_BLOCKING:
where each one stands (a Conditional's predicate, a trigger event's filter or condition, a selector
filter, a static's condition), and whether the tree is verified.

    census_attacking.py <checkout>
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.compiler import card_records  # noqa: E402
from MTG_bot.core.compiler.compiler import compile_pool  # noqa: E402
from MTG_bot.core.compiler.coverage import build_full_registry  # noqa: E402
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402
from MTG_bot.core.errors import StateCorruptionError  # noqa: E402

PREDS = {at.FAtomPred.IS_ATTACKING, at.FAtomPred.IS_BLOCKING}
SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")


def has(node):
    return any(isinstance(n, at.FAtom) and n.pred in PREDS for n in at.walk(node))


registry = build_full_registry()
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
        if res.card is None:
            continue
        verified = "verified" if card_records.is_verified(res, records.get(oid)) else "unverified"
        for n in at.walk(res.card):
            where = None
            if isinstance(n, at.Conditional) and has(n.pred):
                where = "Conditional.pred"
            elif isinstance(n, at.TriggeredAbility):
                if has(n.event):
                    where = f"trigger event {type(n.event).__name__}"
                if n.condition is not None and has(n.condition):
                    where = "trigger condition"
            elif isinstance(n, at.StaticAbility) and n.condition is not None and has(n.condition):
                where = "static condition"
            if where:
                print(code, rc.identity.name, verified, where)
