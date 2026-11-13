"""Run test files of a branch against another checkout (a `git archive` of the base):
run_on_base.py <branch> <checkout> <test file>... Each file is copied to the same relative path in the
checkout, and pytest runs there (its rootdir and imports are the checkout's). Prints the outcomes."""
import shutil
import subprocess
import sys
from pathlib import Path

src_root, base = Path(sys.argv[1]), Path(sys.argv[2])
rels = sys.argv[3:]
for rel in rels:
    shutil.copy(src_root / rel, base / rel)
out = subprocess.run([sys.executable, "-m", "pytest", *rels, "-q", "-rA", "-p", "no:cacheprovider",
                      "--no-header", "--tb=line"],
                     cwd=base, capture_output=True, text=True, check=False)
lines = out.stdout.splitlines()
print("\n".join(line for line in lines if line.startswith(("PASSED", "FAILED", "ERROR")) or "passed" in line or "failed" in line))
