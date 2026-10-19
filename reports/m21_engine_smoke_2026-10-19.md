# M21 engine smoke fuzz — 2026-10-19

- games completed: **500** / 500 (workers=4, wall 92.2s, cap 45.0s/game)
- turn cap 150, deck-pairs seed 201019
- crashed: **7** (crash rate **1.4%)
- distinct signatures: **3**
- exploration depth: median 72.0 acts, 34.0 turns per game

## BackFace reach probe

- verdict: **PASS** over 6 games (13713 intercepted walk calls, 0 correctly skipped)
- walk violations (face subtree descended by an engine consumer): 0
- registry hits (face object registered on executor/binder): 0
- battlefield permanents legitimately CARRYING a BackFace node: 0

## Signatures

### `AssertionError@quantity.py:880 in _eval_atom` — 5 hit(s), seeds [27, 95, 239, 274, 412]
- message: ``
- step: turn 14, 27 acts completed, attempted: `act:Tempered Veteran#0`
- stack: []
- recent acts: ['act:Mountain(#0)', 'act:Forest(#0)', 'act:Plains(#0)']
- **repro**: `python tools/eval/znr_engine_smoke.py --repro 27 --set M21 --deck-pairs-seed 201019 --turn-cap 150`

### `NotImplementedError@quantity.py:373 in resolve` — 1 hit(s), seeds [384]
- message: `executor: QThisTurn(NONCOMBAT_DAMAGE) not implemented (12b turn ledger)`
- step: turn 51, 111 acts completed, attempted: `cast:Fungal Rebirth`
- stack: []
- recent acts: ['act:Rugged Highlands(#2)', 'act:Mountain(#0)', 'cast:Fungal Rebirth(1t)']
- **repro**: `python tools/eval/znr_engine_smoke.py --repro 384 --set M21 --deck-pairs-seed 201019 --turn-cap 150`

### `ValueError@quantity.py:417 in _prop_value` — 1 hit(s), seeds [490]
- message: `executor: POWER undefined on handle card:61`
- step: turn 45, 79 acts completed, attempted: `cast:Carrion Grub`
- stack: []
- recent acts: ['act:Treasure(#0)', 'act:Mountain(#0)', 'act:Temple of Epiphany(#2)']
- **repro**: `python tools/eval/znr_engine_smoke.py --repro 490 --set M21 --deck-pairs-seed 201019 --turn-cap 150`
