# 10 — Training Batch 1: BC floor test (2026-10-05)

Deliverables: `tools/training/{packrec,bc_data,bc_model,train_bc,test_bc}.py`,
`episodes.jsonl`, `bc_s1.pt`, `bc_report.json`. Head f58675c. No engine edits.

## Verdict: PASS — schema + loop validated, proceed to batch 2

`.venv/bin/python -m tools.training.train_bc --device cuda` (239 s wall):

| slice | rows | acc | vs random (floor) | vs null (floor) |
|---|---|---|---|---|
| gold_lines_all | 119 | 0.8235 | **+7.10 SE** (0.4979) | **+8.50 SE** (0.437) |
| train_items | 98 | 0.9388 | +8.53 SE | +9.75 SE |
| l1_certified | 4 | 1.000 | +5.87 SE (0.0287) | +6.05 SE |
| holdout_items | 21 | 0.2857 | **−1.53 SE** | −0.90 SE |

Gate = gold_lines_all beats BOTH cert floors by >3 SE one-sided binomial.
PASS confirmed at p_one_sided ≈ 2e-11 (vs random). **Honest caveat:** the
holdout pack-slice is *below* floor — 119 lines memorize, they do not
generalize to unseen packs. Expected at this scale; batch-2 curriculum volume
is the designated fix. l1_certified (the packs where inaction is punished)
goes 4/4.

Model: PointerBC d=512 L=8 heads=8 ff=3072, **35,086,338 params**, grad
checkpointing, dropout 0, bf16 autocast. **GPU peak 1.37 GiB < 4.0 GiB
budget** (S1 coexist window holds). AdamW 3e-4 wd 0.01, batch 24, full
250-epoch cosine cycle, best train loss 0.2254 @ ep204, seed 1.

Gates: `pytest tools/training -q` 17 passed; `pytest MTG_bot/core -q` 2386
passed + 2 subtests (unchanged); ruff Δ0; pyright 0 errors.

## Measured counts vs batch-0 claims
133/355 packs carry scripted decisions → 96 produce menu-style asks →
**119 gold decision lines**, join to `puzzle_corpus.json` 119/119 zero
mismatch (ordinal-collapse fixed: identity-based gold matching in packrec).
The design doc's "~121" is superseded by 119 (4 packs duplicate-item, 2 ask
families non-menu).

## Schema honesty — candidate grounding
- Handle-vocab candidates (`card:17`) bind lexically to handle-canonical obs
  rows in **80.1% (133/166)** of word occurrences; all 4 l1 packs bind 100%.
- Gap = referents in **unenumerated zones** (library/hand-hidden): cultivate,
  see_the_truth×3, garruk_s_harbinger×3, waker_of_waves. Batch-2 fix:
  enumerate asked-zone candidates into obs, or gate on the grounded subset.
- Index-vocab asks (`choose:card` candidates "0"/"1") have **no referent
  surface in obs at all** — the model can only learn per-pack priors there;
  batch 2 must materialize the choice set into the observation.

## Batch-1 bug ledger (each cost a diagnostic run — see PITFALLS.md)
1. `nn.ModuleList(block for _ in range(L))` with a block built ONCE outside =
   one instance L times: silent weight-tying, 5.5M params not 35M. Loss
   plateaued at 0.67, verdict NULL. Fixed via fresh factory call per block.
2. Plateau rule `min(curve[-patience:]) > best-1e-3` self-fires at
   len(curve)==patience because best sits inside its own window. Replaced by
   `epoch - best_epoch >= patience`.
3. `obs_error: CardState has no attribute 'name'` on 127/138 asks → card
   rows are `state.identity.name`; obs now carries handle-canonical rows
   (`str(handle)` == candidate token form).
4. lr 1e-3 bounced loss (0.53→0.67) and plateau-fired pre-anneal at ep73
   (2.89 SE, NULL by a hair); 3e-4 / 250-epoch cosine converges to PASS.
