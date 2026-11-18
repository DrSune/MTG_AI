"""Which copy sentences of the 19 sets stay unparsed after the copy round (compiler trees, no
records; DESIGN_ATOM_ONTOLOGY §18, BACKLOG "The copy lane still blocked").

    unparsed_copy.py <checkout>
"""
import re
import sys
from pathlib import Path

REPO = Path(sys.argv[1])
sys.path[:0] = [str(REPO), str(REPO / "tools" / "cards")]
import corpus  # noqa: E402
from MTG_bot.core.compiler.compiler import compile_pool  # noqa: E402
from MTG_bot.core.compiler.coverage import build_full_registry  # noqa: E402
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402
from MTG_bot.core.errors import StateCorruptionError  # noqa: E402

registry = build_full_registry()
COPY = re.compile(r"\bcop(y|ies)\b", re.I)
for code in corpus.SETS:
    raw = ingest_pool(REPO / "MTG_bot" / "data" / f"{code}.json")
    for oid, rc in raw.items():
        text = rc.identity.oracle_text or ""
        if rc.is_token or not COPY.search(re.sub(r"\([^)]*\)", "", text)):
            continue
        try:
            res = compile_pool({oid: rc}, registry, require_verified=False).results[oid]
        except (StateCorruptionError, ValueError) as exc:
            print(f"{code} {rc.identity.name}: REFUSED {str(exc)[:90]}")
            continue
        left = [s for s in (*res.unparsed, *res.back_face_unparsed) if COPY.search(str(s))]
        if left:
            print(f"{code} {rc.identity.name}: {len(left)} copy sentence(s) unparsed: {str(left[0])[:110]}")
