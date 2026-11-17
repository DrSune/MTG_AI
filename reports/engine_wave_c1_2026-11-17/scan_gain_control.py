"""GAIN_CONTROL atoms (their controller role and duration), triggers running an EachPlayer as a
designated player, and Conditionals right after a look, in the 19 sets (records applied), with
each card's verified flag.

    scan_gain_control.py <checkout>
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

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
registry = build_full_registry()
LOOKS = (at.Verb.LOOK_AT, at.Verb.REVEAL)


def seq_pairs(node):
    """(prev, next) step pairs of every Seq."""
    for n in at.walk(node):
        if isinstance(n, at.Seq):
            for a, b in zip(n.steps, n.steps[1:]):
                yield a, b


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
        name = rc.identity.name
        for n in at.walk(res.card):
            if isinstance(n, at.Atom) and n.verb is at.Verb.GAIN_CONTROL:
                print("GAIN_CONTROL", code, "|", name, "|", ver, "| controller:", n.args.get("controller"),
                      "| duration:", type(n.args.get("duration")).__name__)
            if isinstance(n, (at.TriggeredAbility,)):
                for m in at.walk(n.effect):
                    if isinstance(m, at.EachPlayer) and m.ref in (at.ControllerRef.TARGET_PLAYER,
                                                                   at.ControllerRef.TARGET_OPPONENT):
                        print("TRIGGER_EACHPLAYER_TARGET", code, "|", name, "|", ver)
        for a, b in seq_pairs(res.card):
            if isinstance(a, at.Atom) and a.verb in LOOKS and isinstance(b, at.Conditional):
                print("COND_AFTER_LOOK", code, "|", name, "|", ver, "| pred:", repr(b.pred)[:160])
