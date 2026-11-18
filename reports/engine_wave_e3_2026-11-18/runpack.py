"""Run packs on one checkout, as the suite's mapped lane does (unverified records applied).

    runpack.py <checkout> <pack.json>...
"""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
for p in (ROOT, ROOT / "tools"):
    sys.path.insert(0, str(p))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from run_scenarios import run_pack  # noqa: E402

from MTG_bot.core.executor.games import compile_supply  # noqa: E402

supplies = {}
for name in sys.argv[2:]:
    path = Path(name)
    code = json.loads(path.read_text()).get("set", "M21")
    if code not in supplies:
        supplies[code] = compile_supply("all", code, require_verified=False)
    fails = run_pack(path, supplies[code])
    print(("FAIL " if fails else "PASS ") + path.name)
    for line in fails:
        print("     " + line)
