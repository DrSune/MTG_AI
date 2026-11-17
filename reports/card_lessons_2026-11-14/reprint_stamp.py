"""The reprint wave (KNOWLEDGE/2026-11-14/207 §5.3): every printing, in any set, of a card another
set verified by its own review, with the same printed text and not yet verified here, stamped
through ``cardtool verify --reprint-of``. The candidates of every set are fixed before the first
stamp, so a reprint never becomes another's home.

    .venv/bin/python -I reports/card_lessons_2026-11-14/reprint_stamp.py REVIEWER
"""
import contextlib
import io
import sys
from collections import Counter
from pathlib import Path

REPO = Path.cwd()
sys.path[:0] = [str(REPO), str(REPO / "tools" / "cards")]
import cardtool
import corpus

reviewer = sys.argv[1]
todo = []
for code in corpus.SETS:
    sc = corpus.compile_set(code)
    open_ = {oid for oid, raw in sc.raw.items()
             if not raw.is_token and not raw.is_emblem and cardtool._state(sc, oid) != "verified"}
    todo += [(code, sc.raw[oid].identity.name, home) for oid, home in sorted(cardtool.reprint_sources(sc, open_).items())]
print(f"{len(todo)} candidates", flush=True)
res = Counter()
for code, name, home in todo:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cardtool.main(["verify", code, name, "--reprint-of", home, "--reviewer", reviewer])
    why = [ln.strip() for ln in buf.getvalue().splitlines() if ln.strip().startswith(("G0", "G1", "G2", "G3", "G4", "REFUSED"))]
    res[(home, code, "verified" if rc == 0 else "not verified")] += 1
    print(code, name, "from", home, "VERIFIED" if rc == 0 else "NOT VERIFIED: " + "; ".join(why[:3]), flush=True)
print(f"verified {sum(n for k, n in res.items() if k[2] == 'verified')} of {len(todo)}")
for key, n in sorted(res.items()):
    print(" ", *key, n)
