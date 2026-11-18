"""The gate's surviving mutants (and two for the gate fixes) against the round's copy tests, on a
scratch copy of the worktree (each mutant applied, the tests run, the file restored). Read-only on
the worktree.

    mutants.py <scratch copy root> <python>
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

T = Path(sys.argv[1])
PY = sys.argv[2]
E = "MTG_bot/core/executor/"
MUTS = [
    ("lki-off", E + "copies.py",
     "if lki is not None and lki.identity is not None and (state is None or (on_battlefield and not here)):",
     "if False:"),
    ("this-creature-resolved-now", E + "copies.py",
     "_filter_is_self_referential(\n        sel.filter\n    ):\n        return [ctx.source]",
     "_filter_is_self_referential(\n        sel.filter\n    ) and False:\n        return [ctx.source]"),
    ("later-cast-copied", E + "copies.py", "f.handle == handle and f.declared_clock <= event.clock]",
     "f.handle == handle]"),
    ("kept-moved-target-kept", E + "copies.py", "if (i, j) not in gone))", "))"),
    ("copy-clock-not-moved", E + "copies.py",
     "        copy.declared_clock = executor.journal.clock\n", "        pass\n"),
    ("become-copy-token-mark-copied", E + "layers.py",
     "identity = replace(values.identity, is_token=base.identity.is_token)",
     "identity = values.identity"),
    ("copy-record-by-oracle-id", E + "verbs.py", "register_token(handle, record, by_oracle_id=False)",
     "register_token(handle, record, by_oracle_id=True)"),
    ("self-new-target", E + "copies.py", "(copy.handle, olds[i][j])", "(olds[i][j],)"),
    ("left-not-recorded-on-remove", E + "stack.py",
     "        self.frames.remove(frame)\n        self.left.append(frame)", "        self.frames.remove(frame)"),
    ("no-swap-lookahead", E + "copies.py", "if completes({**chosen, place: h}, places[k + 1:])]",
     "if legal({**{p: olds[p[0]][p[1]] for p in places}, **chosen, place: h})]"),
    ("copy-chooses-nothing-off", E + "layers.py",
     "choices.update({(handle, q): NOTHING_CHOSEN for q in _chosen_qualities(values.record)})", "pass"),
    ("own-choices-not-restored", E + "layers.py",
     "choices.update({(handle, q): v for q, v in base.choices})", "pass"),
]
TESTS = ["MTG_bot/core/test_executor_copies.py", "MTG_bot/core/test_ability_tree_copies.py"]
for name, rel, old, new in MUTS:
    path = T / rel
    text = path.read_text()
    if text.count(old) != 1:
        print(f"{name}: NOT APPLIED ({text.count(old)} matches)")
        continue
    path.write_text(text.replace(old, new))
    try:
        out = subprocess.run([PY, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", "-x",
                              *TESTS], cwd=T, capture_output=True, text=True, timeout=900).stdout
    finally:
        path.write_text(text)
    last = out.strip().splitlines()[-1] if out.strip() else "no output"
    print(f"{name}: {'KILLED' if 'failed' in last else 'SURVIVED'} | {last}")
