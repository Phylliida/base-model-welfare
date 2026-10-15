#!/bin/sh
# S2(c) sweep: temperature positive control + one optimized vector per band at L40, exact eval for each
cd /home/bepis/prog/llm-tests
M=/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf
D=/mnt/models/homeo/s2opt
OPT="--layer 40 --accum 4 --lr 0.02 --steps 200 --eval-every 50"
./llama.cpp/build-avx2/bin/homeo-steeropt -m $M --rollouts data/rollouts.jsonl $OPT --target-temp 1.3 --out $D/vec_temp1.3_opt2_L40.f32 2>&1 | awk '/^test|^  /'
for P in 0.25 0.1 0.5 0.03; do
  echo "== band $P"
  ./llama.cpp/build-avx2/bin/homeo-steeropt -m $M --rollouts data/rollouts.jsonl $OPT --band $P --out $D/vec_p${P}_opt2_L40.f32 2>&1 | awk '/^test|^  /'
  ./llama.cpp/build-avx2/bin/homeo-steer -m $M --rollouts data/rollouts.jsonl --vec $D/vec_p${P}_opt2_L40.f32 --layer 40 \
    --scales -1,0.5,1,2 --levels 0.8,0.5,0.25,0.1,0.03,0.01 --n-rollouts 8 --out $D/res_vec_p${P}_opt2_L40.json 2>&1 | awk '/^homeo-steer: baseline/'
done
