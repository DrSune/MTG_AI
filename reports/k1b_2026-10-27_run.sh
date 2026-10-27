#!/bin/bash
# K1b volume curve, run A (all castable rows) then run B (fully compiled cards only). CPU only.
set -u
K=/home/sune/mtg_ai_evidence/k1_2026-10-27
cd /home/sune/Desktop/MTG_AI-sets
export MTG_REPO=/home/sune/Desktop/MTG_AI-sets TORCH_DISABLE_NATIVE_JIT=1 CUDA_VISIBLE_DEVICES=
PY=/home/sune/Desktop/MTG_AI/.venv/bin/python
CURVE=/home/sune/Desktop/MTG_AI/tools/k1/curve.py
echo "A start $(date)"
timeout 3000 $PY $CURVE --data $K --cap 60 --epochs 15 --out $K/k1b_curve_A.json > $K/k1b_A.log 2>&1
echo "A exit=$? $(date)"
timeout 2400 $PY $CURVE --data $K --cap 60 --epochs 15 --fully-compiled --out $K/k1b_curve_B.json > $K/k1b_B.log 2>&1
echo "B exit=$? $(date)"
