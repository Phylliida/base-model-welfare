#!/bin/bash
# Every number, table and figure of the writeup, from the fitted probes (minutes, CPU only) -> $RESULTS
set -e
source "$(dirname "$0")/../config.sh"
cd "$WX"
mkdir -p "$RESULTS"
python3 analysis/difficulty_table.py
python3 analysis/baseline_ladder.py
python3 analysis/layer_figures.py
python3 analysis/past_difficulty.py
python3 analysis/data_composition.py
python3 analysis/probe_cosine.py
ls -la "$RESULTS"
