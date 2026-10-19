# 117 — ZNR fuzz B1/B2 fixed: blocker asks gated on CR-completability (Kuhn); MDFC face-cast typed refusal + guard

Date: 2026-10-19. Wave: /112 follow-up fuzz lane (crash pair found by the
500-game rerun). Files touched (executor lane only):
`MTG_bot/core/executor/__init__.py`, `MTG_bot/core/executor/stack.py`,
`MTG_bot/core/test_executor_blockers.py`,
`MTG_bot/core/test_executor_dfc_cast.py` (new). NO compiler/ability_tree
edits (sibling wave owns those; B2's permanent root-cause fix is a
PROPOSAL below — the lane ships the honest refusal, not a fabricated face).

## Headline numbers (executed)
- Both repros zero-raise: `--repro 1269` → `no crash — 41 turns, 81 acts,
  game over: player:1`; `--repro 1715` → `no crash — 24 turns, 48 acts`
  (deck B there literally holds `Beyeen Veil // Beyeen Coast` +
  `Coveted Prize`, the exact crash pair). Cmd:
  `.venv/bin/python tools/eval/znr_engine_smoke.py --repro N --set ZNR
  --deck-pairs-seed 201019 --turn-cap 150`.
- Fuzz: `--set ZNR --games 500 --deck-pairs-seed 201019` →
  **games=500/500 crashed=0 (0.0%) signatures=0** wall 76.1 s
  (json `reports/znr_engine_smoke_2026-10-19.json`).
- Tests: `test_executor_blockers.py` **23/23** (incl. new seed-1269 pin),
  `test_executor_dfc_cast.py` **6/6**. Full `pytest MTG_bot/core -q` →
  **2698 passed** + 1 failed = `compiler/test_coverage.py::TestRegistry::
  test_all_buckets_registered` ('B9' extra) — SIBLING work-in-progress in
  their `compiler/coverage.py`/`templates_b5a/b5b.py` diff (same owner as
  quantity.py), NOT this lane. Packs **410/410** (`tools/run_scenarios.py`).
- pyright 0 (all four files). ruff Δ0: the lane's only NEW violation
  (test F541) fixed; the 4 remaining in `__init__.py` (N999, TRY004×3)
  sit on byte-pre-existing lines 1/353/585/653, untouched.

## B1 — `RuntimeError@executor/__init__.py:1721` (seed 1269)
- Crash: menace attacker blocked by EXACTLY ONE creature — the final
  CR 702.113 invariant. Root cause: the per-blocker ask gated the FIRST
  menace word on `remaining_after >= 1`, i.e. remaining CANDIDATE COUNT,
  not pair-LEGAL completions. The pathological shape needs no exotic
  cards: any blocker whose restriction keeps it OFF the menace attacker
  (seed 1269: `Shacklegeist` "blocks only creatures with flying";
  protection and PREVENT_EFFECT blockers behave the same) makes the
  second slot unfillable while the raw count says one exists. The
  committed first pair stranded the menace at one blocker → raise.
- Fix (lane, enumeration only): precompute the `pair_ok` matrix once per
  step (asks mutate no state) + a nested `completable(partial, tail)`
  Kuhn bipartite matcher — demands: unassigned mandated non-menace
  attacker → 1 slot, mandated menace at 0 → 2, in-progress menace → 1;
  tail blockers are the slots. A word is offered IFF pair-legal AND
  committing it leaves a completion; NONE is offered under exactly the
  same test (the silent-resolve must not strand a menace either — the
  old C15 "narrow to NONE" path used to FORCE the stranding pair). A
  blocker with no completable word is SKIPPED silently (no ask, no
  phantom row; a mandated non-menace attacker it can still legally take
  is salvaged first). Forced-mandate narrowing kept. Both narrowing
  `RuntimeError`s deleted (they were reachable states of the old
  scheme). Final MANDATE_BLOCK check made menace-aware
  (`need = 2 if menace else 1`: one free blocker behind a menace is
  CR 702.113 making the "if able" mandate unfulfillable, not a
  violation). The final one-blocker-menace `RuntimeError` STAYS as the
  loud last-line invariant.
- Pin (real cards): `Bone Pit Brute` (menace) + `Baneslayer Angel` +
  synth Gamma attackers; synth Alpha + `Shacklegeist` blockers. Pin
  truth learned the honest way: a vanilla blocker CANNOT block the
  Angel (CR 509.1b flying) — the synth third attacker keeps the ASK
  alive. Asserts the Brute word is ABSENT from Alpha's asked
  vocabulary, NONE present, nothing blocks, zero raise, life 20−4−5−1.

## B2 — `ValueError@executor/stack.py:1040` (seed 1715, "CAST Beyeen Veil // Beyeen Coast: no SpellAbility")
- Root cause (compiler, sibling-owned): the ZNR spell-front MDFCs
  compile to records whose ONLY ability is the `BackFace` node — the
  front sentence is never parsed (`unparsed: (…, 'spell-effect')`), so
  assembly drops the front SpellAbility. /106's uplift covered ONLY
  enters-tapped + add-mana faces; spell-effect fronts remained a known
  gap. Producer: `Coveted Prize` free-cast ("you may cast target
  permanent card with mana value 3 or less from your graveyard")
  legally selects the DFC from the GY → `cast_card` hit the bare
  no-SpellAbility ValueError → crash.
- Lane fix (r24a twin pattern, /112): `FaceCastAbsentError(ValueError)`
  + `_face_cast_msg(name)` (byte-exact site message rebuilt from the
  stored face name) + `face_cast_absent()` predicate in `stack.py`;
  `cast_card` raises the TYPED refusal when there is no SpellAbility
  AND a `BackFace` on the record (a plain land keeps its byte-identical
  ValueError — lookalike + tampered-`face_name` negatives pinned).
  `_run_guarded_effect`'s skip predicate extends to
  `referent_absent(exc) or face_cast_absent(exc)`: the cast is WAIVED,
  the `unresolved_effects` ledger entry IS the trace (no invented
  journal row — same discipline as r24a). NEVER fabricates a face cast:
  back-face PLAYABILITY stays owner-gated per /106.
- SIBLING PROPOSAL (permanent fix, compiler wave): give spell-front
  MDFCs their FRONT SpellAbility — gate the back-face fold on the front
  sentence actually parsing (or add the missing front templates, e.g.
  the −2/−0 modal combat trick like Akoum Warrior); register the
  `spell-effect` front shapes in the coverage registry so the fold can
  no longer silently swallow a castable front.

## Pins — test_executor_dfc_cast.py (new, 6)
compiled-front MDFC casts; back-face-only typed refusal (type + byte-
exact message + predicate, no movement/stack-frame/ledger); plain-land
refusal is NOT the face-cast class (+ byte-identical legacy message);
lookalike ValueError and hand-tampered `face_name` predicate negatives;
guarded-lane skip + exactly-one ledger entry; ledger dedupe counts
(two waivers of the same producer name fold to one key).
