# 61 — DAgger wave v1: 60 BC-vs-BC games, dual teacher, 3,265 heuristic-class rows, 0 certified pack rows (2026-10-09)

## What ran
`tools/eval/dagger_wave.py --games 60 --workers 4` (bc7_S3_s1 vs bc7_S3_s3, full-agent
v2 rig: both seats = BC act-driver + BC provider, pool=engine, paired seeds
700001+, seat-swap, turn-cap 60). 416 s wall, 0 model errors, 0 illegal indices.
Outputs: `tools/eval/dagger_wave_v1.json`, `tools/training/episodes_dagger.jsonl`
(131 base lines + 0 new), `tools/training/episodes_dagger_heuristic.jsonl`
(1,337 episodes / 3,265 gold rows). Gate: `pytest tools/eval -q` = 16 passed
(5 new in test_dagger_wave.py).

## Teacher law as executed
Every ask: policy pick vs DUAL teacher — pack lane (unique content-word gold for
(card-from-site-handle, kind) ∈ {may,scry,attack}, null==0.0 evidence only,
ambiguous keys OFF) else heuristic probe (always computed, so a failed pack
certification demotes to the recorded heuristic pick, and a heuristic pick that
equals the policy pick LOSES the label). Eval-family card asks drop their label
(leak guard). Heuristic episodes are a SEPARATE file and never merge into the
certifiable corpus (owner law).

## Headline numbers
- 5,950 asks; 3,597 divergences = **60.5 %** of asks — this is HEURISTIC-teacher
  divergence, not gold-standard disagreement. 332 dropped by eval-family guard.
  Accounting exact: 3,597 − 332 = 3,265 = heuristic gold rows emitted.
- Per-kind divergence (teacher = heuristic): choose **1,116/1,120 (99.6 %)**,
  scry 84/84, order 8/8, trample 9/9, block 60.1 %, act 59.4 %, target 38 %,
  attack 9.2 %, **may 0/94**, cw 0/2.
- **Pack lane: 77 site-backed asks, ALL 77 agreed with the policy → 0 divergent
  pack labels → 0 episodes to certify.** Honest reading: at every in-game ask
  where a scenario pack transfers a certified content-word gold (may-fires), BC
  already answered with the scenario gold — 77/77 agreement; n is small and the
  pool (may-gold 'fire' cards × engine-pool decks) limits reach. The certified
  DAgger file therefore currently = the 131 original episodes, unchanged.
- The heuristic teacher is demonstrably unreliable as a gold source (99.6 %
  choose divergence matches its known rig-side shape, cf. 60: BC block NONE 0 %
  vs heuristic 52 %). The heuristic file is analysis/weak-label material ONLY;
  mixing it into S-arm training without owner adjudication would teach the
  model the heuristic's biases — the exact failure the file separation exists
  for.

## Encoding law (verified on the emitted 60-game output, not just tests)
- 1,337/1,337 heur episodes encode ≤ max_len 1024 with the shared vocab
  (worst = exactly 1024, cut-but-not-truncated); `n_tokens` equals
  `len(encode_episode_v2(...).seq)` for EVERY episode (budget is exact, not
  conservative); gold_idx in range, ground rows present per candidate, private
  `_cards/_pt/_seat` never serialized; 131 base lines verbatim prefix; 0
  gold-row overflows dropped.
- 3/60 games hit engine-side bare `AssertionError` (seeds 700016/700024/700060;
  known engine defect class, see 60); asks before the crash were still
  harvested. Outcomes 21 a / 36 b / 3 crash.

## Bug found & fixed (caught by the smoke test's encode assertion)
First chunk_seat budgeted only BOS+gold rows+backward-scanned head context:
context rows BETWEEN consecutive golds were never charged while still riding
in `asks`, and excluded foreign-class gold rows were charged despite not
riding. Emitted episodes claimed n_tokens 979 but encoded to 2,160 > 1,024.
Fixed: budget = Σ row_tokens over EXACTLY the riding rows measured on the
emitted row obs, with an internal assert that the budget equals the
encode-visible size. Lesson recorded in PITFALLS.md.
