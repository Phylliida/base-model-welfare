#!/bin/sh
# S2 steering sweep: scales are fractions of the mean residual norm at the layer
cd /home/bepis/prog/llm-tests
M=/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf
SC=-0.5,-0.25,-0.1,0.1,0.25,0.5
for spec in caa:44 probe_s:44 rand:44 caa:32; do
  v=${spec%%:*}; l=${spec##*:}
  ./llama.cpp/build-avx2/bin/homeo-steer -m $M --rollouts data/rollouts.jsonl --vec /mnt/models/homeo/s2/vec_${v}_L${l}.f32 --layer $l --scales $SC --n-rollouts 8 --out /mnt/models/homeo/s2/res_${v}_L${l}.json 2>&1 | awk '/^homeo-steer|^scale|mass/'
done
