# ZNR engine smoke fuzz — 2026-10-19

- games completed: **60** / 60 (workers=4, wall 9.3s, cap 45.0s/game)
- turn cap 150, deck-pairs seed 201019
- crashed: **1** (crash rate **1.7%)
- distinct signatures: **1**
- exploration depth: median 56.0 acts, 31.0 turns per game

## BackFace reach probe

- verdict: **PASS** over 6 games (3228 intercepted walk calls, 0 correctly skipped)
- walk violations (face subtree descended by an engine consumer): 0
- registry hits (face object registered on executor/binder): 0
- battlefield permanents legitimately CARRYING a BackFace node: 12

## Signatures

### `NotImplementedError@quantity.py:1585 in _eval_atom` — 1 hit(s), seeds [10]
- message: `executor: filter pred HAS_KICKER not implemented (12c query surface)`
- step: turn 31, 61 acts completed, attempted: `cast:Murasa Sproutling`
- stack: []
- recent acts: ['cast:Glacial Grasp(0t)', 'cast:Gnarlid Colony(0t)', 'act:Branchloft Pathway // Boulderloft Pathway(#0)']
- **repro**: `python tools/eval/znr_engine_smoke.py --repro 10 --deck-pairs-seed 201019 --turn-cap 150`
