# 21 — Owner ruling (17:25): volume caveat on capacity; model-range measuring; BPTT cap visibility

1. **Capacity verdict downgraded** from "CONFIRMED" to *measured-under-current-volume*:
   169K > 35M held (+3.21 vs +2.60 SE), but 75 train items over few cards/scenarios is a
   biased sample — the corpus favours simple cases. Do NOT write off bigger models. Standing
   law: every batch reports the **ratio trio** — params : gold lines : median seq_len — so the
   model-range-vs-data-volume curve keeps accumulating. (batch2: 35.1M : 119 : 111 =
   295k params/line; batch3-B: 169k : 75 : 111 = 2.3k params/line.)
2. **Model-range sweep queued (batch 5)**: {0.17M, 0.66M, 2.5M, 10M, 35M} on identical data,
   seed, and gates — engine-off. Re-run whenever the corpus materially grows (same driver).
3. **BPTT cap law**: truncation at max_len must be measurable and never silent. Verified
   TODAY: bc_model.encode() RAISES past max_len (never clips) — so all historical reports are
   honest; longest sequence ever observed = 1008 vs cap 1024 (16-token headroom — ladder work
   WILL hit this). Shipped: _seq_stats now emits over_limit + cap_headroom; train_bc_v3
   aborts BEFORE training when over_limit>0 on train or eval split, with the extend-max_len
   instruction; pinned by test (67 passed). When the abort fires: lengthen max_len (pos_emb
   takes it; it is a config value), do not shorten rollouts.
