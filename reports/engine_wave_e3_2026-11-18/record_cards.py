"""Record the verified pools' dealt cards (oracle ids) per set, for the G1 coverage test.

    record_cards.py <checkout> <out.json>
"""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from MTG_bot.core.executor.games import get_supply  # noqa: E402

out = {code: list(get_supply("verified", code).deckable) for code in ("M21", "M20", "FDN")}
text = "{\n" + ",\n".join(f' "{code}": [\n' + ",\n".join(f'  "{oid}"' for oid in ids) + "\n ]"
                          for code, ids in out.items()) + "\n}\n"
Path(sys.argv[2]).write_text(text)
print({code: len(ids) for code, ids in out.items()})
