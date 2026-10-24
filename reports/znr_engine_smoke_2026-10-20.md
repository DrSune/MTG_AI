# ZNR engine smoke fuzz — 2026-10-20

- games completed: **40** / 40 (workers=4, wall 6.5s, cap 45.0s/game)
- turn cap 150, deck-pairs seed 201019
- crashed: **0** (crash rate **0.0%)
- distinct signatures: **0**
- exploration depth: median 51.0 acts, 30.5 turns per game

## BackFace reach probe

- verdict: **PASS** over 6 games (3863 intercepted walk calls, 0 correctly skipped)
- walk violations (face subtree descended by an engine consumer): 0
- registry hits (face object registered on executor/binder): 0
- battlefield permanents legitimately CARRYING a BackFace node: 14

## Signatures

ZERO crashes. Honest coverage note: random walks only reach legality-adjacent states — this is a robustness smoke, not a state-space proof.
