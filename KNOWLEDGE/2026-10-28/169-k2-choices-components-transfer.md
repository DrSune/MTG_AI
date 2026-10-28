# 169 — K2: a chooser that reads components makes unseen cards' choices well; names don't (2026-10-28)

Owner, 2026-10-27/28: the bottleneck is play level. The network that plays a card must know what
its components mean, "when to choose what it can choose ... what it means to sacrifice". The
text→IR mapping is a chore for agents. Owner: "go for now, do what you need to know more, but in
the long run we use local agents for it."

So K2 asks the play-level version of K1. CPU only. Reading rules are in
`reports/k2_2026-10-28_preregistration.md`, written before any model was trained, with Amendment 1
(more games, also before training).

## Why the engine labels the choices
- The live policy reads card names, not components (`tools/training/ab_duel.py:572-578`). An unseen
  card is `<unk>`.
- Its teacher cannot teach choices. `HeuristicTeacher` (`tools/eval/gameplay_eval_v2.py:168-269`)
  takes the first option at every target, sacrifice and mode ask, and the minimum number. So BC on
  its games, even with a component-reading network, learns nothing about what components mean in a
  choice.
- `tools/k2/gen.py` makes the engine the teacher:
  - uniformly random base games go through the bench's `SeatRouter`;
  - at every target, sacrifice, discard, may, choose and one_of ask, each option is tried by replay
    (same seed and answers, this option, then do-nothing to the next clean boundary,
    `_play(stop_after=...)`);
  - the board is scored by a pre-registered probe value (life, P/T, creatures, hand, lands, tapped).
- Replays are exact. A replay that asks anything but the recorded ask raises `ReplayDivergence`
  (tested).
- Data: 18 sets, 360 games each, 9,577 decisions, of which 4,182 informative (run 1) or 4,784
  (run 2).

## Students (`tools/k2/train.py`)
All students get the board, the ask kind, and each option's object (side, zone, types, P/T, tapped,
token, or the word). They differ only in the source card:
- **none** (floor);
- **name**, an oracle-id embedding with unk-dropout (today's policy);
- **components**, the IR bag of K1/K1c.

Split: 20% of source cards are held out. Metric: top-1 accuracy, where a pick counts when it is
among the engine-best options. Intervals are paired, resampling source cards.

## Results (accuracy; chance about 0.42)
| Unseen source cards | Cards / decisions | none | name | **components** | components − name |
|---|---|---|---|---|---|
| Run 1, pre-registered | 52 / 703 | 0.748 | 0.733 | **0.818** | **+0.085 [+0.009, +0.197]** |
| Run 2, sources fixed | 63 / 815 | 0.733 | 0.709 | **0.861** | **+0.152 [+0.090, +0.235]** |

- **Run 2 fixes a recorder bug found after run 1.** Engine tags read
  `<kind>:player:N:card:M:<digest>` (`core/executor/legality.py:1505`). Taking the first handle
  gave the deciding player, so 945 target, 157 sacrifice and 334 discard asks had no source and were
  dropped. `tools/k2/repair_sources.py` recovered all 1,436 from each game's dealt setup, without
  replaying anything. `gen.py` is fixed. Run 2 is reported as decided after run 1.
- **Seeds 1–5 (exploratory, `reports/k2_2026-10-28_seeds.json`).** components − name on unseen
  cards is +0.094..+0.118 on run-1 data and +0.151..+0.167 on run-2 data. Every seed is positive.
- **Per kind, unseen sources, run 2:**

  | Kind | Decisions | none | name | components |
  |---|---|---|---|---|
  | target | 719 | 0.714 | 0.701 | 0.850 |
  | sacrifice | 52 | 0.923 | 0.904 | 0.942 |
  | may | 34 | 1.000 | 0.676 | 1.000 |
  | choose | 10 | 0.2 | 0.4 | 0.8 |

## Reading, by the pre-registered rules
1. **Sanity holds.** name − none on unseen sources: −0.016 (run 1) and −0.023 (run 2), inside
   ±0.03. No identity leaks.
2. **Components transfer.** components − none on unseen sources: +0.070 [+0.009, +0.159] (run 1)
   and +0.129 [+0.064, +0.220] (run 2). They keep 44% and 67% of their seen-card gain.
3. **Names don't transfer. This holds, with one wobble.**
   - On unseen cards, names add nothing (above).
   - On seen cards, run 1's name − none is −0.040. Across seeds it ranges −0.063..+0.123, so that
     was seed noise. Run 2 gives +0.125.
   - With row-level early stopping, which lets names memorize (exploratory), names gain +0.177 on
     seen cards and −0.026 on unseen ones.
   - So a name-reading chooser can memorize the cards it trained on and gets nothing for any other.
4. **Headline: components beat names on unseen cards by +0.085 (run 1) and +0.152 (run 2).**
5. **By kind.** Targets carry it. Sacrifice is mostly decided by the options' own P/T, so the floor
   is already 0.92. "may" breaks the name chooser on unseen cards (0.68). choose has 10 decisions.

## What this means
- **Your bet holds at the decision level.** A network that reads components makes choices for cards
  it never saw nearly as well as for cards it trained on, and a network that reads names cannot.
  That is the play-level form of "auto-extend to unseen cards made of practised primitives".
- **Components beat names even on seen cards** (+0.193 against +0.125 in run 2). Shared structure
  helps cards with few examples. That is your shared-components point, measured.
- **The engine is the teacher for choices.** K2's replay labels can supervise the real policy,
  which BC on `HeuristicTeacher` cannot.
- **Next, for the real policy** (GPU after 14:45; local agents in the long run):
  - card tokens embedded from components in `PointerBC`, replacing name words
    (`tools/training/bc_model.py:26`, `bc_data_v2.card_row_lookup`), shared by the stream and the
    pointer candidates;
  - K1's effect labels and K2's choice labels as auxiliary losses next to RL;
  - gates: name-permutation invariance, K2 on unseen cards, and a duplicate-duel swap test.
  - The RL payload is pinned, so this is built next to it and adopted at an era boundary.
  - The full design, written for the local agents who run it long term:
    `docs/PLAN_COMPONENT_TRAINING.md`.

## Caveats
- The label is a hand-made, one-turn probe value: board-good, not strategy-good.
- Discard asks are all uninformative. The board summary cannot tell which card went to the
  graveyard, so the probe cannot judge discard choices.
- X is fixed at 0 by the bench (registered scaffold), so "which volumes" is not tested yet.
- Only 63 unseen source cards. Base games are uniformly random. This is decision quality, not
  playing strength.
- Repeated CPU fits differ by about ±0.003 (multithreaded float order).

Data: `~/mtg_ai_evidence/k2_2026-10-28/` (26 MB, reproducible from `tools/k2/gen.py` at master seed
20261028). Results: `reports/k2_2026-10-28_results_run{1,2}.json`,
`reports/k2_2026-10-28_seeds.json`.
