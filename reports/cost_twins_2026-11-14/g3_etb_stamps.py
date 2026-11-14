"""The verified stamps of the cards whose G3 the stillborn-mutant bug emptied (an "As this enters"
node that only taps or puts counters): per card, the stamp's date and its recorded mutation block
(a stamp made while the bug lived records 0 mutants). Run from the repo root:

    .venv/bin/python reports/cost_twins_2026-11-14/g3_etb_stamps.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.compiler import card_records  # noqa: E402
from MTG_bot.core.executor.games import compile_supply  # noqa: E402

for code in ("M21", "M20", "FDN"):
    sup = compile_supply("all", code, require_verified=False)
    records = card_records.load_records(code)
    for oid, res in sorted(sup.pool.results.items(), key=lambda kv: kv[1].card.name):
        rec = records.get(oid, {})
        if not card_records.is_verified(res, rec):
            continue
        if not any(isinstance(a, at.EtBState) and a.effect is None for a in res.card.abilities):
            continue
        mutation = rec["verified"].get("mutation") or {}
        brief = {k: mutation.get(k) for k in ("mutants", "killed", "score") if k in mutation}
        print(code, res.card.name, "|", rec["verified"].get("date"), "|", brief or mutation)
