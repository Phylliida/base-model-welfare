#!/bin/sh
# Plan B2, sensor side at every layer: what each layer's regulated directions track in ordinary text.
# homeo-capture over the same 1,200 FineWeb rollouts as the layer-40 value probe (value_probe/main: 192 tokens each,
# positions 32-191, 192,000 positions), all 61 layers. Per position and layer: the block output projected on that
# layer's top-64 capacity basis (sweep.L{L}.capbasis.f32; every sweep.describe_cap64 direction lies in it) plus 14
# fixed directions (sense/extra.f32: the screen's layer-40 directions and the probing directions), and |h|.
# Checked on 3 rollouts: layer 40 matches the stored acts_L40.f16 projected offline (corr 0.9999998, the difference
# is their f16 rounding); tokens, entropy and surprisal identical. Exposure: none (forward passes over natural text).
# Throttled: DIR/pause_ms is re-read after every rollout (runs/ident/fan_guard.sh).
cd /home/bepis/prog/llm-tests
O=/mnt/models/homeo/score
[ -f $O/sense/pause_ms ] || echo 0 > $O/sense/pause_ms
exec ./llama.cpp/build-avx2/bin/homeo-capture -m /home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf \
  --rollouts /mnt/models/homeo/value_probe/main/rollouts.jsonl --out $O/sense --layers $(seq -s, 0 60) \
  --stride 1 --skip 32 --n-forced 0 --max-len 192 --seed 1 \
  --proj "$O/sweep.L{L}.capbasis.f32" --proj-k 64 --proj-extra $O/sense/extra.f32 >> $O/sense.log 2>&1
