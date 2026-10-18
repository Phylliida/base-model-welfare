#!/bin/sh
# Value probe (VL2): layer-40 activations on the value-lens windows, for linear probes h -> value readouts.
# Sample size (A3): reuses the 1200 VL1 fineweb windows + 44 scenario windows (127 positions each; probes
# are fit on windows 0-899 and tested on 900-1199). Forward passes only, no steering: no exposure.
set -e
R=/home/bepis/prog/llm-tests
M=/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf
O=/mnt/models/homeo/value_probe
for d in main scen; do
  $R/llama.cpp/build-avx2/bin/homeo-capture -m $M --rollouts $O/$d/rollouts.jsonl --out $O/$d \
    --layers 40 --stride 1 --skip 32 --n-forced 0 --max-len 192 --ubatch 192
done
echo "value probe capture done $(date)"
