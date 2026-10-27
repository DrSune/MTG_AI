# 164 — Red-team of the learning architecture (atoms + learned encodings + relational transformer) (2026-10-27)

Owner, 2026-10-27, on the atomized approach: "If there is no existing model that outperforms humans
in MTG, we need a new RL approach anyway … do an adversarial pass and try to find out why the
atomized subcomponents, learned encodings, a relational network, and a transformer wouldn't work."

Full document: `docs/REVIEW_ARCHITECTURE_2026-10-27.md`. Evidence comes from
`tools/audit/arch_probe.py`. The report is `reports/arch_probe_2026-10-27.json`, measured on branch
`sets/onboarding` `5ec4646`.

## Measured
- **Aliasing among fully compiled cards is essentially zero.** M21, ZNR and KHM have no groups of
  different rules text with identical IR. M20 has two groups, both real synonyms ("Flying" with and
  without reminder text). The IR is near-injective where it parses; the blind spots are the
  unparsed text and 13 templates annotated LOSSY or GAP.
- **Long tail.** M21 uses 151 atom types; 57 of them (38%) appear on at most 2 cards.
- **New sets.** ZNR uses 6 atom types M21 never does: BackFace, KickerAbility, HAS_KICKER,
  WAS_KICKED, QPartyCount, DISCARD. KHM's fully compiled cards add 1 (BackFace); M20's add none.
  Every fully compiled M20 card is made only of M21 atoms (107/107), which is selection bias: what
  compiles is what the grammar knows.
- **Card IR size:** median 17–26 nodes, at most 93; canonical JSON is a median of 0.8–2.1k
  characters.
- **Throughput.**
  - Engine only, RandomPolicy on both seats, one process: 1.1–1.3 games/s, 83.5 acts and 34.7 turns
    per game.
  - Model-driven: 0.25 games/s with 6 workers (/147).
  - So inference is the bottleneck, not the engine. This corrects ASSESSMENT §2.4.3, which blamed
    the engine.
- **Decks (B-45).** Each deal is a five-colour pile averaging 13.4 lands of 60 (range 7–23) and 16.6
  mana sources.
- **K3-lite** (400 RandomPolicy games): the deck with more lands wins 0.534 overall. By gap: 0.477 at
  1–2 lands (n=174), 0.536 at 3–5 (n=138), 0.839 at 6 or more (n=31). Seat 0 wins 0.551. So mana is
  not dominant under random play; my first draft's "mana screw dominates" was wrong and is
  corrected in the document.

## Red-team verdict
- **Load-bearing and unproven:**
  - F1: compositional generalization of learned encoders. SCAN, CFQ and COGS show failures on new
    combinations of known parts.
  - F2: learning atom semantics from a sparse reward.
- **The quiet killer:** F3, a game that is not Magic. Batch Magic with live rules bugs (B-43) and
  stress-pile decks.
- **Manageable with known techniques:**
  - F4: hidden information. League play, exploiters, determinized ISMCTS, the omniscient net as a
    privileged critic.
  - F5: non-transitivity. Fixed anchor panel, prioritized fictitious self-play.
  - F6: throughput. Batched GPU inference, cached card embeddings.
  - F7: credit assignment.
  - F8: numbers.
  - F9: tokenizer stability.
  - F10: coverage holes.
  - F11: combos and the trigger cap.
  - F12: evaluation leakage.
- **The strongest form of the bet:** pretrain the encoders on exact engine transitions and on
  synthetic atom compositions. That gives dense, exact semantic labels, which no MTG or Hearthstone
  learner has had. Feed the encoders IR plus the Oracle-text embedding. Put an entity transformer
  with pointer heads on top, and train with league self-play on coherent decks in a priority-correct
  engine.
- **Kill tests, cheapest first:**
  - K1: a supervised effect predictor on random, compound-divergence, M20 and KHM splits, comparing
    IR, text and hybrid encoders.
  - K2: value transfer to M20 zero-shot.
  - K3: deck validity with a trained policy.
  - K4: self-play health against a fixed panel, plus exploiters.

## Ops at the same time (15:45–16:01)
- The owner gave CED the GPU ("just start it now").
- The 27B self-play run was stopped at 15:50 with 0 pairs settled, so no data was lost.
- `docker stop qwen-nvfp4` at 15:51; the container was kept for the RL window's restore.
- The CED session (`ced-training`) runs queue A20: scoring, then round-1 training, then
  `docker start qwen-nvfp4`. It has a hard stop at 23:00.
- The local MTG agent has no model until the engine is back.

## Follow-up, same afternoon: B-45 coherent decks, and the crash they found (branch `sets/onboarding` `36adf48`)
- **The new mode.** `deal_decks(..., deck_mode="coherent")`, also bench `--deck-mode coherent`:
  two seeded colours, 24 basics, 36 cards uniform within the colour pair, at most 4 copies.
  - The default `"stress"` is byte-identical: the M21 seeds 1-5 deal hash `e9fceb12fb91e3ab`, the
    same on `main` and the branch.
  - 24 lands is a registered scaffold.
- **What it changes,** over 200 RandomPolicy M21 games each:

  | Mode | Turns per game | Acts per game | Seat 0 win rate |
  |---|---|---|---|
  | Stress | 34.5 | 78.8 | 0.531 |
  | Coherent | 28.7 | 87.0 | 0.543 |

- **It found an engine crash in 1 of 200 games.** Rise Again returned Wildwood Scourge, whose ETB
  reads X, and the engine raised `NotImplementedError` ("QX has no declared X").
  - CR 107.3b says an object that was not cast has X = 0, so `binding._ctx` now uses X = 0 for a
    permanent's own ETB when no cast X was recorded. Every other undeclared X stays loud.
  - The pack `rise_again_x_wildwood_scourge` is red without the fix, with the exact error. With it,
    the 0/0 dies to state-based actions, CR 704.5f.
  - Afterwards, 200 coherent games had 0 crashes, and the 200 stress games were identical before
    and after.
- **ZNR deals have shifted.** S-1 and S-2 compile more ZNR cards, which changes ZNR's castable pool,
  so the ZNR seed 1-5 deal hash differs from `main` (M21 is unchanged). Do not compare ZNR game
  numbers across the merge.
- **For the RL pilot:** after the merge, M21 behaviour changes only where a game used to crash. The
  re-pin must re-smoke.
