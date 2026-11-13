"""Mutation check of the round-10 engine pieces: each mutant undoes one piece in the worktree, runs
the round-10 test module, records which tests fail, and restores the file. Usage:
    mutants.py <worktree> <out.txt>"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
OUT = Path(sys.argv[2])
PY = "/home/sune/Desktop/MTG_AI/.venv/bin/python"
MUTANTS = [
    ("no 400.7 refresh of 'they' at resolution", "MTG_bot/core/executor/binding.py",
     "        gathered = obj.ctx.binding_handles(\"gathered\")\n        if gathered is not None:",
     "        gathered = obj.ctx.binding_handles(\"gathered\")\n        if False:"),
    ("the event referent sliced to one object again", "MTG_bot/core/executor/selectors.py",
     "    if sel.referent == \"event\":\n        # The triggering event's object",
     "    if False:\n        # The triggering event's object"),
    ("'that many' reads the event register (still-there objects)", "MTG_bot/core/executor/quantity.py",
     "            handles = ctx.binding_handles(\"gathered\")",
     "            handles = ctx.binding_handles(\"event\")"),
    ("a draw of two is one batch", "MTG_bot/core/executor/events.py",
     "            if drawn:\n                batch = self._clock + 1",
     "            if False:\n                batch = self._clock + 1"),
    ("no dedup per event (each row queues)", "MTG_bot/core/executor/binding.py",
     "            if key in self._gathered_queued:\n                return",
     "            if False:\n                return"),
    ("gathered set = the first row's object only", "MTG_bot/core/executor/binding.py",
     "                for e in self._occurrences(event)\n",
     "                for e in (event,)\n"),
    # the fresh-eyes review's fixes (after de082e81)
    ("'that many' looks up an object first (the review's FATAL)", "MTG_bot/core/executor/quantity.py",
     "        if prop.field in _REGISTER_FIELDS:\n            return",
     "        if prop.field in _REGISTER_FIELDS:\n            _referent_handle(prop.referent, ctx)\n"
     "            return"),
    ("no net for a singular read of several gathered objects", "MTG_bot/core/executor/quantity.py",
     "        if referent == \"event\" and len(ctx.binding_handles(\"event\") or ()) > 1:",
     "        if False:"),
    ("a bare Conditional judged on the source under a gathered event",
     "MTG_bot/core/executor/__init__.py",
     "        if len(event) > 1:",
     "        if False:"),
]
lines = []
for label, rel, old, new in MUTANTS:
    path = ROOT / rel
    src = path.read_text()
    assert src.count(old) == 1, (label, src.count(old))
    path.write_text(src.replace(old, new))
    try:
        run = subprocess.run(
            [PY, "-m", "pytest", "MTG_bot/core/test_executor_one_or_more.py", "-q", "--tb=no",
             "-p", "no:cacheprovider", "-rf"],
            cwd=ROOT, capture_output=True, text=True,
            env={"CUDA_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": "2", "PATH": "/usr/bin:/bin"})
    finally:
        path.write_text(src)
    failed = sorted({ln.split("::", 1)[1].split(" ")[0] for ln in run.stdout.splitlines()
                     if ln.startswith("FAILED")})
    lines.append(f"mutant: {label} ({rel})\n  {run.stdout.strip().splitlines()[-1]}\n"
                 + "".join(f"  killed by {t}\n" for t in failed))
OUT.write_text("\n".join(lines))
print(OUT.read_text())
