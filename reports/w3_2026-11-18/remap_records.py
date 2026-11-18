"""Re-map the card records gate round W3 changes, through ``cardtool write`` (G0, the probe; no
``verified`` block: each leaves the verified pool until re-verified).

The drafts are each record's STORED tree, rendered under main by render_records.py (a record's
``mapping.draft_py`` can be older than its tree: Brightwood Tracker's predates its "in a random
order"), with each reveal patched into its one encoding by patch_drafts.py (DESIGN_ATOM_ONTOLOGY
§20). Yarok, the Desecrated's needs-atom record becomes the compiler's tree (the new extra-trigger
template). M19 Vivien Reid, a reprint record with no mapping of its own, takes FDN's clauses.

    remap_records.py <drafts dir> [card name...]
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools" / "cards")]
import cardtool  # noqa: E402

DRAFTS = Path(sys.argv[1])
NOTE = ("Re-mapped by ontology gate round W3 (DESIGN_ATOM_ONTOLOGY §20) from the stored tree: {what}. "
        "Nothing else changed.")
HAND = "the reveal names the hand, reveal_hand(TARGET_OPPONENT)"
FOUND = "\"reveal it|them\" is reveal_result(), the cards the search found"
PICK = "\"reveal ... from among them and put it into your hand\": the move's pick, then reveal_result()"
ROWS = (
    ("FDN", "Pilfer", HAND),
    ("M20", "Thought Distortion", HAND),
    ("FDN", "Campus Guide", FOUND),
    ("FDN", "Expedition Map", FOUND),
    ("FDN", "Micromancer", FOUND),
    ("M20", "Chandra's Flame Wave", FOUND),
    ("M20", "Battalion Foot Soldier", FOUND),
    ("FDN", "Vivien Reid", PICK),
    ("M19", "Vivien Reid", PICK + " (FDN Vivien Reid's clauses: the same printed card)"),
    ("FDN", "Squad Rallier", PICK),
    ("FDN", "Loot, Exuberant Explorer", PICK),
    ("M20", "Brightwood Tracker", PICK),
    ("M20", "Icon of Ancestry", PICK),
    ("M20", "Yarok, the Desecrated",
     "the needs-atom note's trigger-cause axis is AbilityTriggerEvent.cause; the compiler's tree "
     "(B5b-entering-extra-trigger), a static TRIGGER_ADDITIONAL"),
)


def stem(code: str, card: str) -> str:
    return f"{code}_{card.replace(' ', '_').replace(',', '').replace(chr(39), '')}"


only = set(sys.argv[2:])
rows = [row for row in ROWS if not only or row[1] in only]
# A set's records are compiled together (cardtool's probe builds the whole set's supply), and the
# old reveals no longer validate, so every listed record's stored tree is dropped first; each
# write below then writes the record whole again from its patched draft.
for code, card, _what in rows:
    sc = cardtool.corpus.compile_set(code)
    path = cardtool.card_records.RECORDS_DIR / code / f"{sc.by_name(card)}.json"
    record = json.loads(path.read_text())
    if record.pop("ir", None) is not None:
        path.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n")
failed = []
for code, card, what in rows:
    print(f"=== {code} {card}", flush=True)
    rc = cardtool.main(["write", code, card, str(DRAFTS / f"{stem(code, card)}.py"),
                        "--clauses", str(DRAFTS / f"{stem(code, card)}.clauses.json"),
                        "--author", "claude-ontology-w3", "--notes", NOTE.format(what=what)])
    if rc:
        failed.append((code, card))
print("FAILED:", failed)
