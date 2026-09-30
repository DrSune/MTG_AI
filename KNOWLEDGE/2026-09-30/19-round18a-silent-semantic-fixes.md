# 19 — Round 18a: silent-semantic fixes (8 wave-1b packs repatriated; first engine move since 16e)

Mission: fix the SILENT-semantic classes of the wave-1b ledger (doc 18) —
printed promises LOST with no ask and no raise — and repatriate the affected
suspect packs. Loud gaps (flagged verbs, Zone(ANY), TARGET-designation, …)
stay 18b's; suspects untouched.

## The six classes (root cause verified against compiled IR, not ledger guesses)

1. **if-do free rider (CR 611.1)** — "you may X. If you do, Y" ran Y even on
   `skip` (Crypt Lurker drew a card after a sacrificed NOTHING). Verified:
   the compiler's R11-1 default merge (`_append_mandatory_to_seq`) attaches
   the continuation as a plain sibling — NO IR encoding of the gate existed
   (the mission's "OptionalEffect + guard pred?" hypothesis: the pred did
   not exist). Fix: new **`FAtomPred.MAY_DONE`** (handle-free, no slots,
   precedent TARGETS_SOURCE) + compiler **`_merge_if_do_continuation`**: a
   continuation starting "If you do[, so]" whose seam ENDS in an
   OptionalEffect merges as `Conditional(MAY_DONE, tail)` ("If you do, you
   may X" keeps its inner optional INSIDE the gate); a mandatory seam
   (Archfiend's Vessel's condition-gated exile, Mazemind Tome) keeps the
   plain append. The executor answers MAY_DONE by CONSUMING the 14b
   channel's logged outcome (`decision_stream.ask_log`, newest
   `may:<source>` answer == 'fire') — it never re-asks; no record = loud
   raise (FLIP_WON convention).
2. **C15 choice-theft by `optional_offer`** — the exact-count gate compared
   candidates to the WANTED count, so a two-wanted search with one legal
   hit narrowed to `("skip",)` while the runtime CHOOSE would honestly take
   one (Alpine Houndmaster "a card named X and/or a card named Y"). Gate
   now compares to ZERO only (CR 117.3 removes only actions with NO
   candidates; the C17 clamp is the runtime's own resolution rule).
3. **search-fed tail gated against the pre-execution world** — the 13a
   re-search idiom (Fabled-Passage family: Fabled Passage/Chandra's
   Firemaw/Garruk's Warsteed/Teferi's Wavecaster) ends the may-inner in a
   MOVE_ZONE whose population the SEARCH PRODUCES mid-effect (result
   register, 14e); pre-execution it is legitimately empty and ERASED the
   branch (B-9 was this, not only a cast-site gap). The gate now skips
   MOVE_ZONE-after-SEARCH (walk order) and `referent in
   ("event","result")` selectors; the SEARCH selector's own population
   still gates (the honest no-hit world stays skip-only). Runtime half:
   `_v_move_zone`'s top-n draw idiom requires a UNIVERSAL filter and no
   referent — a filtered library→hand tail resolves through its filter
   (firemaw stopped hoovering an unrelated library-top card into hand).
4. **Garruk's Uprising "silent-false"** — the ledger guessed an
   unevaluable-pred silent False; VERIFIED otherwise: `CONTROLLER_COUNT_GE`
   is live since 14d and answered faithfully to a WRONG compile — the b2b
   builder passed the power THRESHOLD as the required COUNT (needed FOUR
   4-power creatures where the print says "a creature"). Fixed to count 1
   (Historian Teferi's count-1 precedent; CR 608.2a follows the printed
   text).
5. **scry-bottom window no-op (CR 701.1)** — `_v_scry` regrouped only the
   viewed window, so a scry-1 "bottom" was an exact no-op. Bottoms now go
   under the WHOLE library (`sorted(bottoms) + unviewed + sorted(tops)`),
   the unviewed remainder order-preserving.
6. **Turret Ogre unfireable trigger (CR 603.4)** — the intervening "if" was
   a bare population filter the trigger gate judged against a SINGLE
   handle, `ctx.source` (the OGRE ITSELF): `FNot(IS_SOURCE)` is
   self-contradictory there → the printed branch could never fire in ANY
   world (wave-1b B-3). Condition now the set-level idiom (b2b
   Uprising/Historian): `CONTROLLER_COUNT_GE` count 1 with the type/power/
   CONTROLLER_IS filter and `FNot(IS_SOURCE)` INSIDE (per-candidate —
   "another" means exactly that). Sanctioned golden mover; audited below.

## Incidental (same mechanism, honest recount)

- **teferis_wavecaster** flipped GREEN from the class-3 gate skip (its
  'fire' resolves: SEARCH → result register → referent MOVE). It is the
  same silent-collapse class, so it was repatriated too: **8 packs moved,
  not 7** (mission note expected 25 suspects; honest: 31−8 = 23).
- **alpine_houndmaster.json rebuilt**: the wave-1b harness constructor's
  opening `begin_turn` draw ate the pack's premise (the Watchdog was the
  ONLY library card → drawn before any step — the "move commits before the
  may-ask" reading was THIS setup mutation, not an engine pre-ask commit;
  the engine never mutated before the ask). Pack now adds a decoy library
  card, answers the previously-STOLEN `'fire'`, and pins the post-shuffle
  library lane exactly (seed 7, deterministic).
- The mission's class-2 "pre-ask mutation path" hypothesis was tested and
  REFUTED at trace level: with `decisions=['skip']` the ask arrived FIRST;
  the theft was purely the narrowed vocabulary.

## Golden audit (snapshot /tmp/golden_pre_r18a → regenerate → set-equal)

9 lines moved, keys ALL `{abilities}`, diff == attributed inventory EXACTLY:
Turret Ogre (6), Garruk's Uprising (4), Crypt Lurker + Ghostly Pilferer +
Jeskai Elder + Dire Fleet Warmonger + Liliana's Devotee + Sanctum of Calm
Waters + Niambi (class-1 seam). **Deviation (reported, not hidden):** the
mission sanctioned turret as the ONLY golden mover, assuming class 1 was
executor-fixable; the verified IR (six dump-checked cards) has NO guard to
consume — the honest CR 611.1 gate is the merge, and it applies to every
may-seam if-do tail in the corpus. Inventory was computed and
set-equality-verified BEFORE regeneration (unambiguous → proceed; the
STOP-REPORT condition was "ambiguous inventory", not "any non-turret move").
PC-4 = 0 diffs post-refresh. The corpus free riders this retired: Jeskai
Elder discarded after a skipped draw; Warmonger's +2/+2-without-sacrifice
(a FROZEN blocker test had pinned exactly that — AMENDED); Devotee minted
Zombies for free; Pilferer drew for free.

## Numbers (all re-measured 2026-10-01)

| metric | value | command |
| --- | --- | --- |
| scenario packs | **63/63** (55 + 8 repatriated) | `.venv/bin/python tools/run_scenarios.py` |
| suspects | **0/23 fail-only** (31 − 8; all loud documented) | `… tools/run_scenarios.py --dir tools/audit/suspects` |
| core suite | **2096 passed + 4 subtests** (2081 + 15 new `test_executor_r18a.py`; **4 AMENDED pins**: scry-top-first, turret condition, uprising count, trample free-rider) | `.venv/bin/python -m pytest MTG_bot/core -q` |
| PC-1 / PC-2 / PC-3 / PC-4 | **301/305 · 634/639 · 0 · 0 diffs (305 files)** — EXACT vs baseline | `.venv/bin/python tools/measure_grammar.py --set M21` |
| engine gate | **297/305, V2 45 verbs — UNCHANGED** (semantics, not dispatch) | `… --with-engine-flags` |
| goldens | 9 moved, diff == inventory set-equal, keys {abilities}; post-refresh 0 | golden.py verify/write + snapshot diff |
| trace catalog | repin 6138 → **6174** entries; post-repin **0/10 diverge** (pre-repin 5/10 diverged, first @ entry 290 — gates now fire/refuse honestly) | `tools/traces/catalog.py repin && … compare` |
| determinism | scenarios reruns byte-identical; replay pin 1 passed | `tools/run_scenarios.py` ×2 / `pytest tools/test_replay.py` |
| pyright / ruff | **0** on every touched file; ruff **Δ0** (ability_tree 57=57, quantity 1=1 legacy) | `pyright <scope>` / `ruff check` per file |

## Known residuals (recorded, NOT silently absorbed)

- "If you search your library this way, shuffle." merges (search-shuffle
  tail) fire the shuffle on ANY fire — searching from graveyard only also
  shuffles (printed text wants the conditional); firemaw/warsteed packs
  don't assert the lane, honest note for a future fidelity row.
- The b2b #31 "Ornery" builder still passes the threshold as the count
  (same shape class 4 had fixed): no corpus card hits its regex today —
  flagged for the next template-fidelity pass.
- The offer-gate search-tail skip assumes walk-order (SEARCH precedes its
  tail in the same effect) — true for every re-search-idiom emit; a
  hand-authored out-of-order tree would skip a gate that should run.

Files touched: `MTG_bot/core/ability_tree.py`, `executor/quantity.py`,
`executor/verbs.py`, `executor/query.py`, `compiler/compiler.py`,
`compiler/templates_b2a.py` (turret), `compiler/templates_b2b.py`
(uprising), 4 amended test files, new `MTG_bot/core/test_executor_r18a.py`,
8 pack moves (suspects→scenarios), 9×2 golden files, catalog.json.
