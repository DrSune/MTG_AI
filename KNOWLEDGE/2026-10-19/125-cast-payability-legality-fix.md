# 125 — effect-CAST legality hole fixed (may-offer actionable while cost unpaid → stack.py:1093 raise; M21 eval seed 777003)

- Date: 2026-10-19. Lane: engine (executor/query + executor/selectors + tests). NO compiler/templates/ability_tree/stack edits. *(F3 correction, re-gate round 3: this line originally claimed "NO … selectors … edits" while round 2 threaded the clamp through `selectors.py` — the re-gate named that a false scope sentence; the truth is ~150 added lines in selectors.py: the role_handles CAST choke point + the three-shape clamp inside `resolve_selector`. Ledger honesty requires the headline to match the diff.)*

## Crash (frozen bsh_S3a era control, seed 777003, report `reports/shadow_M21_bshS3a3_vs_teacher_2026-10-19.json`)
- `executor: CAST cannot pay: cost:mana_generic:2<3` raised LOUD at `stack.py:1093`
  (payment invariant — deliberately kept loud; the offer side was lying).

## Root cause (verified by monkeypatch probes, no repo edits)
- **Conspicuous Snoop** (`card:39`): activated optional `Verb.CAST`, source =
  CHOOSE-∞ Selector over LIBRARY TOP filtered Creature-AND-Goblin, **no cost role**
  → pays printed cost. Fired via a `may` ask; deterministic CHOOSE stand-in
  (`resolve_selector`: binding else sorted[:count]) named **Battle-Rattle Shaman**
  (`card:9`, printed `{3}{R}`) while the seat's pool was `{R:3}` → unpayable fire.
- The r23a CAST gate in `query.optional_offer` checked only SpellAbility-carrier
  existence ("not mana") — the phantom-fire surface. No card-naming ask exists for
  this lane, so the seat could not have known what it was being charged for.

## Fix (executor/query.py, offer side = harvest side, /114 pattern)
- `_cast_effect_actionable` + `_cast_option_payable` in the `optional_offer` CAST gate:
  * payability folds the **same `build_payment_plan`** call stack.py:1093 makes at
    resolution (exact `ctx_for` shape, `mana_use=card`, X-default 0, CR 107.4) —
    legality and execution can never disagree (no parallel affordability arithmetic);
  * **CHOOSE / 12a-bound** designations cast EVERY designee → gate prices the
    stand-in's own slice (`enumerate_candidates` sorted[:count] mirror; bindings ⇒ all());
  * **TARGET / ONE_OF** designate ONE seat-picked card → one payable carrier keeps
    the branch (r18a anti-overfilter, CR 117.3);
  * **EMPTY `Cost` role = corpus cost-waiver idiom** (CR 498.2 "without paying its
    mana cost") ⇒ always payable, mana-blind BY DESIGN; a real `Cost` role REPLACES
    the printed cost (cast_card semantics); non-Cost (12a Ref) → treated as printed cost.
- All-designees-unpayable ⇒ offer narrows to `('skip',)` — auto-consumed by
  `offer_or_autopick` (offers.py:47), honest no-op, NEVER a phantom ask.

## Free-cast-rider audit (engine M21 pool, 8 CAST atoms)
- 4 EMPTY-Cost waivers: Chandra Flame's Catalyst hand-CHOOSE∞, Chandra Heart of Fire
  ×2 exile-CHOOSE∞, Idol of Endurance exile-ONE_OF 1 — mana-blind by design (compiler
  cost-waiver idiom), gate keeps them always-actionable.
- 4 printed-cost: Snoop LIB-TOP CHOOSE∞, Radha LIB-TOP CHOOSE 1, Demonic Embrace
  GRAVEYARD CHOOSE 1, Chandra Catalyst GRAVEYARD TARGET 1.
- No hidden add-cost riders in pool. Compiler-lane NOTE (off-limits here): Snoop's
  oracle text says cast "without paying its mana cost"; the compiled record carries
  no cost role → pays printed. Worth a compiler coverage review; this fix makes the
  offer honest under WHATEVER cost the runtime will charge.

## Test amendment (documented)
- `test_executor_r23a.py::test_a_spell_carrier_restores_the_full_offer` amended: its
  original expectation was ITSELF a phantom fire (fixture's unregistered `card:1`
  sorts first in library → fire-branch raises "no compiled record"); amendment
  registers spell records for both fixture spell and Lightning Bolt so the designee
  lane's actual pick is a payable carrier. Pre-amendment shape verified to raise via
  /tmp probe.

## Headline numbers (executed)
- New pins `test_executor_cast_payability.py`: **11 tests** (crash repro, affordable
  offered, CHOOSE(1) slice matrix, QUnbounded all-designees, ONE_OF any-branch,
  land-first designee-impossible, waiver mana-blind, cost-role-replaces-printed,
  referent-ungated, fire→instant resolves to graveyard + pool emptied, unaffordable
  fire unreachable via offer). With r23a: 27/27.
- Repro: `gameplay_eval_v2 --set M21 --games 2 --workers 1 --seed-base 777001`
  (covers 777002–777003, 777003 = the crash seed, swap=True) → **2/2 completed, crash=None**
  (was: raise@stack.py:1093).
- Gate eval: `gameplay_eval_v2 --set M21 --policy-a tools/training/bsh_S3a_s3_best.pt
  --matchups teacher --games 40 --device cpu --pool engine --workers 4 --seed-base 777001`
  → **40 games, seeds 777002–777041 (incl. 777003), 0 crashes**, 247 s wall
  (`/tmp/opencode/castpay_gate40.json`).
- `pytest MTG_bot/core -q`: **2793 passed + 36 subtests, 0 failed**.
- Packs (`tools/run_scenarios.py`): **415/415**.
- Fuzz `znr_engine_smoke --set M21 --games 300 --workers 4 --deck-pairs-seed 201019
  --recheck 5` → **300/300, crashed=0, signatures=0**, wall 55.8 s.
- pyright: **0 errors** on query.py + both test files; ruff: **all checks passed** (Δ0 new).
- Offer-side probe: every Snoop may-offer in the seed-777003 game narrows to
  `('skip',)` — the model is never even offered "fire" when no designee is payable.

## Adversarial gate round (2026-10-19, COMMIT-NO-GO → fixes)
The adversarial gate re-executed every claim TRUE but raised three
execution-confirmed blockers; all three are fixed and re-pinned.

- **B1 mixed-slice crash** (M21-live: Catalyst HAND CHOOSE-∞ `FAnd(())`; Heart of
  Fire top-3 UNFILTERED exile → `IS_EXILED_WITH_SOURCE` pop + EMPTY-waiver CAST):
  gate priced carriers but `_v_cast` cast the ENTIRE slice → land raised
  "no SpellAbility". **Fix = THE single choke point**: `selectors.role_handles`
  CAST branch composes `ok = query.cast_designee_ok` and threads it INTO
  `resolve_selector` PRE-SLICE (zone-enumerated lanes only: CHOOSE slice, ONE_OF
  vocab, RANDOM, ALL). Designee populations RANGE OVER SPELLS: lands never occupy
  a slot, never enter an ask vocab; ∞ populations clamp and cast their legal
  designees. Explicit designations (12a bindings, referent selectors) stay RAW —
  the LOUD per-card raise is kept for designated cards. Offer gate and runtime
  evaluate the SAME predicate = §10 menu == acceptance.
- **B2 unclamped ONE_OF/TARGET vocab** (the old pin ASSERTED the unpayable option
  present — flip documented): the ask vocabulary is clamped by the same
  predicate at BOTH surfaces — runtime (role_handles ok) and query
  (`_clamp_cast_target_slot` wired into `spell_target_slots` +
  `activation_target_slots`; min/max untouched: empty slot = announcement
  illegal = the rules answer). Test amended to assert ABSENCE of unpayable
  options; e2e fire-by-name casts the payable card while the unpayable sorts first.
- **B3 silent silencing** (Radha LIB-TOP `TYPE_EQ Land` miscompile): zero-carrier
  CAST filters now register LOUDLY once (deduped, counted, queryable in
  `executor.unresolved_effects` — /112 ledger pattern): `cast-gap {host}: filter
  admits 0 spell designees …` and the ∞ filter-omission
  `cast-gap {host}: CAST population admits K non-spell designees …`.
  **Two compiler-lane handoffs**: (1) Radha PLAY_LAND→CAST miscompile;
  (2) Catalyst `FAnd(())` admits lands where card text says "spell card"
  (Heart of Fire's UNFILTERED exile-pop CAST is the same class).
- **Typed /115 shape preserved** (this round's own caught regression): a
  BackFace-only compiled record is NOT a clamp member — `cast_run_gap` keeps it a
  designee so `cast_card`'s `FaceCastAbsentError` still reaches the guard lane
  (skip + LEDGER, pinned byte-identical in test_executor_dfc_cast.py); the
  may-offer for a face-gap-only population is skip-only and REGISTERS
  "face-cast-absent only". Land/creature plain-ValueError shapes ARE clamp
  members (the B1 crash class).
- Lane law in `_cast_effect_actionable`: bindings ⇒ all(ok) (explicit designations
  never re-picked); finite CHOOSE ⇒ POSITIONAL `all(sorted(cands)[:count] ok)`
  (land-first = skip, NO re-pick — the designation is positional); QUnbounded ⇒
  WHOLE clamped population payable, never any(); TARGET/ONE_OF ⇒ any(ok) with the
  vocab clamped at its surface. Gate/runtime bypass divergences (finite positional
  vs pre-slice clamp) accepted: the raise stays the engine's last line.
  *(superseded by the round-3 section below: the p1_probe falsified the
  "accepted" divergence — the runtime now enforces the SAME positional law.)*
- Gate-round numbers: pins **18** (dfc+r23a+cast_payability: 40 green); core
  **2800 passed + 36 subtests 0 failed**; pyright **0** on all three touched files
  (two new errors fixed: `Executor|None` narrowing, Binding list-vs-tuple);
  ruff **Δ0**. B1/B2 live repros rebuilt verbatim from the gate findings
  (`/tmp/opencode/b1_repro.py`): HoF exile-pop + Catalyst hand ∞ + Catalyst
  TARGET grave slot → ALL COMPLETE, no raise, gap ledger names both filters.

## Re-gate round 3 (AMEND→GO, F2 prescription applied 2026-10-19)
- **F2(1) positional slice-first**: the round-2 pre-slice clamp made the
  runtime RE-PICK on a finite CHOOSE (gate's p1_probe: head Colossus
  unpayable, pool pays Bolt → round 2 CAST Bolt — violating the gate's
  positional law, verbs.py's "deterministic first-n stand-in" and this
  docstring's own "first ``count`` of the Handle-sorted candidates").
  The clamp is now THREE-SHAPED inside `resolve_selector`: POPULATION
  menus (ALL / CHOOSE-QUnbounded / ONE_OF vocab / RANDOM / TARGET
  legality set) keep the population clamp (legal-set menus — legitimate);
  the finite CHOOSE lane slices the RAW population FIRST, then checks
  the HEAD — a failing head REFUSES the whole effect: no cast, no pool
  spend, a `cast-gap <host>: finite CAST head cannot execute: <Name>
  (<why>)` ledger row (reason classified via cast_carrier: "cannot be
  paid for right now" vs "not a SpellAbility carrier"); NEVER a silent
  re-pick, NEVER a raise (mandatory-lane crash class retired — the
  refusal is the CR 601.2e rules answer, mirroring
  `_clamp_cast_target_slot`'s include_zero pattern). The two doc-strings
  the round-2 clamp falsified (verbs.py:1421-1424, query.py finite branch)
  are TRUE again at runtime.
- **F2(3) random bias documented**: the RANDOM CAST draw is uniform over
  the CLAMPED pool (payable spells), not the raw zone population — a
  known, intended distribution bias (the raw draw only reached the
  raise-trap the B1/B2 laws retire; the offer gate already refuses such
  fires). Comment on the branch + pin `test_f2_random_cast_draws_the_
  clamped_pool` freezes it.
- **F2(4) TARGET-bound drop registered**: a BOUND designation the CAST
  legality clamp removes now writes `cast-gap <host>: CAST TARGET
  designation left the legal set: <Name> (<why>)` (was silent, contrary
  to its own round-2 comment; the CR 603.3-mode drop itself is
  unchanged). Reachable via the resolve_selector lane (the role_handles
  bound shortcut still returns plain designations RAW — the raw per-card
  raise stays the OTHER explicit-designation law).
- **Ledger API**: `_register_cast_gap` gained a public composition
  wrapper `register_cast_gap(executor, host, note)` + `cast_refusal_note`
  (names + reasons, read through the same carrier primitive the gate
  uses). No new exception types — the round-2 no-raise contract holds on
  every gated lane.
- **New pins** (cast_payability 18→23): p1_probe-as-test (refusal, no
  re-pick, pool intact, ledger names head+reason), land-head refusal
  (carrier reason), clean-head cast (tail behind the slice irrelevant,
  no ledger row), TARGET-bound clamp-drop ledger (resolve_selector lane),
  random-clamped-draw (12 draws, always the payable card).
- p1_probe + b1_repro re-run green on the delivered tree (probe prints
  "NO divergence: runtime refused too"; ledger row present).
