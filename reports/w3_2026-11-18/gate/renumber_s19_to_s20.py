"""Renumber W3's references to its DESIGN_ATOM_ONTOLOGY section, §19 -> §20, after merging main
69f7f8a2 (round B12 keeps §19). A line is W3's when the branch's last commit (680ec521) has it and
neither the merge base (a6e90ba6) nor main (69f7f8a2) does; only those lines change, so B12's
"§19" (main's lines) and older ones (the base's: other documents' sections) stay.

    renumber.py            (dry run: prints what would change, and every line it cannot place)
    renumber.py --write
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/sune/Desktop/MTG_AI/.claude/worktrees/agent-a3637301ad1c4f789")
HEAD, BASE, MAIN = "680ec521", "a6e90ba6", "69f7f8a2"
write = "--write" in sys.argv


def lines_at(rev: str, rel: str) -> set[str]:
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{rel}"], capture_output=True, text=True)
    return set(r.stdout.split("\n")) if r.returncode == 0 else set()


files = subprocess.run(["git", "-C", str(ROOT), "grep", "-l", "§19"], capture_output=True, text=True).stdout.split()
changed = unplaced = 0
for rel in files:
    if rel.startswith("docs/DESIGN_ATOM_ONTOLOGY.md"):
        continue  # resolved by hand (resolve_design.py)
    p = ROOT / rel
    text = p.read_text()
    ours, base, main = lines_at(HEAD, rel), lines_at(BASE, rel), lines_at(MAIN, rel)
    out = []
    for line in text.split("\n"):
        if "§19" in line:
            if line in ours and line not in base and line not in main:
                new = line.replace("§19", "§20")
                print(f"W3   {rel}: {line.strip()[:110]}")
                out.append(new)
                changed += 1
                continue
            if line not in main and line not in base:
                print(f"???  {rel}: {line.strip()[:110]}")
                unplaced += 1
        out.append(line)
    if write:
        p.write_text("\n".join(out))
print(f"{changed} W3 lines renumbered, {unplaced} lines unplaced", "(written)" if write else "(dry run)")
