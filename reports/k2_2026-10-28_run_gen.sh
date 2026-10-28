#!/bin/bash
# K2 data: engine-labelled choices, 60 games per set, CPU only, low priority (RL window running).
set -u
K=/home/sune/mtg_ai_evidence/k2_2026-10-28
cd /home/sune/Desktop/MTG_AI-sets
export MTG_REPO=/home/sune/Desktop/MTG_AI-sets CUDA_VISIBLE_DEVICES=
for c in M21 ZNR M20 KHM 10E M10 M11 M12 M13 M15 ORI M19 DOM WAR ELD THB IKO FDN; do
  nice -n 19 timeout 3600 /home/sune/Desktop/MTG_AI/.venv/bin/python /home/sune/Desktop/MTG_AI/tools/k2/gen.py --set $c --games 60 --workers ${K2_WORKERS:-3} --out $K/k2_$c.jsonl 2>>$K/gen.err | tail -1
done
echo "GEN-DONE $(date)"
