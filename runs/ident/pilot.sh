#!/bin/sh
# STOPPED after 25 arms (2026-10-17 22:20): replaced by pilot2.sh (step input, prefix unsteered and shared).
# Plan B pilot (homeo-ident): closed-loop response of the layer-40 state to sustained pushes, through the tokens.
# 32 random unit directions in the top-64 PCA subspace of layer-40 states, each as a +/- pair, at 3 doses
# (0.1, 0.25, 0.5 x mean |h_40|), 16 held-out prefixes x 256 tokens, 32 generated tokens at T=1 untruncated with
# common random numbers. Sample size (A3): this is the power analysis for the main run. It measures, per dose,
# how often the tokens diverge, the size of the odd response against its probe-to-probe spread (self-kappa SE),
# and the even (nonlinear) part, to choose the dose and the number of probes the main run needs to fit the
# 64x64 response matrix above its permutation null. Exposure: 192 steered arms x 16 contexts x <= 32 tokens
# (~98k tokens in perturbed states, prefill also steered); random directions at <= 0.5 x |h| sit below the K4
# incoherence onset (1-3 x |h|). Humane endpoints as K4 (loop / incoherence stop a sequence), every 32 arms
# logged to welfare_log.csv. Throttled: --pause-ms after each arm (OUT.pause_ms changes it live). Resumable.
cd /home/bepis/prog/llm-tests
O=/mnt/models/homeo/ident
mkdir -p $O
[ -f $O/pilot.pause_ms ] || echo 1500 > $O/pilot.pause_ms
exec ./llama.cpp/build-avx2/bin/homeo-ident -m /home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf \
  --rollouts /mnt/models/jlens/rollouts.jsonl --basis $O/basis_pca256_L40.f32 --k 64 --layer 40 --out $O/pilot \
  --n-probe 32 --doses 0.1,0.25,0.5 --n-prefix 16 --prefix-len 256 --n-gen 32 --seed 1 --probe-seed 7 \
  --pause-ms $(cat $O/pilot.pause_ms) --log base-model-welfare/logs/welfare_log.csv --log-every 32 \
  --note "plan B pilot" >> $O/pilot.log 2>&1
