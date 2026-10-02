# 2026-10-02 — engine batch 24a: the LIFE quantity lane + harness token lane (2 suspects closed)

HEAD 868cb19 baseline. Mission: close the last two non-owner-blocked
suspects — `peer_into_the_abyss` (engine) and `treasure_token_activation`
(harness). Compiler + goldens FROZEN. Both closed and promoted; suspect
folder now holds only the two owner-blocked packs.

## 1. Verdicts

**peer_into_the_abyss — ENGINE lane landed; life-half remains a compiler
gap (promoted with documented deviation).** The frozen golden (M21
`21fa2442-…`) carries ONLY the DRAW `((QCount(LIBRARY,TARGET_PLAYER)+1)
DIV 2)` — the print's "loses half their life. Round up" has no LOSE_LIFE
atom (C3 STOP, file 05: no quantity could read a life TOTAL). Batch 24a
lands the roadmap's engine half (02-compiler-roadmap line 47):

* `QPropField.LIFE` (ability_tree.py, additive+byte-stable per the R3 law
  — no frozen golden contains it, PC-4 0 diffs re-verified). Validated as
  a PLAYER property: referent `"controller"` only, the exact twin
  convention of CARDS_IN_HAND/LIBRARY/GRAVEYARD; a mismatched referent
  raises at construction, never silently re-scopes.
* `quantity._prop_value` — direct order-free attribute read (the
  determinism contract the zone-count twins keep; PC-9 stable re-verified).
* `_v_lose_life` already resolves `amount` through `resolve`, so the atom
  is live end-to-end the moment the field exists: pinned at
  `test_executor_r24a.py` (10 pins — controller-scoped read, round-up
  half 20→10 / 13 loses 7 / 1 loses 1, executor end-to-end 20→10,
  referent-validation raises).
* **Compiler half NOT landed (frozen):** the promoted pack's
  `expect.life {0:20,1:20}` RECORDS the print still dropping the clause —
  the pack is the witness that the draw-half (round-up, discriminated by
  padding p1's library to 7 → draw 4 not 3) works and the life-half is
  pending the compiler batch-2 emit `LOSE_LIFE(QBin((n+1)//2))`.

**SCOPE FLAG:** `ability_tree.py` is outside the mission's authorized
edit list (`executor/**` + `run_scenarios.py`). It was touched because the
roadmap names the lane as `QPropField.LIFE` itself — the engine half
cannot exist without the enum member. Additive-only (one enum member +
one validation tuple entry), goldens byte-identical, every PC number
Δ0. Orchestrator should ratify or revert.

**treasure_token_activation — HARNESS gap closed (engine untouched).**
setup died `pool has no card 'Treasure'`: `compile_supply` filters
`is_token` records out of `metas`, yet the Treasure golden sits in
`supply.pool.results` (one ActivatedAbility {T},Sac → ADD_MANA 1 ANY) and
`binder.attach_pool`/`legality.spell_record` resolve it by real oracle_id.
Fix = token-golden fallback in `run_scenarios.py` for `"real"` refs on a
metas miss. The pack proves the chain: activate t (decision "W") → W paid
into Defiant Strike (soldier power 2 = payment consequence, ADD_MANA-ask
lane); activate t2 ("U") → U1 still in the NEW `expect.mana_pool` lane at
end (zero-equivalence both sides); `tokens {Treasure: 0}` proves both
sacrifices. **Keyless-mint law stands** (PITFALLS): engine-minted
(Gadrak) treasures remain pack-inaccessible — documented limitation,
report-lane `tokens.Treasure` works (probe). Supersedes the
"no mana-pool expect lane" note in `chromatic_orrery.json`.

## 2. Gates (all green; NUMBERS.md batch section has the rows)

302/302 packs · suspects 0/2 (chandras_pyreling + secure_the_scene,
owner-blocked signatures unchanged) · suite 2322+3 subtests 0 fail ·
grammar PC-1 303/305 PC-2 637/639 PC-3 0 PC-4 0 engine 297/305 (45 verbs)
Δ0, PC-6/PC-8 standing · catalog 0/10 NO repin · games 0 crash classes
100 decisive 48/52 mean_turns 33.49 exact Δ0 · pyright Δ0 (6 pre-existing
run_scenarios.py Counter FPs, HEAD copy proves 6) · ruff Δ0 (identical
per-file multisets).

## 3. Gotcha learned

LOSE_LIFE pins must assert the REMAINDER: half of 13 rounded UP is 7
LOST → life reads 6 (the first draft asserted 7 and caught a genuine
floor/round-up discriminator — 20→10 is ambiguous, 13→6 is not).

## Orchestrator ratification (scope flag resolved)
The QPropField.LIFE enum member in ability_tree.py is RATIFIED: additive, byte-stable,
PC Δ0, goldens byte-identical, lane-named verbatim by the roadmap (my scoping artifact) —
meets the R3 additive-grammar standard (same class as the EtBState additive, 17a). Owner
veto available; revert path = drop member + peer pack reverts to suspect.
