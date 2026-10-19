# ZNR engine smoke fuzz — 2026-10-19

- games completed: **2000** / 2000 (workers=4, wall 325.0s, cap 45.0s/game)
- turn cap 150, deck-pairs seed 201019
- crashed: **2** (crash rate **0.1%)
- distinct signatures: **2**
- exploration depth: median 60.0 acts, 32.0 turns per game

## BackFace reach probe

- verdict: **PASS** over 6 games (3228 intercepted walk calls, 0 correctly skipped)
- walk violations (face subtree descended by an engine consumer): 0
- registry hits (face object registered on executor/binder): 0
- battlefield permanents legitimately CARRYING a BackFace node: 12

## Signatures

### `RuntimeError@__init__.py:1721 in _declare_blockers` — 1 hit(s), seeds [1269]
- message: `executor: menace attacker card:11 was blocked by exactly one creature ['card:79'] (CR 702.113 — the ask narrowing should have prevented this)`
- step: turn 26, 50 acts completed, attempted: `act:Riverglide Pathway // Lavaglide Pathway#0`
- stack: []
- recent acts: ['act:Mountain(#0)', 'cast:Nahiri, Heir of the Ancients(0t)', 'act:Riverglide Pathway // Lavaglide Pathway(#0)']
- **repro**: `python tools/eval/znr_engine_smoke.py --repro 1269 --set ZNR --deck-pairs-seed 201019 --turn-cap 150`

### `ValueError@stack.py:1040 in cast_card` — 1 hit(s), seeds [1715]
- message: `executor: CAST Beyeen Veil // Beyeen Coast: no SpellAbility on the card`
- step: turn 21, 42 acts completed, attempted: `cast:Coveted Prize`
- stack: []
- recent acts: ['act:Swamp(#0)', 'act:Throne of Makindi(#0)', 'act:Crawling Barrens(#0)']
- **repro**: `python tools/eval/znr_engine_smoke.py --repro 1715 --set ZNR --deck-pairs-seed 201019 --turn-cap 150`
