"""The verified stamps of the cards whose G3 the stillborn-mutant bug emptied (an "As this enters"
node that only taps or puts counters), in every set: per card, the stamp's date, the home set of a
reprint stamp (``verify --reprint-of``) and its recorded mutation block. The bug lived from
774fa6b9 (2026-11-13) to this round's fix: a stamp made then records 0 mutants, flagged EMPTY when
its home stamp, made before, records some (M19 Diregraf Ghoul's 0 is its home's, and the fixed
G3's). Run from the repo root:

    .venv/bin/python reports/cost_twins_2026-11-14/g3_etb_stamps.py
"""
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.compiler import card_records  # noqa: E402
from MTG_bot.core.executor.games import compile_supply  # noqa: E402

stamps: Counter = Counter()
for code in sorted(p.stem for p in (REPO / "MTG_bot" / "data").glob("*.json")):
    sup = compile_supply("all", code, require_verified=False)
    records = card_records.load_records(code)
    for oid, res in sorted(sup.pool.results.items(), key=lambda kv: kv[1].card.name):
        rec = records.get(oid, {})
        if not card_records.is_verified(res, rec):
            continue
        home = rec["verified"].get("reprint_of")
        stamps["reprint" if home else f"home {code}"] += 1
        if not any(isinstance(a, at.EtBState) and a.effect is None for a in res.card.abilities):
            continue
        mutation = rec["verified"].get("mutation") or {}
        brief = {k: mutation.get(k) for k in ("mutants", "killed", "score") if k in mutation}
        date = rec["verified"].get("date")
        before = card_records.load_records(home)[oid]["verified"] if home else {}
        empty = (date >= "2026-11-13" and not mutation.get("mutants")
                 and (before.get("mutation") or {}).get("mutants"))
        print(code, res.card.name, "|", date, "|", f"reprint of {home}" if home else "home", "|",
              brief or mutation, "| EMPTY" if empty else "")
print("verified stamps:", sum(stamps.values()), dict(sorted(stamps.items())))
