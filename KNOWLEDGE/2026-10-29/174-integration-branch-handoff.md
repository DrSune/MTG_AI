# 174: `cards/integration`, the era-boundary package (2026-10-29)

Handoff to the owner and the local agent. **Not merged.** The merge changes M21 play, so it waits for
the owner's OK, an RL-window boundary, and the local agent's re-smoke and explicit re-pin (PIN law,
/146).

## What the branch holds (43 commits over `main`, all pushed)
- **Card-onboarding tools** (/173): card records, the `verified` supply mode, `tools/cards/`, gates
  G0–G5, calibration.
- **FDN records:**
  - 60 verified: 35 compiled, 19 mapped, 5 basic lands and re-mapped Fireshrieker. Re-mapped
    Fireshrieker is unverified until a second verifier passes it, so the verified pool is 59.
  - 12 mapped but not verified.
  - 12 needs-atom.
  - Spec packs in `tools/scenarios/cards/FDN/` (40).
- **Engine and compiler fixes,** each test-first with a regression pack:
  - **B-49:** noncreature permanents castable. Plus five follow-ups:
    - #1 Chandra phantom free-cast;
    - #2 Aura enchant restriction;
    - #3 Tormod's Crypt player target;
    - #4 Ugin's −X gated;
    - #5 Garruk's +1 register.
  - **B-52:** counted static P/T is continuous.
  - **B-55:** a trigger with no legal target is removed (CR 603.3d).
  - **B-56:** "a creature died this turn" counts creatures only.
  - **B-57:** "combat damage to a player" means a player.
  - **B-59:** mandates respect duration.
  - **B-60a/b:** Equip and Speaker of the Heavens are sorcery-speed.
  - **B-61:** no damage from a blocked attacker whose blockers left (CR 510.1c).
  - **B-62:** planeswalker death replacements.

## Measured on the branch
- **Suite:** 2 failed (the D3/D11 gates) / 3560 passed. Packs 448/448. FDN card packs 40/40. M21
  goldens verify with 0 diffs after the re-bakes.
- **M21 golden re-bakes, each proven field-by-field to be only the intended change:**
  - 45 carriers;
  - 10 ENCHANT filters;
  - 3 equip and Speaker timings;
  - 4 damage recipients.
- **M21 pool:** castable 239 → 278 cards. Chandra ×2 and Ugin are now honestly unsupported.
- **M21 sweep** (castable, 400 games per deal mode):

  | Deal mode | Crashes, `main` | Crashes, branch | Anomaly-detector flags, `main` | Flags, branch |
  |---|---|---|---|---|
  | stress | 0 | 0 | 8 | 4 |
  | coherent | 1 (Kinetic Augur, pre-existing) | 1 (same) | 10 | 6 |

  The leftover flags are pre-existing classes (B-73).
- **Changed M21 games:** fixer A's fixes change 12 of 300 seeded games (2 winners flip); fixer B's
  change 2 of 200. The carrier changes most deals, because 39 more cards can be dealt.
- **Puzzle corpus re-certified:** `reports/puzzle_corpus_recert_integration_2026-10-29.json`.
  - 194 items, against 199 in `main`'s committed corpus. l1_ready stays 36.
  - `tools/audit/puzzle_corpus.json` is unchanged on the branch: eval_acc reads it, so adopting the
    re-cert is the local agent's call at the merge.

## What the merge means for the RL pilot
- Several of the fixed bugs made M21 cards **stronger than printed**: B-52, B-56, B-57, B-59,
  B-60, B-61. The pilot's policy has been trained and evaluated with them.
- The merge changes the environment. Win rates before and after are not comparable, so treat the
  merge as an era boundary in the /171 and /172 series.
- **Re-pin steps:**
  1. Merge after a window ends.
  2. Re-smoke in real mode.
  3. Update `RL_PILOT_PIN` explicitly, with provenance.

## Open decisions
- **B-60c (Kitesail Freebooter, Stasis Snare):** a `duration` role on MOVE_ZONE/EXILE (recommended)
  or an extra trigger. It is an ontology change, so it goes in a gated round.
- **Whether to keep spending Claude usage on mapping.** End to end, a card costs about 30k tokens
  (18k to map, 10k to verify). The other option is to hand mapping to local agents, measured by the
  same calibration (honeypot agreement, planted-fault detection).
