#!/bin/sh
# Value lens, first full run (the Value Lens proposal; NOTES-homeostasis.md "Value lens").
# Teacher-forced real text (fineweb ids), no steering: per position now / short (k<=8) / fut (k<=32) price
# vectors at layers 40 (slot), 44, 50, 56. Resumable: rerun this script to continue after an interruption.
# Sample size (A3): 1200 windows x 127 positions = 152k positions, enough to estimate the leading directions
# of the 6144-d price covariance and to split by window for the split-half check (H1); ~25 h at 75 s/window,
# ~22 GB. No candidate-aversive manipulation (gradients only).
cd /home/bepis/prog/llm-tests
./llama.cpp/build-avx2/bin/homeo-value -m /home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf \
  --ids /mnt/models/jlens/fineweb_ids.bin --out /mnt/models/homeo/value --n-windows 1200 \
  --n-tokens 192 --skip 32 --horizon 32 --short 8 --layer 40 --read 44,50,56 --seed 0 --pause-ms 250
