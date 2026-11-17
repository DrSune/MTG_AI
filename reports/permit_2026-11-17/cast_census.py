"""Every CAST and PERMIT atom of the 19 sets (compiler trees with records applied, verified or not):
its source selector's mode, zones, referent, filter and roles. Run from the worktree root."""
import sys
from collections import Counter
from pathlib import Path

REPO = Path.cwd()
sys.path.insert(0, str(REPO))
import MTG_bot  # noqa: E402

assert Path(MTG_bot.__file__).resolve().is_relative_to(REPO.resolve()), MTG_bot.__file__
from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.compiler import card_records  # noqa: E402
from MTG_bot.core.compiler.compiler import compile_pool  # noqa: E402
from MTG_bot.core.compiler.coverage import build_full_registry  # noqa: E402
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
registry = build_full_registry()
rows = Counter()
for code in SETS:
    raw = ingest_pool(REPO / "MTG_bot" / "data" / f"{code}.json")
    records = card_records.load_records(code)
    for oid, rc in raw.items():
        if rc.is_token or rc.is_emblem:
            continue
        try:
            res = compile_pool({oid: rc}, registry, records=records, require_verified=False).results[oid]
        except Exception:  # noqa: BLE001
            continue
        for n in at.walk(res.card):
            if isinstance(n, at.Atom) and n.verb in (at.Verb.CAST, at.Verb.PERMIT):
                sel = n.args.get("source")
                zones = tuple(f"{z.kind.name}:{z.controller.name}{':' + z.position.name if z.position else ''}"
                              for z in sel.zones) if isinstance(sel, at.Selector) else ()
                roles = tuple(sorted(r for r, _ in n.args.pairs if r != "source"))
                key = (n.verb.name, sel.mode.name if isinstance(sel, at.Selector) else type(sel).__name__,
                       zones, getattr(sel, "referent", None), roles)
                rows[key] += 1
                print(code, "|", rc.identity.name, "|", key, "|", at.canonical_json(sel.filter)[:120] if isinstance(sel, at.Selector) else "")
print()
for k, v in sorted(rows.items(), key=str):
    print(v, k)
