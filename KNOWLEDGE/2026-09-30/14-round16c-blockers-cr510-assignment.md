# Round 16c — blockers (CR 509) + damage assignment (CR 510) + Herald policy + token binder

Date: 2026-09-30 · base HEAD 428cf56 (16b) · scope per /11 §16c.

## What landed
- **Blockers (CR 509)**: per-blocker ask `block:<card>:<turn>` = attackers the
  permanent may legally block + `NONE` (C15: NONE only when emptiness is
  legal). Legality consumers wired: tapped/defender, flying-reach (a blocker
  with **flying OR reach** blocks a flyer — 509.1b fix found by test),
  two-sided protection (`layers.protections_of` reads the live PROTECTION
  KeywordAbility params), menace (inclusion rule: a pair needs
  assigned+remaining ≥ 1; the last unasked blocker in front of a stuck menace
  attacker loses its NONE word), MANDATE_BLOCK narrowing (Canopy Stalker,
  `mandated_to_be_blocked`), static + runtime PREVENT_EFFECT consults
  (`replacements.prevents_block_declaration`: node slots filter/subject vs
  the BLOCKER, `blocked` vs the ATTACKER; Tome Anima's draw clock
  (CARDS_DRAWN_THIS_TURN_GE — journal-backed, first live consumer) judges
  LIVE per pair). A creature legal against NOTHING is never asked.
  DECLARE_BLOCKERS rows: subject=blocker, data=(attacker, group); settle
  after the blocker step so block triggers resolve before damage (509.4);
  `blocked_by` + the combat ledgers clean on leaves/EOT.
- **CR 510 assignment**: one COMBAT_DAMAGE row per dealer per wave,
  `data=(plan,)`, plan canonical-sorted `((amount,recipient),…)`. THE
  DEALER SET IS BOTH SIDES (blockers assign to the attacker they blocked —
  16b's attacker-only wave superseded). Order asks `order:<dealer>:<slot>`
  POSITIONAL picks (deviation: the mission's permutation-index-cap-6 vocab
  would crash real games; positional is vocab-honest and equivalent for the
  corpus). Trample `trample:<dealer>:<slot>` = EXTRA onto that blocker,
  asked only when power > total lethal; the remainder lands on the attacked
  object. Deathtouch marks lethal (ledger flag → SBA). A blocker whose
  attacker left combat announces nothing (no damage, no row).
- **Herald [-7] `DAMAGE_ASSIGN_POLICY`**: `policy:<dealer>:<turn>`
  (AS_BLOCKED|UNBLOCKED); AS_UNBLOCKED re-routes the ASSIGNMENT while the
  BLOCKED STATUS stands (the blocker still hits back — CR "as though
  unblocked"). Grant rides the live `_granted` map (liveness for free).
  **CR-version scope**: damage-assignment ORDER was removed from the CR in
  Nov 2024 (Foundations); the engine models M21-era CR 510.1 (order ask +
  lethal-first greedy). 16d candidate = free-distribution (reuse the
  trample split, delete the order ask).
- **Token binder**: `_v_create_token` synthesizes a full CardRecord
  (printed-keyword KeywordAbility rows + spec abilities + is_token) and
  `binder.register_token` registers it before the op-boundary snapshot —
  the ETB ZONE_CHANGE row then attaches like any permanent. The Whale's
  Pirate binds its own "can't block" static (pair-vetoed, never asked) and
  its "Creatures you control attack if able" mandate (attack vocab
  narrowed to ATTACK for the whole controller).
- **Harbinger fix**: `_match_damage` finally consumes `node.source`
  (vs row `cause`) and `node.combat` (vs the 16a row flag); bind-time scope
  raises retired (Subira/Pyreling/Incinerator `combat:False` shapes bind).

## Bugs the design pass caught (each pinned by a test)
1. `attach_card` order: `replacements.attach_source` sweeps its own source
   first — called AFTER `layers.attach_source` it expired the static
   prevents the layers had just registered (Whale tokens were blockable).
   Replacements first, layers last (`binding._register`, `bind_emblem`).
2. `_combat_damage_atom` hardcoded the PLAYER-zone target and the 16a
   player-side rule is binding-blind → ALL combat damage bypassed blockers.
   Recipient-kind lane (`_CARD_TARGET` binding-first) added.
3. Blocker-side dealers missing from the damage wave (16b leftover).
4. Trample merge used `plan.index(new_entry)` — merge in place.
5. `protections_of` matched `_keyword_name(KeywordAbility-node)` (repr
   noise) — must pass `node.keyword` (Baneslayer's veto silently dead).
6. No settle between the blocker step and the damage step — block triggers
   (Snarespinner's pump) resolved AFTER damage.

## Verification (final code)
| gate | result |
|---|---|
| core suite | **2076 passed + 4 subtests** (was 2054; +22 blockers tests) |
| validation packs | **16/16** (7 NEW: block_save_trade, block_defender_and_tapped, trample_excess_partition, gloom_sower_blocked_swap, stalker_must_be_blocked, whale_pirate_token, herald_assigns_unblocked) |
| engine 30 (seeds 0-29, cap 60) | survived **28/30 (93.3%)**, crash classes **0**, 3 deaths-by-combat-damage (reported apart); mean 58.7t |
| all-305 ×10 | 8/10, sole crash GAIN_CONTROL (Enthralling Hold) — baseline |
| engine10 / castable10 | 9/10 (0 crashes) / 8/10 (0 crashes) |
| catalog | repinned **6676 entries / 10 games**, post-repin **0/10 diverge**; the one seed that diverged from the pre-fix pin: seed 2 entry 597 — blocker damage now routes correctly → game ends life-zero instead of drifting to the cap (located + clean outcome) |
| determinism | engine30 double-run: only argv/wall differ (semantic byte-identical) |
| replay | seed 2 (the blocker game) ×2 HTML byte-identical |
| PC | PC-1 0.9869 · PC-2 0.9922 · PC-3 0 · PC-4 0 diffs · PC-5 0.282ms — all PASS; PC-6 (orphan=1, DRAW 0.0934) and PC-8 (0.3213) unchanged baseline FAILs (not 16c targets) |
| engine gate | **293/305** dispatch-ready (V2 = 43 verbs); flip probe: −{MANDATE_BLOCK, DAMAGE_ASSIGN_POLICY} loses exactly {Canopy Stalker, Garruk, Savage Herald}, gains nothing |
| pyright / ruff | 0 errors; no new ruff violations vs HEAD in any touched file |

## Known gaps (documented, not patched)
- **Bone Pit Brute cannot enter in a PACK**: its ETB TARGET trigger has no
  designation lane (TargetingEvent is the 12c placeholder — same family the
  PC-8 gap measures); the engine's honest raise kills the runner. Menace is
  pinned in `test_executor_blockers.py` instead (add_card-before-attach
  sidesteps the ETB legitimately). Fix belongs to the target-designation
  round.
- Planeswalkers never attack (players-only combat v1).
- "to a player" damage scope compiles universal (frozen-grammar lossy
  pair, /11 note) — the scope flags now BIND, recipient-type fidelity waits
  on a grammar round.
- Multi-blocker piles: each blocker deals to its attacker (CR-correct);
  blocker-side ordering asks (510.2 multiple blockers) unimplemented —
  no corpus need.
