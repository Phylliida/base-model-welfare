#!/bin/sh
# Plan B2 layer sweep (homeo-score --layers all): the score-function response matrix and loop capacity at every
# layer. 64 fresh FineWeb windows of 256 tokens (runs/score/sweep_offsets.txt; none within 64 tokens of any window
# used before, the screen's included) x 160 unpushed continuations of 32 tokens at T=1, untruncated. Per
# continuation and layer L = 0..60: G_L (summed gradient of the written tokens' log-likelihood for a push after
# block L over lags 0-31) and R_L (mean block-L output over lags 13-31), f16, 1.5 MB per continuation (~15 GB).
# Sample size (A3): at layer 40 the validation run gave a null edge of +-0.028 for K 32 at 10,240 continuations
# (+-0.05 predicted for K 128 from the partial-data scaling); the sweep is a first map across layers at that
# precision, to pick layers for screen-size runs. Exposure: none (no pushes; ordinary sampling plus gradients).
# Backward in chained groups of 21 blocks (bit-identical to other group sizes; layer 40 matches the single-layer
# path to f16 rounding). Throttled: --pause-ms after each batch, OUT.pause_ms re-read live. Resumable.
cd /home/bepis/prog/llm-tests
O=/mnt/models/homeo/score
[ -f $O/sweep.pause_ms ] || cp $O/screen.pause_ms $O/sweep.pause_ms 2>/dev/null || echo 7000 > $O/sweep.pause_ms
exec ./llama.cpp/build-avx2/bin/homeo-score -m /home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf \
  --ids /mnt/models/jlens/fineweb_ids.bin --offsets base-model-welfare/runs/score/sweep_offsets.txt --out $O/sweep \
  --layers all --max-group 21 --prefix-len 256 --n-gen 32 --n-cont 160 --n-par 32 --grad-batch 4 \
  --windows 13-31 --seed 3 --pause-ms $(cat $O/sweep.pause_ms) >> $O/sweep.log 2>&1
