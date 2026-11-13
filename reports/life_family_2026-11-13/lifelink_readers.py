"""For the replayed games whose play differs (lifelink_replay.py journals, before and after the
fix): the rows caused by the cards that read life gain, from the first differing journal row to
the next untap step, on each side. Output in lifelink_blast_radius.txt, section 5.

    lifelink_readers.py <before.journals.json> <after.journals.json> SET:GAME ...
"""
import json
import sys
from pathlib import Path

before = json.loads(Path(sys.argv[1]).read_text())
after = json.loads(Path(sys.argv[2]).read_text())
#: the verified cards of M21, M20 and FDN that read a life gain (a trigger on it)
GAIN_READERS = ("Ajani's Pridemate", "Marauding Blight-Priest", "Vito, Thorn of the Dusk Rose",
                "Epicure of Blood", "Bloodthirsty Aerialist", "Light of Promise")
for spec in sys.argv[3:]:
    code, game = spec.split(":")
    rows_b, rows_a = before[code][game]["rows"], after[code][game]["rows"]
    first = next(k for k, (r, s) in enumerate(zip(rows_b, rows_a)) if r != s)
    print(f"== {code} game {game}, first differing row {first}")
    for label, rows in (("before", rows_b), ("after", rows_a)):
        shown = 0
        for row in rows[first:]:
            if row[1] == "TURN_PHASE" and "UNTAP" in row[5]:
                break
            if any(name in row[3] for name in GAIN_READERS) and row[1] != "DAMAGE":
                print(f"   {label} {row[:5]} {row[5][:60]}")
                shown += 1
        print(f"   {label}: {shown} rows caused by a life-gain reader before the next untap")
