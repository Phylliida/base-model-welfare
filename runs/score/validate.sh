#!/bin/sh
# Plan B2 step 2 (homeo-score): validate the score-function estimator against the plan B main run.
# The main run's 32 prompts (fineweb windows, offset 500000, stride 100003, 256 tokens) x 320 unpushed
# continuations of 32 tokens at T=1, untruncated; per continuation G (summed gradient of the written tokens'
# log-likelihood at the block-40 output over lags 0-31) and the block-40 readout averaged over lags 1-4, 5-12
# and 13-31, as full 6144-dim vectors (analysis: homeo/score_fit.py).
# Sample size (A3): the proposal's theory (sigma 0.020 |h|, I_F ~105, calibration c = 3.0) predicts a null edge
# of about +-0.05 for the 32x32 matrix at ~10,000 sequences, enough to see the main run's strongest directions
# (+0.14 sentence progress, -0.17 register). Exposure: none (no pushes; ordinary sampling plus gradients).
# Checks done before this run (homeo-score --check): recompute bit-identical; G within the model's layout noise
# floor of jlens_value_exact (cos 0.992-0.997); per-token log p within 0.01 nats of llama.cpp.
# Throttled: --pause-ms after each batch of 32, OUT.pause_ms re-read live (runs/ident/fan_guard.sh). Resumable.
cd /home/bepis/prog/llm-tests
O=/mnt/models/homeo/score
mkdir -p $O
[ -f $O/val.pause_ms ] || echo 3000 > $O/val.pause_ms
exec ./llama.cpp/build-avx2/bin/homeo-score -m /home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf \
  --ids /mnt/models/jlens/fineweb_ids.bin --ids-offset 500000 --ids-stride 100003 --out $O/val \
  --layer 40 --n-prompt 32 --prefix-len 256 --n-gen 32 --n-cont 320 --n-par 32 --grad-batch 4 \
  --windows 1-4,5-12,13-31 --seed 1 --pause-ms $(cat $O/val.pause_ms) >> $O/val.log 2>&1
