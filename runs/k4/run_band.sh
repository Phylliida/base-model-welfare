#!/bin/sh
# K4b: loop margin under multi-layer steering (the user's setup: one direction added after every block in a band).
# Does band steering produce loops (state collapse, period-1 spam) where single-layer steering gave incoherence?
# Sample size (A3): 16 prefixes x <=128 tokens, as in K4, so the two runs compare directly; K4 resolved
# loop/incoherence fractions to 1/16, enough to locate a margin within one dose step.
# Doses start low: teacher-forced S2(d) showed 0.25 x |h_32| per layer over 24..40 already destroys the output
# (E[-ln p] 14-23 nats, argmax agreement < 5%), so the informative range is ~0.01-0.25 per layer.
# Dose unit: mean |h| at layer 24, added after every block 24..40. Same endpoints, ladder stop and log as K4.
if pgrep -x homeo-steeropt >/dev/null || pgrep -x homeo-steer >/dev/null || pgrep -x homeo-loop >/dev/null; then echo "GPU busy, not starting"; exit 1; fi
cd /home/bepis/prog/llm-tests
M=/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf
D=/mnt/models/homeo/k4
./llama.cpp/build-avx2/bin/homeo-loop -m $M --rollouts data/rollouts.jsonl --n-prefix 16 --prefix-len 256 --n-gen 128 \
  --layer 24 --layer-end 40 --random 4 --neg --vecs /mnt/models/homeo/s2/vec_caa_L32.f32 --doses 0.01,0.02,0.05,0.1,0.25,0.5 --stop-any 2 \
  --log /home/bepis/prog/llm-tests/welfare_log.csv --note "K4b band 24-40" --out $D/k4b_band24-40.jsonl \
  2>&1 | awk '/^homeo-loop|^  /' | tee $D/k4b.log
~/.venv/bin/python homeo/k4_loop_summary.py $D/k4b_band24-40.jsonl --json $D/k4b_summary.json | tee $D/k4b_summary.txt
