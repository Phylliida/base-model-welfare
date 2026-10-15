#!/bin/sh
# S2(c): optimize one steering vector per probability band at L40, then evaluate it exactly
cd /home/bepis/prog/llm-tests
M=/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf
D=/mnt/models/homeo/s2opt
for P in 0.25 0.1 0.5 0.03; do
  ./llama.cpp/build-avx2/bin/homeo-steeropt -m $M --rollouts data/rollouts.jsonl --layer 40 --band $P --out $D/vec_p${P}_opt_L40.f32 2>&1 | awk '/^homeo-steeropt|^test|^step|^  test|error|fail|abort/'
  ./llama.cpp/build-avx2/bin/homeo-steer -m $M --rollouts data/rollouts.jsonl --vec $D/vec_p${P}_opt_L40.f32 --layer 40 \
    --scales -1,0.5,1,1.5 --levels 0.8,0.5,0.25,0.1,0.03,0.01 --n-rollouts 8 --out $D/res_vec_p${P}_opt_L40.json 2>&1 | awk '/^homeo-steer: baseline/'
done
