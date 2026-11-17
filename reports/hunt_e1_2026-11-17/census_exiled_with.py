"""Which cards of the 19 sets read IS_EXILED_WITH_SOURCE (their compiled trees, records applied),
and which of them are verified; and the same for IS_ATTACHED_TO_SOURCE in a trigger event of an
Aura whose effect moves the Aura out of a graveyard (the CR 113.6m Aura exception).

    census_exiled_with.py <checkout>
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
from MTG_bot.core.executor.binding import functions_from_graveyard  # noqa: E402

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
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
        nodes = list(at.walk(res.card))
        verified = card_records.is_verified(res, records.get(oid))
        if any(isinstance(n, at.FAtom) and n.pred is at.FAtomPred.IS_EXILED_WITH_SOURCE for n in nodes):
            print("EXILED_WITH", code, rc.identity.name, "verified" if verified else "unverified")
        aura = "Aura" in res.card.subtypes  # as the binder reads it (CR 113.6m)
        gy = [a for a in res.card.abilities if functions_from_graveyard(a, aura)]
        if gy:
            print("GRAVEYARD-ONLY", code, rc.identity.name, "verified" if verified else "unverified",
                  rc.identity.type_line)
