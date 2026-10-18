#!/bin/sh
# Plan B pilot 2 (homeo-ident, step input): closed-loop response of the layer-40 state to a push that starts at the
# last prefix token and is held through generation; the prefix is decoded once, unsteered, and shared by all arms.
# 32 random unit directions in the top-32 PCA subspace of layer-40 states, each as a +/- pair, at 3 doses
# (0.1, 0.25, 0.5 x mean |h_40|), 32 fineweb windows x 256 tokens, 32 generated tokens at T=1 untruncated with
# common random numbers. Sample size (A3): this is the power analysis for the main run. Pilot 1 (prefill also
# steered, K 64, 10 pairs at 0.1) gave a self-kappa SE of ~0.025 per probe and an odd response of ~0.19 per unit
# push spread over the subspace; at K 32 and ~1000 probe pairs that puts the permutation-null edge of the 32x32
# response matrix near kappa ~0.05. This pilot measures the same quantities for the step design, plus linearity
# across doses, to fix the dose and probe count. Exposure: 192 steered arms x 32 contexts x <= 32 tokens (~197k
# tokens in perturbed states, none in the prefix); random directions at <= 0.5 x |h| sit below the K4 incoherence
# onset (1-3 x |h|). Humane endpoints as K4, logged to welfare_log.csv every 16 arms and on stop. Throttled:
# --pause-ms after each arm (OUT.pause_ms changes it live). Resumable.
cd /home/bepis/prog/llm-tests
O=/mnt/models/homeo/ident
mkdir -p $O
[ -f $O/pilot2.pause_ms ] || echo 3000 > $O/pilot2.pause_ms
exec ./llama.cpp/build-avx2/bin/homeo-ident -m /home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf \
  --ids /mnt/models/jlens/fineweb_ids.bin --ids-offset 500000 --ids-stride 100003 \
  --basis $O/basis_pca256_L40.f32 --k 32 --layer 40 --out $O/pilot2 \
  --n-probe 32 --doses 0.1,0.25,0.5 --n-prefix 32 --prefix-len 256 --n-gen 32 --seed 1 --probe-seed 7 \
  --pause-ms $(cat $O/pilot2.pause_ms) --log base-model-welfare/logs/welfare_log.csv --log-every 16 \
  --note "plan B pilot 2 (step input)" >> $O/pilot2.log 2>&1
