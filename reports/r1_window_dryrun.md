
## R1 window run — 2026-10-19 22:27:08 (dry-run=1, HEAD 2864fd1)

Commands (exact): per seed /home/sune/Desktop/MTG_AI/.venv/bin/python run_train.py --phase r1-r1_S4_s<N> --timeout 7200 --ignore-prev -- /home/sune/Desktop/MTG_AI/.venv/bin/python -m tools.training.train_bc_v3 --arm S4 --seed <N> --prefix r1_S4_s<N> --episodes /home/sune/Desktop/MTG_AI/tools/training/episodes_champ_big.jsonl --fresh; then eval_ckpt.py <best.pt> --device cpu; /128 patched meter (--split set --fresh-sets ZNR); ab_duel.py --a <best.pt> --b /home/sune/Desktop/MTG_AI/tools/training/bsh_S3a_s3_best.pt --workers 4 --device cpu --seed-file /home/sune/Desktop/MTG_AI/reports/monitoring/duel_seeds.json

| lane | subject | result | gate/CI | extra |
|---|---|---|---|---|
| gate | r1_smoke_best.pt | acc=0.6231 | verdict=None | beat_SE=None | n_cert=199 note=periodic best-train-loss checkpoint (pre-final) |
| train | S0 (r1_smoke_report.json) | cause=dry-smoke best_epoch=1 wall_s=150.9 device=cpu | acc(eval-fam)=0.7069 | gate=PASS margin_SE=6.39 | vocab=866 head=unknown |
