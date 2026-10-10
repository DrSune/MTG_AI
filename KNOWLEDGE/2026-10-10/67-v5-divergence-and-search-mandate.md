# 67 — v5: puzzle-acc and gameplay skill DIVERGE (35M: acc 0.839, WR 0.31 vs teacher / 0.47 vs random) + owner search mandate

Date: 2026-10-10. bc10_S4_s3_best.pt (acc 0.839) vs teacher/random, 200 games, engine pool CPU:
- vs teacher: wr 0.3105 CI[0.249,0.380] (WORSE than bc9 one-shot 0.3927); vs random: 0.4737 CI[0.404,0.545] — below/around coin flip.
- Illegal actions 0. Puzzle acc UP, gameplay WR DOWN => curated-position imitation overfits positions the game
  rarely visits and can HURT play. Outcome-meter is now a first-class gate for all future training claims.
- OWNER DIRECTION (10:17): AlphaZero-style bootstrapping. Requirements: policy = probabilities over full legal
  menu (pointer softmax — already); tree branching with values so the net doesn't get "cold feet" mid-sequence
  (scary-but-correct options need backed-up true values); expansion pruned by model top-k (branching control);
  eventual full-BPTT-rollout world acknowledged as bigger goal. Preview-crutch (outcome diffs as input) explicitly
  judged as early-training aid that must anneal out / become cheating later — distillation of search into the
  one-shot policy IS the annealing mechanism (AlphaZero law). MEASURE over theorize.
