# 78 — Digit-lane cure: implementation facts (2026-10-13, IN PROGRESS)

Per /76 §8 the numeric world-lanes are digit-tokenized: standalone numbers in
serialized obs/site streams + the `ref` referent-section of grounded candidate
spans become `dnum d#<digits…>`. Gate: env `NUMTOK=1` (default OFF keeps every
legacy gate byte-identical). Menu lane (`tokenize(cand)`, choose-index labels,
gold positions) stays literal — `tools/training/test_numlane.py` locks this.

## Stream inflation (measured 2026-10-13, NUMTOK=1)
Digit composition replaces one number token with 1+ndigits+1 words, e.g. every
handle `card:17` → `card dnum d#1 d#7`. On episodes_champ.jsonl (778 eps,
probe: flatten site_words + obs_words_v2 lengths): mean 1196, max 1443,
p99 1423; 676/778 streams exceed the old 1024 pos table. Eval
(episodes_v2.jsonl, 143 eps): max 1426, 3 over 1024. => cure runs use
`--max-len 1536` (new train_bc_v3 flag; cfg flows into ckpt config so
eval_ckpt/BcAsk rebuilds follow automatically).

## Transplant (vocab/embedding) — smoke verified
`numlane.transplant_state`: widens tok_emb (866→877, +dnum d#0..d#9; donor
row = mean d0..d9 if present else `<unk>` + N(0,0.02), seeded) AND pos_emb
(1024→1536 rows, std-0.02 init for new rows); loads strict=True; warm-start
config check tolerates ONLY vocab growth + pos-table widening. Smoke run
(8+8 eps, /tmp): epoch 0 eval_acc 0.667 (cold model ~0.1) — prior knowledge
survives transplant intact. prev-best reference 0.00340 (bsh_S3a_s1).

## Runs in flight (this session)
- `ntk_scratch_S3a_s1` (NUMTOK=1, no warm-start, max_len 1536, 60 ep, seed 1):
  started 19:36, GPU 2.9 GiB peak observed (bsh was 0.93 @1024), budget 4 GiB.
  Log /tmp/opencode/ntk_scratch.log. Scratch vocab is built WITH d-tokens from
  the stream (857 vs legacy 866 — literal-only numbers vanish from standalone
  positions).
- `ntk_S3a_s1` (transplant from bsh_S3a_s1_best.pt): chained by
  /tmp/opencode/ntk_transplant_rerun.sh (waits for ALL_DONE marker, rm's
  partial artifacts, `--fresh --warm-start`). Log ntk_transplant2.log.

## FINAL results (session died 00:23 to foreign OOM; queue2 completed 00:41; orchestrator harvest 2026-10-14):
- ntk_scratch_S3a_s1 (from-scratch, digit vocab 857, max_len 1536): vs teacher 0.4308 CI[.363,.501]; mirror vs bsh_S3a_s1 0.5053 [.435,.576] — single-run best teacher WR to date (band-top), parity vs frontier clone.
- ntk_S3a_s1 (transplant from bsh): teacher 0.3814 [.316,.452]; mirror 0.4946 [.423,.566] — transplant resumed sensibly (epoch0 0.667) but lands mid-band, no cure premium over containment.
- Frontier battle 400g: bsh_S3a_s1 vs bc9 champ 0.4649 [.416,.515] = PARITY (not decisive surpass); shadow3_gate 0.4051.
Verdict (cure-vs-containment): digit-tokenization (a) works mechanically (byte-identical legacy gates via NUMTOK=0; vocab shrinks literals 866->857), (b) gives NO measurable WR premium over live-vocab containment at this scale — the plateau (0.37-0.43 across 3 shadow gens + cure variants, all overlapping CIs) is now the story: SAMPLE-BOUND cloning, not tokenizer-bound. Next lever: collection scale (256-game gen in flight) + opponent diversity. max_len 1536 cost noted for any future era-switch adoption.
