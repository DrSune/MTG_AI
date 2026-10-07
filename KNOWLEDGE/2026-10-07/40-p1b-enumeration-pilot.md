# 40 — T4 P1b: pick enumeration + ask-promotion pilot (2026-10-07)

Full report: `docs/T4_PICK_ENUMERATION.md`. Headlines:

- **Census**: 155 CHOOSE surfaces / 113 cards. Liftable core (QConst(1),
  referent None, ¬self-ref, ¬cost) = **22** surfaces (21 pack-mentioned).
  69 surfaces (44%) are IS_SOURCE self-designations — NOT blind picks.
  cost-victim 26 (sac lane already asks; CostDiscard = gap), anaphoric 37,
  k>1/search-tail 31 stay.
- **Pilot**: compiler `PICK_ASK_ALLOWLIST` (8 cards × MOVE_ZONE) lifts the
  first candidate selector onto the existing ONE_OF ask channel; loud
  `StateCorruptionError` guard for stale rows. Honest runtime blast radius:
  5 packs gain asks, zero silent changes (the first probe's 14 "trigger
  swallow" failures were ALL the §4 mode-gate artifact, see below).
- **Packs remediated** with falsifiable gold decisions + null-twin replay:
  rain_of_revelation, rousing_read (named hand cards; gold ≠ vocab[0]),
  sanctum (Early Card prefix shifts vocab[0]), experimental_overload ×2
  (lane-1 pool words `fire` + raw handle `card:2`/`card:6`; old 'Jolt'
  decision was a zero-discrimination vocab[0] accident).
- **Gates (executed 2026-10-07)**: scenarios 373/373; core pytest **2466
  +2st** (new `test_pick_ask_promotion.py` 5 pins); tools audit+training 153.
- **Eval loop (200 rollouts/item, HEAD worktree vs pilot)**: items
  157→164 (+7 all punish_inaction-class), families 77→80, eval 51→54 items,
  gold_rows_with_ground 79→84, candidate_ground 229/474→246/495,
  no_discrimination **0** both sides, fail_registered 11 unchanged.

## Decisions
- k>1 and referent-bound picks stay untouched (stage-2+); self-ref NEVER
  lifts while the r20c exemption is CHOOSE-mode-gated.
- Crypt Lurker SACRIFICE-menu / Obsessive Stitcher self-sac cost /
  Cultivate /31 search lane verified byte-identical to baseline — the lift
  does not spread within a card.
- Allowlist (not a rule) is deliberate for the pilot: stage 2 should propose
  the GENERAL rule only after the deferred-gap list (opponent-direction ask
  channel, name-menu, CostDiscard lane) is closed.
