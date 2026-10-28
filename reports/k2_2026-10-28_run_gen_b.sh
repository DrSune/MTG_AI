#!/bin/bash
# K2 data, amendment 1: games 61-360 per set, low priority.
set -u
K=/home/sune/mtg_ai_evidence/k2_2026-10-28
cd /home/sune/Desktop/MTG_AI-sets
export MTG_REPO=/home/sune/Desktop/MTG_AI-sets CUDA_VISIBLE_DEVICES=
for c in M21 ZNR M20 KHM 10E M10 M11 M12 M13 M15 ORI M19 DOM WAR ELD THB IKO FDN; do
  nice -n 19 timeout 5400 /home/sune/Desktop/MTG_AI/.venv/bin/python /home/sune/Desktop/MTG_AI/tools/k2/gen.py --set $c --games 300 --first-seed 61 --workers ${K2_WORKERS:-3} --out $K/k2_${c}_b.jsonl 2>>$K/gen_b.err | tail -1
done
echo "GEN-B-DONE $(date)"
