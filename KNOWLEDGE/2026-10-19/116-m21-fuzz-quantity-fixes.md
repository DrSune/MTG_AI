# 116 — M21 fuzz trio fixed in quantity.py: existence-count, turn-ledger NONCOMBAT_DAMAGE, undefined-P/T aggregation (r25)

Date: 2026-10-19. Wave: /109-addendum M21 smoke follow-up. Files touched:
`MTG_bot/core/executor/quantity.py` + `MTG_bot/core/test_executor_quantity_m21_smoke.py`
(new, 16 pins). No compiler/templates/ability_tree/`__init__`/selectors edits.

## Headline numbers (executed)
- Baseline (/109 addendum): M21 500 → 7 crashes / 1.4 % / 3 signatures.
- After fix: `--set M21 --games 500 --workers 4 --recheck 5 --deadline 1500` →
  **500/500 completed, crashed=0 (0.0 %), signatures=0**, wall 91.3 s. The
  canonical ledger `reports/m21_engine_smoke_2026-10-19.{json,md}` now carries
  THIS rerun (documented overwrite behaviour of the tool's stem discipline).
  No new crash class surfaced — nothing to ledger beyond the trio.
- All 7 pinned seeds rerun at the documented seed 201019, ALL "no crash":
  27/95/239/274/412 (S1), 384 (S2), 490 (S3).
- `pytest MTG_bot/core -q`: **2692 passed + 36 subtests** (2676 + 16 new pins).
- Packs (`tools/run_scenarios.py`): **410/410**.
- ruff: test file clean; quantity.py violation set byte-equal to the
  pre-existing one (I001 = the pre-existing `Rounding` misplacement in the
  ability_tree import block — my `ThisTurnKind` insertion is at ruff's
  correct position; UP007 = the untouched line-76 `Union` alias) → Δ0 new.
  pyright: 0 new (quantity.py 0 errors, test file 0 errors).

## S1 — AssertionError@quantity.py:880 (5 hits, Tempered Veteran)
- Verified shape (compile via `compile_card`): "put a +1/+1 counter on target
  creature WITH a +1/+1 counter on it" folds to
  `FAtom(HAS_COUNTER, counter_kind=PLUS_1_PLUS_1, count=None)`. /109's "BOTH
  fields None" was imprecise: **counter_kind IS bound; only count is None**.
- Why it validates: `_FATOM_RULES[HAS_COUNTER]` lists count required, but
  `FAtom.__post_init__`'s required-slot *enforcement list* (ability_tree
  ~1470-1483) omits `"count"` — grammar hole, proposal for the compiler/
  grammar wave (either emit `QConst(1)` at the fold or enforce the slot).
- Crash lane: the 12c QUERY surface (`play_activation → activation_target_
  slots → legal_targets → enumerate_candidates → eval_filter`).
- Eval fix (honest reading, per slot): count unbound + kind bound = the
  pred's own existence semantics — "with a {K} counter on it" ⇔ count ≥ 1.
  NOT the phantom-counter trap: threshold 0 makes the pred vacuously True
  for EVERY object (every creature a legal Tempered Veteran target); 1 is
  the text's meaning. Kind unbound (only hand-buildable — grammar enforces)
  = typed named `NotImplementedError` ("which counter is asked for?"),
  never a any-kind zero reading. Bound counts keep the ordinary resolve
  lane; non-card judged handles read characteristic-absent False (the
  KEYWORD_HAS convention, replacing a latent KeyError).
- The guard convention does NOT apply to this site: the crash is on the
  query lane, and a refusal there would still kill the game — the datum
  (which counters of which kind sit on the object) is fully present, so
  the honest answer is servable, and the /112 flag-don't-degrade law reads
  "flag what you CANNOT answer".

## S2 — NotImplementedError@quantity.py:373 (seed 384, cast Fungal Rebirth)
- Producer: **Chandra's Incinerator** (on deck B) — templates_b4 folds
  "This spell costs {X} less …, where X is the total amount of noncombat
  damage dealt to your opponents this turn" as
  `CostDeltaReduceGeneric(amount=QThisTurn(NONCOMBAT_DAMAGE, ALL_OPPONENTS))`,
  resolved by `build_payment_plan` inside `legal_casts`.
- Journal HAS the datum (events.py DAMAGE rows: `(amount,)` noncombat,
  `(amount, True)` combat — the 16c scope flag; subject = the recipient),
  so the branch is IMPLEMENTED, not refused: sum the turn window's
  noncombat DAMAGE rows whose subject is a seat of the referent side.
  Planewalker-recipient rows never count (CR 118.5: damage to a planeswalker
  is not damage to that player). Bare ctx (no journal) raises naming itself;
  LIFE_GAINED/CARDS_DRAWN QThisTurn kinds stay flagged (no corpus consumer).

## S3 — ValueError@quantity.py:417 (seed 490, cast Carrion Grub)
- Context read from the repro: **card:61 = Kinetic Augur**, printed P/T
  `*4` → identity power None (the /99 shape-gap family: ZNR Nighthawk
  Scavenger `1+*`). Reader: **Carrion Grub's static** "gets +X/+0, where X
  is the greatest power among creature cards in your graveyard" —
  `QProp(POWER, graveyard-selector, MAX)` materialized by
  `layers.recompute → pt_atom_delta` while the Augur sat in the graveyard.
- Fix (CR-defined aggregation): an object with NO power is not a member of
  the "powers among" value set — SELECTOR aggregations (MAX/SUM/MIN/FIRST)
  skip undefined-P/T objects, the same characteristic-absent rule that
  makes POWER_LE/GE read False for such objects. Scalar string-referent
  reads keep the strict ValueError (no-power ≠ zero-power). All-undefined
  population → the established empty-set 0. Honest cost: the Augur's real
  CDA power is invisible to the engine, so Grub's X UNDER-reports while an
  `*`-power creature card is in the yard — registered here as a CDA-
  coverage gap (compiler/ledger side), never a guessed number.

## Follow-ups (ledger)
1. Grammar/compiler wave: close the `count`-required hole (enforce the slot
   in `FAtom.__post_init__`) or emit `QConst(1)` at the "with a K counter"
   fold — then the S1 existence reading stays as the documented twin.
2. CDA `*`-power modelling (Kinetic Augur / Nighthawk Scavenger, /99
   family): until then MAX-aggregations under-report (S3 honest cost).
3. `QThisTurn(LIFE_GAINED/CARDS_DRAWN)` quantity lane: journal lanes exist
   (filter preds do it); implement the quantity twin when a consumer ships.
