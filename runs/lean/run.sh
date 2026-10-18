#!/bin/sh
# H3 lean test (Value Lens proposal): at 6 positions per window of held-out fineweb text, the model's top 8
# candidate next tokens, each continued 4 times for 16 steps at T=1 untruncated (common random numbers).
# Sample size (A3): up to 4000 windows x 6 positions; a run cut by the deadline still gives >= ~15k positions
# with the actual token in the top 8, so the lean coefficient b has a bootstrap SE of roughly 0.05 per nat of
# future entropy (from the smoke test's within-position spread of V); the synthetic gate measures attenuation
# from rollout noise on the same data. No steering: the model's own top candidates and plain samples, so no
# exposure. Throttled: --pause-ms per decode (OUT.pause_ms can change it live). Resumable.
cd /home/bepis/prog/llm-tests
O=/mnt/models/homeo/lean
mkdir -p $O
[ -f $O/lean.jsonl.pause_ms ] || echo 60 > $O/lean.jsonl.pause_ms
exec ./llama.cpp/build-avx2/bin/homeo-lean -m /home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf \
  --ids /mnt/models/jlens/fineweb_ids.bin --out $O/lean.jsonl --n-windows 4000 --n-tokens 170 --pos-start 48 \
  --pos-step 24 --n-cand 8 --n-roll 4 --horizon 16 --seed 7 --pause-ms $(cat $O/lean.jsonl.pause_ms) >> $O/run.log 2>&1
