"""Rebuild every surviving round's planted mutant from its key (set, oracle id, operator, path) on
today's tree and ask the lints whether they see it. Run from the worktree root."""
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path.cwd()
sys.path[:0] = [str(REPO), str(REPO / "tools" / "cards")]
import corpus  # noqa: E402
import gates  # noqa: E402
import lints  # noqa: E402

S = Path("/tmp/claude-1000/-home-sune/2e18468a-eed7-47b5-a69b-d15b1f5fd0e8/scratchpad")
keyfiles = []
for d in ("round_m20_verify/private/key", "round_m20_verify2/private/key", "round_fdn_verify1/private/key",
          "round_r3/private/key_m20", "round_r3/private/key_fdn"):
    keyfiles += [p for p in (S / d).glob("P*.json")]
for d in ("verify_keys", "verify_keys_1b", "verify_keys_1c", "verify_keys_1d", "verify_keys_1e"):
    keyfiles += list((S / d / "plants").glob("*.json"))
sets = {}
res = Counter()
rows = []
for kf in keyfiles:
    k = json.loads(kf.read_text())
    code, oid, op, where = k["set"], k["oracle_id"], k["planted"], k["where"]
    if code not in sets:
        sets[code] = corpus.compile_set(code)
    sc = sets[code]
    raw, result = sc.raw.get(oid), sc.results.get(oid)
    if raw is None or result is None:
        res["card gone"] += 1
        continue
    mutant = next((m for o, w, m in gates.mutants(result.card) if (o, w) == (op, where)), None)
    if mutant is None:
        res["mutant no longer exists"] += 1
        rows.append((code, raw.identity.name, op, "n/a"))
        continue
    found = lints.lint(raw, mutant)
    res["caught" if found else "missed"] += 1
    res[f"{op.split(' (')[0]}:{'caught' if found else 'missed'}"] += 1
    rows.append((code, raw.identity.name, op, found[0][:110] if found else "-"))
for r in sorted(rows):
    print(r)
print(dict(sorted(res.items())))
