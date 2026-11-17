#!/bin/bash
# soak3.sh <checkout> <tag> <games>: the soak (with the invariant) over the three dealt pools,
# CPU-only, under a memory cap. Output: soak_<tag>_<SET>.json/.log beside this script.
CK=$1
TAG=$2
N=${3:-300}
S=/tmp/claude-1000/-home-sune/53a867d9-979e-400a-9ce1-caf029cc7b16/scratchpad/guards
export CUDA_VISIBLE_DEVICES=
export OMP_NUM_THREADS=1
for code in M21 M20 FDN; do
  systemd-run --user --scope -q -p MemoryMax=16G -p MemorySwapMax=0 nice -n 19 \
    /home/sune/Desktop/MTG_AI/.venv/bin/python "$CK/tools/cards/soak.py" "$code" --games "$N" \
    --mode verified --workers 4 --out "$S/soak_${TAG}_${code}.json" > "$S/soak_${TAG}_${code}.log" 2>&1
done
echo done
