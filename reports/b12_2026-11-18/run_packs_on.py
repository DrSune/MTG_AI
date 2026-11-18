"""Run the given packs on one checkout (its engine, compiler and records): run_packs_on.py <checkout>
<pack...>. A pack under mapped/ plays on the unverified records, as the suite plays it."""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from MTG_bot.core.executor.games import compile_supply, get_supply  # noqa: E402
from tools.run_scenarios import run_pack  # noqa: E402

for arg in sys.argv[2:]:
    path = Path(arg)
    code = json.loads(path.read_text()).get("set", "M21")
    supply = compile_supply("all", code, require_verified=False) if "mapped" in path.parts \
        else get_supply("all", code)
    try:
        failures = run_pack(path, supply)
    except Exception as exc:  # noqa: BLE001 - a raise is a failure on this checkout
        failures = [f"raised {type(exc).__name__}: {str(exc)[:160]}"]
    print("PASS" if not failures else "FAIL", path.name, "|", (failures[0][:200] if failures else ""))
