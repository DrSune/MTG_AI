# 122 — ZND-5 landing: bucket B10 (templates_b10.py, priority 118)

Date: 2026-10-19. Builds on the binding spec /121. UNCOMMITTED (owner law).

## What landed
- `MTG_bot/core/compiler/templates_b10.py` — 6 templates, bucket B10, priority 118
  (registry law: strictly above every existing bucket; disjointness probe vs B2b
  Cat/Dog/noncreature heads passes — neighbours keep exact owners).
  Head `_instant_sorcery_or_wizard()` = FOr(TYPE_EQ Instant, TYPE_EQ Sorcery,
  SUBTYPE_EQ Wizard), actor CONTROLLER_IS YOU. "Wizard" rides SUBTYPE_EQ as the
  CR-correct IR — the [G-A1] "TYPE_EQ never-fires" narrative was corrected the same
  night by the diff gate (see Gate section below; the engine word-tests all three
  type predicates identically at quantity.py:726).
- Tails reused from executed carriers: GRANT_ABILITY self/EOT; OptionalEffect(DRAW);
  PUT_COUNTER CHARGE self; DEAL_DAMAGE 1 any-target (3-branch, Player discriminator);
  MODIFY_PT self/EOT. Anticognition s1: COUNTER + FOr(Creature|Planeswalker) menu +
  FLAT Cost {2} unless (payer-seat safe, verbs.py kickback lane).
- Defer ledger untouched & verified: Master of Winds PT-fork (ZND-5f) is the ONLY
  "instant, sorcery, or Wizard" row still in the queue — the template matches nothing
  deferred. Anticognition s2 (ZND-5e) stays queued.
- `test_templates_b10.py`: 22 tests — registry laws + per-tail executor pos/neg
  falsifiers (P0 law satisfied) + counter lane tests.
- Pack `tools/scenarios/znr_cast_kind_triangle.json`: real Umara Mystic watches the
  cast feed; negative (Cliffhaven Sell-Sword, non-Wizard creature) cast FIRST (mana
  drain order made {W} exact), instant (Broken Wings) +2/+0, Wizard (Joraga Visionary)
  +2/+0 => power 1->3->5 triangle. 414/414 packs pass.

## Headline measurements (`tools/measure_grammar.py --set ZNR`, 2026-10-19, two runs identical)
- PC-1 0.3688 (104/282) -> **0.3830 (108/282)**, +4 flips: Umara Wizard//Umara
  Skyfalls, Windrider Wizard, Rockslide Sorcerer, Umara Mystic.
- PC-2 0.5413 -> 0.5496 (393 -> 399 sentences, +6).
- Register 333 -> **327 (−6)**: 5 batch-A trigger rows + Anticognition s1.
- M21: PC-4 golden_stability **0 diffs** (full report byte-identical except PC-5
  latency jitter 0.304->0.309 ms, machine noise).
- Fuzz `tools/eval/znr_engine_smoke.py --games 40`: 40/40, 0 crashes (Umara MDFC
  front-face flipped, so the fuzz gate was live).
- pyright 0 on all four touched/new files; ruff clean on them.

## Deviations from /121 (published, ground-truth driven)
1. **Expected flips = 4, not 5.** Relic Amulet is TWO rows away: its
   "{2},{T},Remove all charge counters from this artifact: It deals that much
   damage to any target" activation is also unparsed (no quantity-from-removed-
   counters lane exists). Clearing it would need a new lane -> NOT in ZND-5 scope.
   Relic Amulet's trigger row IS cleared; the card remains a PC-2 feeder.
2. **Register delta −6, not the spec's predicted −7..−10** (same root cause: the
   spec counted cards, the register counts rows; Anticognition contributes s1 only).
3. Test-shape note for future buckets: COUNTER_SPELL is frame-only (verbs.py raises
   for parked/unframed cards) — the falsifier must run through the RUNG-1 response
   window (Rung1Case), and the kickback ask vocab ("PASS","PAY") is a SUBSET of the
   window-offer vocab ("PASS", <counter-handle>): providers must dispatch on "PAY",
   never on "PASS", to tell the two asks apart. DRAW falsifiers need a seeded
   library — empty-deck draw is a silent no-op that blinds the negative.

## Pitfall added
- See PITFALLS.md entry appended today (counter-frame/kickback-vocab/draw-noop trio).

## Diff-gate verdict + same-night correction (adversarial, 2026-10-19)
- Verdict was **NO-GO (conditional)**: every EXECUTABLE axis passed (falsifiers real,
  numbers honest, defers clean), but the landing narrative carried a fabricated
  "verified" claim: the [G-A1] TYPE_EQ("Wizard")-never-fire trap does not exist as
  written — quantity.py:726 evaluates TYPE_EQ/SUBTYPE_EQ/SUPERTYPE_EQ as ONE shared
  type-line word-test, so the mutant builder (TYPE_EQ) fires AND all executor tests
  stayed green. Root cause: a biased prior (the spec's code-reading inference) was
  recited as gate-verified without executing the mutant.
- Fixes executed before commit (docs + one pin, zero behavior change):
  (1) templates_b10.py header + builder docstring rewritten to the truth (atom-kind
  is a STRUCTURAL, CR-correctness pin; behavior falsifiers target fire/never-fire);
  (2) three test narratives corrected; (3) pack note's "TYPE_EQ stays silent /
  power 3" falsifier clause removed; (4) [G-A1] corrected in /121; (5) PITFALLS
  entry with the mutation recipe; (6) NEW regression test
  `test_type_predicates_share_one_word_test_branch` — TYPE_EQ("Wizard") and
  SUBTYPE_EQ("Wizard") heads BOTH fire on a Wizard-creature cast through the real
  stack (23/23 b10 green; a future strict-predicate split must update it
  consciously). All headline numbers above unchanged by the correction.
