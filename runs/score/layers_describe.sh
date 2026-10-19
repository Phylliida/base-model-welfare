#!/bin/sh
# Plan B2: the layer-40 analysis at every layer of the sweep (no GPU model run; CPU + GPU linear algebra only).
# Per layer: a 128-direction capacity basis from that layer's 10,240 continuations (homeo/score_capbasis.py
# --basis-only, on the GPU, a 15 s pause between layers to keep the fan down), then homeo/score_describe.py in its top
# 64 directions at every layer in one process: spectrum, null, split halves, the top 3 pushed-back / amplified
# directions with their effector readout, J-lens decode and the cosine with the screen's layer-40 directions.
cd /home/bepis/prog/llm-tests/base-model-welfare
O=/mnt/models/homeo/score
for L in $(seq 0 60); do
  [ -f $O/sweep.L$L.capbasis.f32 ] && continue
  nice -n 10 /home/bepis/.venv/bin/python homeo/score_capbasis.py $O/sweep --layer $L --basis-only --gpu --n-basis 128 >> $O/sweep.capbasis_layers.log 2>&1
  sleep 15
done
nice -n 10 /home/bepis/.venv/bin/python homeo/score_describe.py $O/sweep --basis "$O/sweep.L{L}.capbasis.f32" --k 64 --layers 0-60 --tag cap64 > $O/sweep.describe_cap64.log 2>&1
