#!/bin/sh
# S2(c) layer sweep: one optimized vector per layer; temperature positive control first
cd /home/bepis/prog/llm-tests
M=/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf
D=/mnt/models/homeo/s2sweep
B=./llama.cpp/build-avx2/bin/homeo-steeropt
OPT="--accum 4 --lr-frac 0.006 --steps 60 --eval-every 30"
ALL=$(seq -s, 0 60)
EVERY4=$(seq -s, 0 4 60)
$B -m $M --rollouts data/rollouts.jsonl $OPT --target-temp 1.3 --layers 0,10,20,30,40,50,60 --out $D/temp1.3 2>&1 | awk '/^test|^==|^  test/'
for P in 0.25 0.1; do
  echo "#### band $P"
  $B -m $M --rollouts data/rollouts.jsonl $OPT --band $P --layers $ALL --out $D/p$P 2>&1 | awk '/^test|^==|^  test/'
done
for P in 0.5 0.03; do
  echo "#### band $P"
  $B -m $M --rollouts data/rollouts.jsonl $OPT --band $P --layers $EVERY4 --out $D/p$P 2>&1 | awk '/^test|^==|^  test/'
done
