"""Render card records' STORED trees as drafts, run under the checkout whose IR they were written
for (main 0b7f9c22 for gate round W3's re-map): the stored ``ir`` is the record, its
``mapping.draft_py`` may be older (Brightwood Tracker's draft predates round 5's "in a random
order", which a later write put in the ir only). Each draft is written as <SET>_<name>.py beside
the record's clauses, for patch_drafts.py and remap_records.py.

    render_records.py <checkout> <out dir> <record path>...
"""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2])
sys.path[:0] = [str(ROOT), str(ROOT / "tools" / "cards")]
import irpy  # noqa: E402

from MTG_bot.core.compiler.card_records import decode_ir  # noqa: E402

OUT.mkdir(parents=True, exist_ok=True)
for rel in sys.argv[3:]:
    d = json.loads((ROOT / rel).read_text())
    stem = f"{d['set']}_{d['name'].replace(' ', '_').replace(',', '').replace(chr(39), '')}"
    if "ir" not in d:
        print(stem, "no stored tree")
        continue
    keywords, abilities = decode_ir(d["ir"])
    head = f"# {d['set']} {d['name']}: the record's stored tree (rendered by render_records.py)\n"
    (OUT / f"{stem}.py").write_text(head + irpy.render_card(keywords, abilities) + "\n")
    clauses = (d.get("mapping") or {}).get("clauses") or (d.get("verified") or {}).get("clauses") or []
    (OUT / f"{stem}.clauses.json").write_text(json.dumps(
        [{"clause": c["clause"], "ir": c["ir"]} for c in clauses if "ir" in c], indent=1))
    print(stem, "rendered", len(abilities), "abilities")
