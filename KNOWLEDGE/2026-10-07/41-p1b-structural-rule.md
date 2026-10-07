# 41 — T4 P1b stage 2: the structural promotion rule replaces the pilot allowlist (2026-10-07)

Full report: `docs/T4_PICK_ENUMERATION.md` §6. Headlines:

- **Rule**: `PICK_ASK_ALLOWLIST` deleted; `_is_liftable_pick`
  (CHOOSE ∧ QConst(1) ∧ referent None ∧ ¬IS_SOURCE ∧ ¬cost) is now the
  ONLY promotion rule — every future set's real picks promote
  automatically (§8 tokenizer law). Escape hatches: `PICK_ASK_FORCE_SILENT`
  (8 rows, L-27..L-29), `PICK_ASK_FORCE_ASK` (empty; loud §4 mode-gate).
- **Corrected census**: distinct surfaces **154** (stage-1's 155
  double-counted Liliana's emblem: embedded-in-parent AND standalone),
  disjoint decision-order partition core 22 / self-ref 55 / referent 36 /
  cost 26 / k≠1 15 — pinned pool-wide by
  `MTG_bot/core/compiler/test_promotion_predicate.py`.
- **Disposition** (oracle-text audited): 14 surfaces lift live over 13
  cards (incl. Crypt Lurker SACRIFICE — pilot's (name, verb) keying had
  missed it; and Idol + Primal Might after handler inspection: `_v_fight`
  resolves ONE_OF once via resolve_selector, Idol's exile-cast is a real
  controller menu). 8 pinned silent: Goremand/Run Afoul/Steward/Waker
  (opponent-seat decider — CR 701.8a "that player chooses"), Keral Keep
  (forced direction = no decision), Runed Halo (name menu absent),
  Furious Rise/Radha (top-of-library position, `_v_move_zone` TOP never
  resolves a selector) → ledger L-27/L-28/L-29.
- **Runtime, measured not assumed** (take_decision instrumentation,
  predicate off vs on, 373 packs): SAME 5 pilot packs hold the ask sites;
  the 14 new lifts fire ZERO scripted-lane asks (singleton auto-fill
  §1.4 / unexercised lanes) — the widening is a TOKENIZER (encoding) move.
  Goldens: 305 full regen, verify clean, 6 cards drifted.
- **Eval chain byte-reproduces the pilot**: items 164, punish_inaction
  153, no_discrimination 0, families 80, gold_rows_with_ground 84,
  candidate_ground 246/495, split new [] — all pins unchanged.
- **Gates (final, after every regen)**: `pytest MTG_bot/core -q` **2471
  passed +2 subtests** (5 new census pins); scenarios **373/373**;
  `pytest tools/audit tools/training -q` **153, zero fail**.

## review fixes (fresh-eyes pass, 2026-10-07)

- **(a) FORCE_ASK dead path → LOUD.** Reviewer flag verified TRUE: under
  the old gate (`shape and key in FORCE_ASK`), reaching the branch implied
  `shape ∧ (cost ∨ IS_SOURCE)` (shape-complete non-guarded surfaces are
  already promoted by the structural branch), so the promotion line was
  UNREACHABLE and the documented use-case rows (referent-bound near-misses)
  silently no-opped under the shape gate. Functionalizing is impossible in
  current grammar: `Selector.__post_init__` C2 forbids referent+ONE_OF, and
  non-controller deciders need provider-seat routing (L-27). Fix: branch
  re-gated on `mode is CHOOSE` (near-miss rows can no longer pass unseen);
  cost/self-ref hit keeps the pinned StateCorruptionError; any other hit
  now raises NotImplementedError citing L-27/C2. Pinned by new
  `test_force_ask_hit_on_a_near_miss_is_loud_not_silent` (referent-bound
  fixture on Rain of Revelation, assertRaises).
- **(b)** compiler docstring `L-27..L-30` → `L-27..L-29` (ledger has no
  L-30 row).
- **(c)** test_promotion_predicate docstring partition synced to the
  measured 154 disjoint partition (referent 36, was stale 155/37).
- **(d) Controller-seat tripwire** (L-27 class arriving via future sets):
  census test now scans every base-CHOOSE→live-ONE_OF lift and asserts its
  menu ControllerRef ∈ {YOU, ANY} — the sheet sets containing the seat the
  ONE_OF channel fires at. Data: 14 live lifts = 13×YOU + 1×ANY (Primal
  Might fight menu); goldens' 2 PRE-EXISTING non-YOU ONE_OFs (TARGET_PLAYER
  partition, ANY) are outside the promoted set, so the scan is scoped to
  lifts only. Honest limit (documented at the helper): zone.controller is
  the MENU seat not the DECIDER — menu-side opponent/bound-player sheets
  (Steward TARGET_PLAYER caught) fail the scan; decider-invisible rows with
  controller-side menus (Goremand YOU-battlefield) stay covered by
  FORCE_SILENT + oracle audit.
- Gates after fixes: `pytest MTG_bot/core -q` 2473 passed +2 subtests;
  scenarios 373/373; `pytest tools/audit tools/training -q` 153 passed.
