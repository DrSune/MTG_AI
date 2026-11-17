"""Run packs against one checkout's engine: onepack.py <checkout> <pack.json>..."""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
import run_scenarios as rs  # noqa: E402
from MTG_bot.core.executor.games import get_supply  # noqa: E402

for p in sys.argv[2:]:
    path = Path(p)
    code = json.loads(path.read_text()).get("set", "M21")
    fails = rs.run_pack(path, get_supply("all", code))
    print("FAIL" if fails else "PASS", path.name, *fails, sep="\n  ")
