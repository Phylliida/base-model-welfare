#!/bin/sh
# Value lens scenario set 2 (VL4): model-written fiction (36 prompts), boring prose (36) and structured text
# (24), 2 continuations each, through homeo-value. Tests whether stakes orders the group's scenarios when every
# group is model-written (set 1 compared model-written fiction with human fineweb text).
# Sample size (A3): 192 windows x 127 positions. Set 1's window-level stakes sd was about 0.05, so 72 vs 72
# windows resolve a group difference of about 0.025 (2 SE); prompts are the unit for the test (36 vs 36).
# Unsteered generation at T=1 and gradients only: no exposure. Throttled (--pause-ms, llama-server pauses).
set -e
cd /home/bepis/prog/llm-tests
M=/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf
S=/mnt/models/homeo/value_scen2
if [ ! -f $S/manifest.json ]; then
  ~/.venv/bin/python base-model-welfare/homeo/value_scenarios2_prep.py --out $S
fi
N=$(~/.venv/bin/python -c "import json; print(len(json.load(open('$S/manifest.json'))))")
[ -f $S/out/pause_ms ] || { mkdir -p $S/out; echo 450 > $S/out/pause_ms; }
./llama.cpp/build-avx2/bin/homeo-value -m $M --ids $S/scenario_ids.bin --stride 192 --n-windows $N --out $S/out \
  --n-tokens 192 --skip 32 --horizon 32 --short 8 --layer 40 --read 44,50,56 --pause-ms 450 >> $S/run.log 2>&1
tail -n 1 $S/run.log | awk '/finished/ {ok=1} END {exit !ok}'
echo "scenario set 2 done $(date)"
