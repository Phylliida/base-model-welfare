#!/bin/sh
# Value lens follow-up, after runs/value/run.sh finishes: Antra's scenarios (loops, fiction), then the analyses.
# Sample size (A3): 16 loop pairs x 2 loop types + 12 fiction windows = 44 windows (~1 h). Paired loop windows
# share their first 96 tokens with main-run windows 0-15, so 16 pairs resolve a loop-vs-control difference in
# stakes far larger than the window-to-window spread. Fiction is unsteered generation at T=1 (no exposure).
# Every step's exit status is checked (no pipelines hide failures).
set -e
cd /home/bepis/prog/llm-tests
M=/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf
S=/mnt/models/homeo/value_scen
V=/mnt/models/homeo/value
cmake --build llama.cpp/build-avx2 --target homeo-value -j 48 > /dev/null
rm -rf $S/out   # a re-run of the prep must not resume stale windows against a new manifest
~/.venv/bin/python homeo/value_scenarios_prep.py --out $S
N=$(~/.venv/bin/python -c "import json; print(len(json.load(open('$S/manifest.json'))))")
./llama.cpp/build-avx2/bin/homeo-value -m $M --ids $S/scenario_ids.bin --stride 192 --n-windows $N --out $S/out \
  --n-tokens 192 --skip 32 --horizon 32 --short 8 --layer 40 --read 44,50,56 > $S/run.log 2>&1
tail -n 1 $S/run.log | awk '/finished/ {ok=1} END {exit !ok}'
~/.venv/bin/python homeo/value_lens.py $V --json $V/summary.json --examples 4 > $V/summary.txt 2>&1
~/.venv/bin/python homeo/value_lens.py $V --clean --json $V/summary_clean.json --examples 4 > $V/summary_clean.txt 2>&1
~/.venv/bin/python homeo/value_scenarios.py > $S/summary.txt 2>&1
echo "value lens follow-up done $(date)"
