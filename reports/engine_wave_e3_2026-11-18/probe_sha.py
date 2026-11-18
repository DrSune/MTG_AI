"""The G1 probe trace sha of named cards on one checkout, against a verdict's probe_sha (what
`cardtool verify` checks first), read-only.

    probe_sha.py <checkout> <SET> <card name> <verdict.json>
"""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
for p in (ROOT, ROOT / "tools" / "cards", ROOT / "tools"):
    sys.path.insert(0, str(p))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from probe import Probe  # noqa: E402

from MTG_bot.core.executor.games import compile_supply  # noqa: E402

code, name, verdict = sys.argv[2], sys.argv[3], json.loads(Path(sys.argv[4]).read_text())
sup = compile_supply("all", code, require_verified=False)
oid = next(o for o, m in sup.metas.items() if m.name == name)
rep = Probe(sup, code, oid).report()
print(f"{name}: probe {rep.sha()[:16]}, verdict {verdict['probe_sha'][:16]}: "
      f"{'SAME' if rep.sha() == verdict['probe_sha'] else 'DIFFERENT'}; engine errors {len(rep.errors)}")
