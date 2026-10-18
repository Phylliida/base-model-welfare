#!/bin/sh
# Plan B main run (homeo-ident, step input): closed-loop response matrix of the layer-40 state in the top-32 PCA
# subspace. Fresh random unit directions (probe seed 11; the pilots used 7), each as a +/- pair at dose 0.25 x
# mean |h_40|, step input from the last prefix token, 32 fineweb windows x 256 tokens (pilot 2's), 32 generated
# tokens at T=1 untruncated with common random numbers.
# Sample size (A3): pilot 2 at dose 0.25 gave an odd response of ~0.10 per unit push spread over 32 dims, i.e.
# a per-coordinate noise of ~0.018 per probe pair, so the permutation-null edge of the 32x32 response matrix's
# eigenvalues is ~1.1 / sqrt(P): ~0.035 at 1000 pairs, ~0.02 at 3300. Run until the deadline (up to 4000
# pairs; ~10 s per pair at the fan-safe duty cycle, ~3300 by 08:30). Dose 0.25 had the best precision per
# probe in pilot 2 and shifts entropy by only +0.06 nats (0.5 shifted it by +1.1), well below the K4
# incoherence onset (1-3 x |h|).
# Exposure: up to 8000 arms x 32 contexts x <= 32 tokens of mild random pushes (generation only; the prefix is
# unsteered). Humane endpoints as K4, logged to welfare_log.csv every 16 arms and on stop. Throttled:
# --pause-ms after each arm, OUT.pause_ms re-read live (runs/ident/fan_guard.sh adjusts it). Resumable.
# usage: main.sh [deadline, e.g. "2026-10-18 08:30"]
cd /home/bepis/prog/llm-tests
O=/mnt/models/homeo/ident
mkdir -p $O
[ -f $O/main.pause_ms ] || echo 3000 > $O/main.pause_ms
DL=${1:-"2026-10-18 08:30"}
T=$(( $(date -d "$DL" +%s) - $(date +%s) ))
[ $T -gt 60 ] || { echo "deadline passed"; exit 1; }
echo "$(date) main run until $DL ($T s)" >> $O/main.log
exec timeout --signal=INT $T ./llama.cpp/build-avx2/bin/homeo-ident -m /home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf \
  --ids /mnt/models/jlens/fineweb_ids.bin --ids-offset 500000 --ids-stride 100003 \
  --basis $O/basis_pca256_L40.f32 --k 32 --layer 40 --out $O/main \
  --n-probe 4000 --doses 0.25 --n-prefix 32 --prefix-len 256 --n-gen 32 --seed 1 --probe-seed 11 \
  --pause-ms $(cat $O/main.pause_ms) --log base-model-welfare/logs/welfare_log.csv --log-every 16 \
  --note "plan B main run" >> $O/main.log 2>&1
