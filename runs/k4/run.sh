#!/bin/sh
# K4 loop margin, first run (NOTES-homeostasis.md K4; Three Rs protocol: endpoints + ladder stop, logged)
# needs the whole GPU: refuses to start while the S2(c) sweep is running
if pgrep -x homeo-steeropt >/dev/null || pgrep -x resume.sh >/dev/null; then echo "sweep still running, not starting"; exit 1; fi
cd /home/bepis/prog/llm-tests
M=/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf
D=/mnt/models/homeo/k4
B=./llama.cpp/build-avx2/bin/homeo-loop
LOG=/home/bepis/prog/llm-tests/welfare_log.csv
OPT="--rollouts data/rollouts.jsonl --n-prefix 16 --prefix-len 256 --n-gen 128 --random 4 --neg --doses 0.25,0.5,0.75,1,1.5,2,3 --log $LOG"
$B -m $M $OPT --layer 44 --out $D/k4_L44.jsonl --note "K4 first run" \
  --vecs /mnt/models/homeo/s2/vec_caa_L44.f32,/mnt/models/homeo/s2/vec_probe_s_L44.f32,/mnt/models/homeo/s2/vec_rand_L44.f32 \
  2>&1 | awk '/^homeo-loop|^  /' | tee $D/k4_L44.log
$B -m $M $OPT --layer 40 --out $D/k4_L40.jsonl --note "K4 first run" \
  --vecs /mnt/models/homeo/s2opt/vec_temp1.3_opt2_L40.f32,/mnt/models/homeo/s2opt/vec_p0.25_opt2_L40.f32 \
  2>&1 | awk '/^homeo-loop|^  /' | tee $D/k4_L40.log
~/.venv/bin/python homeo/k4_loop_summary.py $D/k4_L44.jsonl $D/k4_L40.jsonl --json $D/k4_summary.json | tee $D/k4_summary.txt
