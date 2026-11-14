"""Dry run of `cardtool verify --reprint-of` over every reprint of a verified card in the 16 other
sets; records are written to a scratch directory, never to MTG_bot/data/cards."""
import contextlib
import io
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path.cwd()
sys.path[:0] = [str(REPO), str(REPO / "tools" / "cards")]
import cardtool  # noqa: E402
import corpus  # noqa: E402

from MTG_bot.core.compiler import card_records  # noqa: E402

scratch = Path(sys.argv[1])
scratch.mkdir(parents=True, exist_ok=True)
REAL = card_records.RECORDS_DIR
HOME = ("M21", "M20", "FDN")
res = Counter()
rows = []
for code in [s for s in corpus.SETS if s not in HOME]:
    sc = corpus.compile_set(code)
    oids = {o for o, r in sc.raw.items() if not r.is_token and not r.is_emblem}
    card_records.RECORDS_DIR = REAL
    homes = cardtool.reprint_sources(sc, oids)
    for oid, home in sorted(homes.items()):
        name = sc.raw[oid].identity.name
        card_records.RECORDS_DIR = scratch
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            try:
                rc = cardtool.main(["verify", code, name, "--reprint-of", home, "--reviewer", "dry-run"])
            except SystemExit as exc:
                rc = f"exit {exc.code}"
            except Exception as exc:  # noqa: BLE001
                rc = f"crash {type(exc).__name__}: {exc}"[:120]
        out = buf.getvalue()
        why = [ln.strip() for ln in out.splitlines() if ln.strip().startswith(("G0", "G1", "G2", "G3", "G4", "REFUSED"))]
        res["verified" if rc == 0 else "not verified"] += 1
        for w in why:
            res[w.split(":")[0] + ": " + w.split(":")[1][:60].strip()] += 1
        rows.append((code, name, home, rc, why[:3]))
        print(code, name, home, rc, why[:2], flush=True)
card_records.RECORDS_DIR = REAL
print(dict(res))
json.dump(rows, open(scratch / "rows.json", "w"), indent=1)
