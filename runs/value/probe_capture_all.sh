#!/bin/sh
# All-layer value probe: every block output (layers 0-60) on the 1200 VL1 fineweb windows, same positions as
# probe_capture.sh (skip 32, 192 tokens), for linear probes on all layers jointly (homeo/value_probe_all.py).
# Full f16 states are about 144 GB, so they go to RAM (/dev/shm), not disk. Forward passes only: no exposure.
set -e
R=/home/bepis/prog/llm-tests
M=/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf
O=${1:-/dev/shm/vlprobe_all}
mkdir -p $O
$R/llama.cpp/build-avx2/bin/homeo-capture -m $M --rollouts /mnt/models/homeo/value_probe/main/rollouts.jsonl --out $O \
  --layers $(seq -s, 0 60) --stride 1 --skip 32 --n-forced 0 --max-len 192 --ubatch 192 --pause-ms ${PAUSE_MS:-150}
echo "all-layer value probe capture done $(date)"
