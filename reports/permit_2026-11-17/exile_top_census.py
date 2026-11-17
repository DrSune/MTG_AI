"""The two forms of "exile the top card(s) of your library" over the 19 sets (compiler trees with
records applied): a MOVE_ZONE to exile whose target/cards selector is over the top of a library,
and the library pop to exile (pop_order TOP). Also the OptionalEffect-wrapped permission-like
atoms. Run from the worktree root."""
import sys
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
forms: dict[str, list] = {"selector": [], "pop": [], "wrapped": []}
WRAPPED = {at.Verb.ADD_LAND_PLAY, at.Verb.GRANT_ACTIVATION, at.Verb.MANA_POLICY}
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
        ver = card_records.is_verified(res, records.get(oid))
        for n in at.walk(res.card):
            if isinstance(n, at.Atom) and n.verb is at.Verb.MOVE_ZONE:
                dest = n.args.get("destination")
                if not (isinstance(dest, at.Zone) and dest.kind is at.ZoneKind.EXILE):
                    continue
                if n.args.get("pop_order") == "TOP":
                    forms["pop"].append((code, rc.identity.name, ver, str(n.args.get("amount"))))
                for role in ("target", "cards"):
                    sel = n.args.get(role)
                    if isinstance(sel, at.Selector) and any(
                            z.kind is at.ZoneKind.LIBRARY and z.position is at.ZonePosition.TOP for z in sel.zones):
                        forms["selector"].append((code, rc.identity.name, ver, f"{sel.mode.name} {sel.count}"))
            if isinstance(n, at.OptionalEffect) and isinstance(n.inner, at.Atom) and n.inner.verb in WRAPPED:
                forms["wrapped"].append((code, rc.identity.name, ver, n.inner.verb.name))
for k, rows in forms.items():
    print(k, len(rows), "verified", sum(1 for r in rows if r[2]))
    for r in sorted(rows):
        print("   ", r)
