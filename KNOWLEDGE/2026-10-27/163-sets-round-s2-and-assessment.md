# 163 — Sets round S-2 (B11 general clauses), a rules bug it exposed, and the SOTA assessment (2026-10-27)

Owner request (2026-10-27, afternoon):
- use the 27B for the benchmark, self-playing with different decks;
- fix more compiler issues;
- explain the atomic subcomponents;
- evaluate the approach against the state of the art.

The full answer to the last two is `docs/ASSESSMENT_2026-10-27.md`.

## S-2 on branch `sets/onboarding` (commits `1c526bc`, `5ec4646`; merge scheduled after night-3)
- **Bucket B11** (`core/compiler/templates_b11.py`, priority 10, fallback only) is the first
  noun-phrase grammar in the compiler.
  - The target phrase covers one type, or two joined by "or", or "nonland permanent". It takes an
    optional controller ("you control" / "an opponent controls" / "you don't control"), an
    optional "with <keyword>" or "with power N or less|greater", and either suffix order.
  - The regex is built from the builder's own tables, which closes the B-36 class.
  - Five verbs use it: destroy, exile, return to its owner's hand, tap, untap.
  - Also added: "Enchanted|Equipped creature gets +P/+T [and has <keywords>]", bare "Equip
    {cost}", "Enchant <type> [or <type>]", and "Create <n> P/T <color|colorless> <Subtypes>
    [artifact] creature token(s) [with <keywords>]".
- **Before B11, none of these parsed:** "Destroy target artifact.", "Destroy target enchantment.",
  "Create a 1/1 white Soldier creature token.", "Enchanted creature gets +2/+2." and bare
  "Equip {3}".
- **Identity:** on the 52 sentences of M21/ZNR/M20/KHM that an older template also matches, B11
  builds byte-identical IR (`test_templates_b11.py`). M21 goldens 305/305 are unchanged.
- **Three ZNR packs had asserted the old partial compile.** Their notes said so ("tap target
  creature ... DROPPED"; "effect is Conditional(WAS_KICKED, DRAW 1 YOU)").
  - They now give the new targets and check that the new clauses execute.
  - Pressure Point taps the goat (tapped lane).
  - Into the Roil and Roost of Drakes return an opponent's creature to its owner's hand.
  - The rockslide triangle's first tick names the goat: a cast step lifts `player:N` into the
    spell's targets (run_scenarios r22b). Its kind-gate reading is unchanged.
  - The runner is unchanged; Transmogrify depends on that lift.

| | Before S-2 (after S-1) | After S-2 |
|---|---|---|
| ZNR PC-1 | 0.3936 | 0.4078 (115/282) |
| ZNR PC-2 | 0.5634 | 0.5826 |
| M20 dev PC-1 | 0.1146 | 0.1465 |
| M20 dev unseen-shape PC-2 | 0.1283 | 0.1504 |
| M20 test PC-1 (sealed read) | 0.1524 | 0.1619 |
| M20 test unseen-shape PC-2 (sealed read) | 0.0870 | 0.0994 |
| KHM dev PC-2 | 0.3263 | 0.3552 |
| KHM test unseen-shape PC-2 (sealed read) | 0.1333 | 0.1686 |
| M20 whole set, dealable cards fully compiled | 96 | 101 |

The sealed test splits moved with dev, so the clauses generalize.

Suites at the end of the round:
- `pytest MTG_bot`: 2 fail (the D3/D11 gates), 3458 pass.
- Packs: 428/428.
- `pytest tools`: 270 pass, 35 skipped (no checkpoints in the worktree).
- Fuzz: 40/40 games, 0 crashes on M20, KHM and ZNR.

## Found while building it
- **B-43, a live M21 rules bug.**
  - "Return … to its owner's hand" is encoded as `Zone(HAND, ANY)` on Barrin, Tolarian Archmage;
    Niambi, Esteemed Speaker; and Roaming Ghostlight.
  - `zone_owner` (`executor/selectors.py:162-175`) resolves ANY to seat 0, so the bounced card goes
    to seat 0's hand, whoever owns it.
  - Three other M21 cards already use the correct `Zone(HAND, OWNER)`: Read the Tides, Sublime
    Epiphany, Unsubstantiate.
  - The OWNER branch also reads `controller_of`, not an owner. The World has no owner field.
  - **Not fixed:** the fix changes M21 games, and the RL pilot checks byte-identical M21 episodes.
    Schedule it at a pilot era boundary: three builders → OWNER, three goldens re-baked, and a
    pack bouncing an opponent's creature.
- **B-42, MOVE_ZONE divergences.** The moved object is named `cards` in 67 uses and `target` in 20
  (the exile family). The owner's-hand destination is spelled two ways (B-43).
- **B-44, one-card predicates.** `LIFE_LEAD_OVER_START_GE`, `NAME_PARTITION_COUNT_GE`,
  `ATTACK_AGAINST_COUNT_GE`, `NOT_FIRST_DRAW_THIS_STEP` and `INSTANT_OR_SORCERY_CAST_THIS_TURN` are
  candidates for decomposition. That is a gated ontology round, not done here.
- **What a trigger-prefix composer would add.** Joining a known trigger prefix to a tail that
  already parses would newly parse only 9, 22 and 8 unique sentences (ZNR, M20, KHM). Prefixes are
  usually the unknown part. The next step is a constituent grammar (assessment §2.5), not a
  composer.

## 27B self-play benchmark (started 15:01, detached, tmux `bench27b`)
- **Setup:**
  - `llm` vs `llm` on four deals in parallel, each deal a duplicate pair (two decks, seats
    swapped);
  - model `nvidia/Qwen3.8-27B-NVFP4-32k-instant`, masked names, the primer included;
  - M21 castable pool, a 40-turn cap and a hard stop at 23:45, before the window.
- **Pace:** about 60 s per decision under contention with the local agent. The prefix cache hit
  rate is about 96%, so the primer is reused.
- **Output:** `~/mtg_ai_evidence/bench_selfplay_2026-10-27/`. Results go to DESIGN_BENCHMARK §10
  when the pairs settle.

## Assessment, in one paragraph
The engine is the right family: compiled Oracle text, as in MTG Arena's GRE and phase-rs. Its IR
discipline is better than either publishes. It is not state of the art in parser generality: Arena
compiles about 80% of new cards; here 11% of M20's new-text cards compile at first touch. Nor in
rules fidelity: there is no priority or stack. The play stack is not a state-of-the-art approach:
it reads names, sees hidden zones, imitates a heuristic and does no search.

The fix order is: rules fidelity, an IR card encoder, engine throughput (0.25 games/s), privileged
teacher → per-seat self-play RL, then determinized ISMCTS.

The omniscient net is reusable as a privileged teacher or critic. That is the Suphx and AlphaStar
pattern, which corrects REVIEW A-1's "contradiction" framing for training: it is only wrong for
the acting policy. Evaluation is at or above field practice.

Merged to main 2026-10-28 03:45 CET as 6674753; the next window needs re-smoke + explicit re-pin. M21 compile output and supply unchanged, M21 goldens 305/305. Engine behaviour changes only where a game used to crash (CR 107.3b X=0) and for cards that newly compile (B11, B12, B13 frames). Post-merge gates: pytest MTG_bot 2 failed (the D3/D11 gates, same as the pre-merge baseline) / 3505 passed; run_scenarios 429/429; verify_goldens M21 = [].
