# 177: `cards/integration` after the M21 campaign: the era-boundary package (2026-10-30, NOT merged)

The owner asked (2026-10-29): "Fix the remaining M21 pool to be castable and playable, and mapped
properly." This follows up /174. The branch is pushed. Merging it changes M21 play deeply, so it
needs three things:
- the owner's OK;
- a gap between RL windows;
- the local agent's re-smoke and explicit re-pin (PIN law).

## What was done
- **Blind review of every castable M21 card (gate G2).**
  - 294 packets in 10 batches, 60 of them planted with a fault. Planted faults caught: **60/60**.
  - Real packets flagged WRONG: **68 of 234 (29%)**, most of them in the rule-dense cards.
  - Verified: 159 cards were stamped (G0–G4, with spec packs). 4 later dropped for schema-only
    changes (Cancel, Miscast, Keral Keep Disciples, Vito), leaving **155**.
  - Wave 4, the remaining 126 castable cards on the merged engine, is in progress.
- **Engine and compiler fixes,** about 70, each test-first with a pack. The review findings are V1–V44
  (session ledger), and BACKLOG has the residue.
  - **Decisions:**
    - the deciding player is asked (edicts, discards, sacrifices);
    - the legend rule (704.5j);
    - modes are chosen at cast;
    - "up to N" allows zero;
    - target player vs target opponent;
    - an Aura put onto the battlefield chooses its host;
    - discard down to seven at cleanup;
    - "end the turn" (724.1);
    - CHOOSE is mandatory.
  - **Combat:**
    - creatures can attack planeswalkers;
    - defenders can block;
    - an attacking bonus ends with combat;
    - per-slot targets and the damage source (dealer).
  - **Mana and costs:**
    - the pool empties at every step and phase end;
    - an engine payment witness taps for out-of-window payments (scaffold B-90);
    - summoning sickness applies to {T}/{Q} abilities;
    - "any color" is WUBRG only;
    - additional costs and targeting taxes are paid;
    - "discard your hand" discards the whole hand.
  - **Zones and objects:**
    - cards go to owner zones and ownership never changes;
    - counters, tapped status and tokens are cleared or cease on zone changes, with last-known
      information for dies triggers;
    - only DRAW is a draw;
    - nested changes are journalled once;
    - graveyard triggers fire;
    - phasing is a status;
    - exile "until it leaves" returns the card (R5-1, B-60c);
    - extra turns go in last-in, first-out order.
  - **Planeswalkers:** at 0 loyalty they die; an X lane for loyalty abilities; the 606.3 window.
  - **Protection:** full damage/enchant/block/target protection plus player protection (702.16).
  - **Conditions and quantities:**
    - existence checks (Furious Rise, Scavenging Ooze);
    - "if you do";
    - "died this turn" counted from events;
    - Hunter's Edge and Unleash Fury.
  - **Compiler fidelity:**
    - hexproof-from;
    - Peer into the Abyss's life loss;
    - Life Goes On;
    - Azusa;
    - Nine Lives;
    - Riddleform;
    - Barrin, Niambi and Ghostlight;
    - the named tutors;
    - Brash Taunter and Run Afoul;
    - Wildwood Scourge's X counters;
    - Basri's delayed triggers;
    - Falconer Adept;
    - token colours.
- **Ontology round R5** (docs/DESIGN_ATOM_ONTOLOGY.md §9–§10). Three adversarial rounds; implemented:
  - R5-1 (exile until it leaves, with the return registry);
  - R5-6 (TargetingEvent actor);
  - R5-7 (AbilityActivatedEvent plus `is_mana_ability`);
  - R5-10 (STACK_KIND_EQ plus the counter-window mode ask);
  - R5-11 (TokenSpec.colors);
  - TARGET_OPPONENT.

  Round 4 is still to come: R5-2 permissions, R5-5 copies, R5-8, R5-12 REPLACE, REVEAL.until, and
  the batching axis.

## Measured on the branch (4debe50)
| Measure | Result |
|---|---|
| `pytest MTG_bot` | 2 failed (the D3/D11 gates) / **4310 passed** |
| `tools/run_scenarios.py` | **652/652** |
| Card packs in the suite | 250 |
| M21 castable | **281** (main: 239; engine pool 281 of 285; out: Chandra ×2, Double Vision, Sublime Epiphany) |
| Soak, 200 games per deal mode | 0 crashes (main and the pre-fix branch: 1 Kinetic Augur crash) |

## For the RL pilot: read before the merge
1. **The game is different.**
   - Mana empties.
   - Tap abilities respect summoning sickness.
   - Planeswalkers can be attacked.
   - Players discard to seven.
   - Opponents make their own choices.
   - The 42 dead cards on main are castable.

   No earlier number carries over: treat this as a new era (/171–/173).
2. **Consumers to update at the merge.** All are in pinned files that the branch did not edit:
   - `tools/training/ab_duel.py` and `collector.py` send every ask to `world.active_player`. Opponents
     now decide discards, sacrifices, the legend rule, Aura hosts and the cleanup discard, so read
     `executor.decisions.asking_seat`. Otherwise the policy answers its opponent's questions.
   - `tools/eval/gameplay_eval_v2.py`:
     - `resolve_seat` is wrong for may/choose asks rotated by EachPlayer;
     - its act loop keeps acting after an effect ends the turn;
     - its heuristic never attacks a planeswalker.
   - `bc_data` SITE_KINDS lacks `discard`, `legend` and `enchant`.
   - Attack asks list planeswalkers between ATTACK and DECLINE.
   - Act windows skip activations with more than one target slot, so Garruk's −2 is unused.
   - A negative life total (CR 119.3) is a life token the model has never seen.
   - Re-pins already made on the branch, in test files only: `tools/training/test_duel_elo.py`
     (V36), and `test_bc_v2.py` (the monkeypatch order).
3. **Re-pin steps** (as in /174):
   1. Merge after a window ends.
   2. Re-smoke in real mode.
   3. Update `RL_PILOT_PIN` explicitly.
   4. Re-certify the puzzle corpus.
   5. Re-baseline every probe.

## Still weaker than printed (recorded, none stronger)
- **Teferi, Timeless Voyager's "can't phase in"** (D16).
- **Furious Rise's window and Chandra, Flame's Catalyst's rider:** pending R5 round 4.
- **Radha's land play and Demonic Embrace's graveyard cast** are inert (B-100).
- **BACKLOG entries:**
  - Primal Might (B-79);
  - Drowsing Tyrannodon (B-80);
  - See the Truth (B-81);
  - per-attacker attack triggers (B-103, R5-14);
  - untargeted "up to N" (B-107).
- **Snoop's "has all activated abilities of that card".**
- **Teferi, Master of Time has no window on the opponent's turn** (scaffold).
- **The batch-Magic limits:** no priority; one act window per turn.
