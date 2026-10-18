#!/bin/sh
# Overnight queue, 2026-10-17 (user away until ~17:00; GPU idle by 16:30). Throttled for fan noise.
# Each step is resumable and cut by a deadline (timeout); rerunning a step's command continues it.
#   1. H3 lean test (runs/lean/run.sh has the sample-size line) until 04:30: early data for the gate
#   2. VL4: value lens on scenario set 2, first continuation of each prompt (96 windows; runs/value/scen2.sh)
#   3. lean test continues until 14:30
#   4. VL4 second continuations until 16:30
cd /home/bepis/prog/llm-tests
M=/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf
S=/mnt/models/homeo/value_scen2
until_ts() { echo $(( $(date -d "$1" +%s) - $(date +%s) )); }
VAL="./llama.cpp/build-avx2/bin/homeo-value -m $M --ids $S/scenario_ids.bin --stride 192 --out $S/out --n-tokens 192 --skip 32 --horizon 32 --short 8 --layer 40 --read 44,50,56"
mkdir -p $S/out; [ -f $S/out/pause_ms ] || echo 450 > $S/out/pause_ms
T=$(until_ts "2026-10-17 04:30"); echo "step 1 (lean) $(date), $T s"
[ $T -gt 300 ] && timeout --signal=INT $T base-model-welfare/runs/lean/run.sh
T=$(until_ts "2026-10-17 14:00"); echo "step 2 (VL4 first 96) $(date), $T s"
[ $T -gt 300 ] && timeout --signal=INT $T $VAL --n-windows 96 --pause-ms $(cat $S/out/pause_ms) >> $S/run.log 2>&1
T=$(until_ts "2026-10-17 14:30"); echo "step 3 (lean) $(date), $T s"
[ $T -gt 300 ] && timeout --signal=INT $T base-model-welfare/runs/lean/run.sh
T=$(until_ts "2026-10-17 16:30"); echo "step 4 (VL4 rest) $(date), $T s"
[ $T -gt 300 ] && timeout --signal=INT $T $VAL --n-windows 192 --pause-ms $(cat $S/out/pause_ms) >> $S/run.log 2>&1
echo "queue done $(date)"
