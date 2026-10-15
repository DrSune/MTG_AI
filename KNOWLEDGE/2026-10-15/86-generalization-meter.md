# 86 — Generalization meter v1: first unseen-CARD split of the 199-item gate — era line shows no detectable fresh-set penalty; set-level split impossible until ZNR

Date: 2026-10-15. Tool: `tools/eval/holdout_report.py` (reuses eval_side/eval_rows/
cert-join internals of eval_ckpt; no training). JSON: `tools/eval/holdout_report.json`.

## Set list + recency evidence (why FRESH-by-SET is empty)
- Integrated sets: **M21 only.** Evidence: `MTG_bot/core/golden/M21/` (305 trees, git
  add 2026-09-24); `mtg_bot.db` 397 cards, `set_code` distinct = {M21}; engine
  `SET_CODE="M21"` (executor/games.py:120) — the supply the harness can play is M21-only,
  so no scenario pack can even reference another set.
- ZNR: fetch HALTED on integrity grounds 2026-10-08 (/59); `MTG_bot/data/ZNR.json`
  re-fetched 2026-10-09 but still **git-untracked**; owner memos /81 (2026-10-14, "ZNR
  verified source still pending") and /85 (2026-10-15, R3 lists ZNR integration as
  pending). => zero eval items belong to a set younger than any train corpus;
  `--split set` verified degenerate: n_fresh = 0/199 for all three ckpts.

## CRITICAL caveat, VERIFIED (the "never in TRAIN by construction" claim is FALSE)
`eval_split.json` is family-wise (sorted card names, idx%5∈{0,1} → eval). Both era ckpts
(bc9_S3_s1, bc10_S3a_s1) train ON `episodes_v2.jsonl` itself minus the 33 eval-family
cards (reports: `gold_lines_train: 141`; train_bc_v3:419 keeps exactly the non-eval-family
gold rows). The 199-item gate = 199 gold rows of that same file joined pack-ordered
(bc_data.join_corpus asserts counts+gold match). Therefore **the 141 train-family gate
items ARE the era checkpoints' training rows, item for item** — memorization mass, not
evidence. Only the 58 eval-family items are held out. "seen/fresh" at SET level would be
about sets appearing in the train corpus — there is only one set, so the meter ships with
a card-level mode: SEEN = card had ≥1 label-eligible row in the ckpt's own train_file
under the trainer's exclusion law; FRESH = otherwise.
- bsh_S3a_s1 (shadow): train_file = `episodes_champ.jsonl` (2,424 live rows). The
  family filter is a **no-op on live rollout files** — their `card` field is an episode
  id (`champshadow-g…`), never a card name, so eval-family live asks were NOT excluded
  from shadow training. 77/80 gate card names appear verbatim as entities in bsh's
  training observations (only token names Fodder/Spare Goat/Stray Aurochs absent).
  bsh's fresh half is n=6 items — not a usable half.
- The "200k-row TRAIN corpus" figure does NOT describe the cited ckpts: bc9/bc10 trained
  141 gold lines, bsh 2,424. The 5.9x corpus (~200k-scale) belongs to the bshb line (/80).

## Results (seed 1, card-cluster bootstrap B=4000/side, SE_gap = sqrt(se_s²+se_f²))
| ckpt | regime | seen_acc (n) | fresh_acc (n) | GAP | SE_gap | CI95 |
|---|---|---|---|---|---|---|
| bc9_S3_s1   | era    | 0.7518 (141, 47 cards) | 0.7931 (58, 33 cards) | **+0.041** | 0.138 | [−0.230, +0.312] |
| bsh_S3a_s1  | shadow | 0.6528 (193, 77 cards)* | 0.3333 (6, 3 cards) | −0.320* | 0.286 | [−0.881, +0.242] |
| bc10_S3a_s1 | era    | 0.7518 (141, 47 cards) | 0.7759 (58, 33 cards) | **+0.024** | 0.143 | [−0.256, +0.305] |

Full-gate acc cross-checks: bc9 0.7638, bc10 0.7588, bsh 0.6432 (= recorded 0.643 /77 ✓
validates the join/scoring reuse).

## Verdict per regime
- **Era (bc9, bc10):** generalization score = +0.04 / +0.02, CI ±≈0.28 — **no detectable
  unseen-card penalty**: on the 58 truly held-out items both era models perform at or
  slightly above their memorization half. Caveat: n_fresh = 58 items / 33 cards → the
  meter can only exclude |gap| ≳ 0.28 today; a real −0.1 gap would hide in this noise.
- **Shadow (bsh):** no valid unseen half exists (77/80 cards exposed in live training;
  family filter no-op). Its lower gate acc (0.643) reflects a different exposure regime
  (live vocab, long obs), not a measured generalization deficit.

## What this meter becomes when ZNR lands
Owner-verified ZNR integration → `--split set --fresh-sets ZNR` gives the first TRUE
set-level generalization score (§8 tokenizer law applies at the same moment). Until then
the card split above is the honest proxy, and the shadow line's family-filter no-op is a
P1 audit item for every live-data clone.

Producer: `.venv/bin/python -m tools.eval.holdout_report --ckpts tools/training/bc9_S3_s1_best.pt,tools/training/bsh_S3a_s1_best.pt,tools/training/bc10_S3a_s1_best.pt --split card --out tools/eval/holdout_report.json` (set-mode degeneracy: same cmd `--split set`, json → /tmp/opencode/holdout_set_mode.json).
