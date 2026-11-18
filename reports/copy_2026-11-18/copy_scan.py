"""Regex scan of the 19 sets for copy wordings (read-only): every sentence that says "copy"."""
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(sys.argv[1])
sys.path[:0] = [str(REPO), str(REPO / "tools" / "cards")]
import corpus  # noqa: E402
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402

SENT = re.compile(r"(?<=[.!])\s+(?=[A-Z•\"])")
hits = defaultdict(list)
cards = defaultdict(set)
for code in corpus.SETS:
    raw = ingest_pool(REPO / "MTG_bot" / "data" / f"{code}.json")
    for oid, rc in raw.items():
        text = rc.identity.oracle_text or ""
        name = rc.identity.name
        for line in text.split("\n"):
            line = re.sub(r"\([^)]*\)", "", line).strip()
            if not re.search(r"\bcop(y|ies)\b", line, re.I):
                continue
            for s in SENT.split(line):
                if re.search(r"\bcop(y|ies)\b", s, re.I):
                    norm = s.replace(name, "~")
                    hits[norm].append(f"{code} {name}")
                    cards[name].add(code)
for s, where in sorted(hits.items(), key=lambda kv: (-len(kv[1]), kv[0])):
    print(f"{len(where):3d}  {s}")
    print("       " + "; ".join(sorted(set(where)))[:300])
print(len(cards), "cards,", sum(len(v) for v in cards.values()), "printings")
