#!/bin/bash
# 7 chunks, each: generate 1,000 rollouts (pure ancestral sampling, temperature-only sampler chain, duty-cycled to keep
# the GPU fan near 45%), then capture all 61 block outputs at the probe sites of those rollouts and 333 natural windows.
# Original run: ~2 h per chunk on one RTX 3090 (~14 h). Restartable: chunks already captured are skipped.
set -e
source "$(dirname "$0")/../config.sh"
cd "$REPO"
mkdir -p "$ACTS"
DEADLINE=${DEADLINE:-$(date -d '+7 days' +%s)} NCHUNK=7 NO_FIT=1 sh runs/rollprobe/run.sh
