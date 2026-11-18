"""Run pytest with some of this checkout's files as they were at a commit, then put them back.

    at_commit.py <commit> <file>[,<file>...] <pytest args...>

The files are copied aside first and written back in a ``finally``, so the checkout is left as it
was whatever pytest does. Gate round W3 used it to show that the fresh review's fix tests fail at
the round's first commit: ``at_commit.py 62cd34d8 MTG_bot/core/executor/binding.py,
MTG_bot/core/executor/verbs.py,MTG_bot/core/ability_tree.py MTG_bot/core/test_executor_w3.py
MTG_bot/core/test_ability_tree_w3.py -q`` (``review_fixes_at_62cd34d8.txt``).
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

commit, files, *args = sys.argv[1:]
saved = {}
with tempfile.TemporaryDirectory() as aside:
    try:
        for f in files.split(","):
            dst = Path(aside) / f.replace("/", "__")
            shutil.copy2(ROOT / f, dst)
            saved[f] = dst
            old = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{f}"], check=True,
                                 capture_output=True).stdout
            (ROOT / f).write_bytes(old)
        subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "pytest", *args], cwd=ROOT, check=False)
    finally:
        for f, dst in saved.items():
            shutil.copy2(dst, ROOT / f)
print("restored", list(saved))
