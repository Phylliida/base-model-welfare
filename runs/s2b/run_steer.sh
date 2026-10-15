#!/bin/sh
# S2b steering eval: band vectors at L40, scales = fraction of mean residual norm
cd /home/bepis/prog/llm-tests
M=/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf
D=/mnt/models/homeo/s2b
for v in p0.5_normal p0.25_normal p0.1_normal p0.03_normal p0.5_bracket p0.25_bracket p0.1_bracket p0.03_bracket; do
  ./llama.cpp/build-avx2/bin/homeo-steer -m $M --rollouts data/rollouts.jsonl --vec $D/vec_${v}_L40.f32 --layer 40 \
    --scales -0.2,0.05,0.1,0.2,0.4 --levels 0.8,0.5,0.25,0.1,0.03,0.01 --n-rollouts 8 --out $D/res_vec_${v}_L40.json 2>&1 | awk '/^homeo-steer: baseline/'
done
