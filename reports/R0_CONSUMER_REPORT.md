# R0 Consumer Inventory — `Selector.zone`+`zones` → one `zones` set field

Full machine-readable inventory: `/tmp/opencode/r0_consumer_inventory.json` (395 classified prod sites + 172 test sites; **UNCLASSIFIED list empty**). Method: AST scans (`r0_scan*.py`, `r0_type_tests.py`) distinguishing Selector consumers from two decoys, plus corpus census (`r0_corpus.py`) recompiling M21+ZNR via `_compile_pool_tolerant` — not the signature registry.

## Totals (measured)
- Prod `Selector(` constructions: **263** (239 positional slot-4, 24 `zone=`, 6 also `zones=`); zone is required — no zone-less construction exists.
- Test constructions: **309**; selector-typed test asserts: **163** in 16 files (151 `.zone`, 12 `.zones`) → re-pin; 9 `FAtom.zone` decoy asserts untouched; 106 world-side test calls out of scope.
- Corpus: **549 selectors** (M21 388 / ZNR 161); **twins (non-empty `zones`): 10, on 10 M21 cards, 0 ZNR**; neutral `ANY/ANY`+`zones=()` C2 class: 48.
- **LOUD — spec is wrong**: "~64 `zone=` constructors" understates migration surface ~8× (239 positional prod + 293 positional test sites).

## KEYED lanes (need logic rewrites, not renames)
| Lane | Site | Keys on | Rewrite |
|---|---|---|---|
| L1 | selectors.py:451-457,473 | ONE_OF/REST ∧ LIBRARY∧TOP | filter `sel.zones` for LIBRARY/TOP, controller from match (pop 15) |
| L2 | selectors.py:614 | `zone.kind is PLAYER` re-point | ∃-PLAYER (pop 10) |
| L3 | selectors.py:833-837 | PLAYER ∧ `not zones` | **SINGLETON** `len(zones)==1 and zones[0].kind is PLAYER` — ∃ resurrects r21a Magmutt/Leafkin bug (pop 8; twins at risk) |
| L4 | selectors.py:877-886 | GRAVEYARD∧TARGET_PLAYER | zone satisfying both clauses (pop 1, Tormod's Crypt) |
| L5 | verbs.py:246-250 | draw-guard LIBRARY | **SINGLETON** LIBRARY (guard, corpus pop 0) |
| **L6 NEW** | **legality.py:947-951** | `CostDiscard.target.zone.kind is HAND` activation-window gate (Waker of Waves) | ∃-HAND — **not among the spec's known four; LOUD** |

Also KEYED-LOSS: **compiler.py:1050** rebuilds Selector positionally and **silently drops `value.zones`** — must edit or twins lose data.

## Serialization / order
`_OMIT_IF_EMPTY` omits `zones`; every Selector dict loses `zone` gains `zones` → **219/305 M21 goldens re-bake**; stale goldens fail `from_dict` loudly (good). Ask vocabulary carries Handle strings only — no zone-name order change; enumeration-order risks: `selectors.py:559` ALL-mode raw order (corpus pop 0), `verbs.py:265` first-n slice. repr-keyed designation identity (stack/binding/query) is fold-safe.

## Decoy warning
`FAtom.zone` is a different Zone field (quantity.py ZONE_COUNT_GE etc.) — a blanket `.zone→.zones` sweep breaks it.
