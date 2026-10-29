# 173: Card onboarding by agents and play-time verification; FDN round 1 (2026-10-29)

Owner, 2026-10-29: "We should get some more cards encoded, and make sure they work as intended at
play-time ... so we dont introduce bugs for our play engine to abuse." Plan:
`docs/PLAN_CARD_ONBOARDING.md`. Guide for mapper and verifier agents: `docs/MAPPER_GUIDE.md` (on the
branch).

## What exists (branch `cards/mapping`, not merged; worktree `/home/sune/Desktop/MTG_AI-sets`)
- **Card records** (`MTG_bot/core/compiler/card_records.py`). An agent-mapped card is data at
  `MTG_bot/data/cards/<SET>/<oracle_id>.json`.
  - It holds keywords and abilities as canonical `to_dict` JSON, passed through the compiler's own
    canonical passes.
  - `text_sha` pins the printed text the mapping read; `verified.tree_sha` pins the tree that passed.
  - Games apply only verified records. New supply mode `verified`.
  - M21 has no records, so it is byte-identical: suite 2 failed (D3/D11 gates) / 3507 passed.
- **`tools/cards/cardtool.py`.**
  - `show` (per-sentence parse, tree as Python), `similar` (exemplar retrieval over 19 sets),
    `parse` (the compiler on any wording).
  - `try` / `write` (draft → G0 → G1), `needs-atom`, `probe`, `mutate`.
  - `packet` (blind review packet, optionally planted), `runpack` (with `--card --draft`), `verify`.
- **`tools/cards/round.py`**: packets with hash ids and planted twins, `score-mappers`,
  `score-verifiers`, `apply`. **`tools/cards/soak.py`** is gate G5.
- **Gates.**

  | Gate | What it is |
  |---|---|
  | G0 | Static checks |
  | G1 | Engine probe: every legal variant on a fixed board, about 20 trigger stimuli, end-of-turn diffs |
  | G2 | Blind review; packets may carry planted faults |
  | G3 | Mutation analysis with fault-model operators; equivalent classes skipped |
  | G4 | Spec packs, kept in `tools/scenarios/cards/<SET>/` |
  | G5 | Soak: crashes, detectors D1–D6, abuse screen |

## FDN round 1 (Claude agents: 2 mappers, 3 verifiers)
- **Mapping.**
  - 50 cards, 6 of them hidden calibration cards.
  - Of the 44 real cards: 30 were written onto existing components and 12 are needs-atom. Each
    needs-atom names a missing general axis: turn-history counts, an edict's deciding player,
    exile-until-leaves, a cast-timing permission, a life-gain prohibition, COPY. 2 were skipped
    (probe limits, since fixed).
  - Calibration: 4 of 5 attempted calibration cards byte-exact. The miss differs only by
    `SEARCH.controller` (D12), and the mapper reported that card contaminated.
- **Verification of compiled cards.**
  - 48 packets of FDN cards no one had checked, 8 of them planted faults.
  - Planted faults caught: 8/8 (95% CI 0.68–1.00).
  - The 4 real packets failed are genuine bugs: 3 × B-49 and Obliterating Bolt (B-62).
  - `verify` re-ran every gate and stamped **35 cards**.
- **Verification of mapped cards:** in progress (39 packets, 8 planted, two verifiers).
- **Soak** (300 games each).
  - FDN compiled: 0 crashes, 1 lifecycle hit.
  - With the unverified mapped records: B-55 crashed 37 games (Pirate's Cutlass). The per-card probe
    missed it because its board added the Pirate.

## Engine findings (docs/BACKLOG.md; repro packs in `tools/scenarios/known_bugs/`)
**Stronger than printed, live in M21.** The RL pilot plays these cards today:
- **B-52:** a counted static P/T bonus freezes (Kinetic Augur).
- **B-56:** "a creature died this turn" counts a sacrificed Treasure (Twinblade Assassins).
- **B-57:** "combat damage to a player" fires on damage to a blocker (Jeskai Elder and 3 more).
- **B-59:** lures never expire.
- **B-60:** equip at instant speed; Kitesail Freebooter's exile is permanent; Speaker of the
  Heavens loses its sorcery timing.
- **B-61:** first strikers kill their blocker, then hit the player (CR 510.1c).

**Correctness:**
- **B-49:** 45 M21 noncreature permanents were uncastable.
- **B-55:** a trigger with no legal target resolves and crashes.
- **B-50:** resolved end-of-turn grants end with their source.
- **B-62:** planeswalkers ignore "exile instead".
- **B-53:** "target player" offers only opponents.
- **B-51:** CHOOSE offers an empty pick.
- **B-54:** minor findings.
- **B-58:** a static Seq uses its first selector for every step.
- **B-63:** eight packs declare a `tapped` setup key that was never honoured; honoured, rewind fails.

**Divergences:**
- **D12:** `SEARCH.controller` is written on 14 compiled cards and left out on 15, and the executor
  never reads it.
- **D13:** cost victims are written as TARGET or CHOOSE for the same meaning.

## Branches (all pushed)
| Branch | Holds | Effect on M21 |
|---|---|---|
| `cards/mapping` | the tools and records | invariant |
| `cards/castable-permanents` | the B-49 carrier and its follow-ups (Chandra phantom ability, Aura enchant restriction, Tormod's Crypt, Ugin, Garruk) | changes |
| `engine/fixes-combat` | B-55, B-57, B-61, B-62 (fixer agent working) | changes |
| `engine/fixes-statics` | B-56, B-52, B-59, B-60 (fixer agent working) | changes |

Merge only at an RL era boundary, after the window ends, with the local agent's re-smoke and
explicit re-pin. Every branch except `cards/mapping` changes M21 episodes.

## Next
1. Apply the mapped-card verdicts and soak FDN with verified records.
2. Merge the fix branches.
3. Scale the mapping: more mappers on the rest of FDN, then M19 and M20. Report the needs-atom share
   per set, which is the saturation signal for the long RL run.
