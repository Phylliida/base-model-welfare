#!/bin/sh
# Plan B2 steps 3-4 (homeo-score): full-space capacity basis and closed-loop screen on fresh prompts.
# 160 fresh FineWeb windows of 256 tokens (runs/score/screen_offsets.txt: random offsets, none within 64 tokens of
# any window used before, i.e. pilot 2, the probing main run, validation, the value lens and the lean test) x 320
# unpushed continuations of 32 tokens at T=1, untruncated. Per continuation the full 6144-dim G and readouts
# (lags 1-4, 5-12, 13-31), so the analysis can work in any basis:
#   - homeo/score_capbasis.py: greedy capacity basis of the full space on half the prompts, capacities and the
#     AM-GM certificate on the remainder evaluated on the other half (25,600 samples per half, ~4x n_embd);
#   - homeo/score_fit.py: the response matrix in the capacity basis (and in the PCA bases), split halves.
# Sample size (A3): null edges measured on the first 2,880 validation samples (lags 13-31) were +-0.088 at K 128,
# +-0.111 at K 256 and +-0.32 in the full space, scaling as 1/sqrt(n): at 51,200 samples about +-0.021, +-0.026 and
# +-0.076. Exposure: none (no pushes; ordinary sampling plus gradients).
# Throttled: --pause-ms after each batch of 32, OUT.pause_ms re-read live (runs/ident/fan_guard.sh). Resumable.
cd /home/bepis/prog/llm-tests
O=/mnt/models/homeo/score
mkdir -p $O
[ -f $O/screen.pause_ms ] || cp $O/val.pause_ms $O/screen.pause_ms 2>/dev/null || echo 4000 > $O/screen.pause_ms
exec ./llama.cpp/build-avx2/bin/homeo-score -m /home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf \
  --ids /mnt/models/jlens/fineweb_ids.bin --offsets base-model-welfare/runs/score/screen_offsets.txt --out $O/screen \
  --layer 40 --prefix-len 256 --n-gen 32 --n-cont 320 --n-par 32 --grad-batch 4 \
  --windows 1-4,5-12,13-31 --seed 2 --pause-ms $(cat $O/screen.pause_ms) >> $O/screen.log 2>&1
