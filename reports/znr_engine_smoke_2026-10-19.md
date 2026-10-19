# ZNR engine smoke fuzz — 2026-10-19

- games completed: **1000** / 1000 (workers=4, wall 160.0s, cap 45.0s/game)
- turn cap 400, deck-pairs seed 201019
- crashed: **0** (crash rate **0.0%)
- distinct signatures: **0**
- exploration depth: median 62.0 acts, 33.0 turns per game

## BackFace reach probe

- verdict: **PASS** over 6 games (3869 intercepted walk calls, 0 correctly skipped)
- walk violations (face subtree descended by an engine consumer): 0
- registry hits (face object registered on executor/binder): 0
- battlefield permanents legitimately CARRYING a BackFace node: 14

## Signatures

ZERO crashes. Honest coverage note: random walks only reach legality-adjacent states — this is a robustness smoke, not a state-space proof.
