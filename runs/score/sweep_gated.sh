#!/bin/sh
# Gate for the layer sweep: the chaining test on the current homeo-score binary (all layers, backward groups of 21
# vs 13 blocks, 16 continuations = 4 gradient batches each, so the shared allocator is reused across batches); the
# per-layer G and R must be bit-identical. Then the sweep. Exposure: none.
cd /home/bepis/prog/llm-tests
O=/mnt/models/homeo/score
M=/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf
rm -f $O/gate_*
for v in 21 13; do
  ./llama.cpp/build-avx2/bin/homeo-score -m $M --ids /mnt/models/jlens/fineweb_ids.bin --out $O/gate_$v --n-prompt 1 --n-cont 16 \
    --n-par 8 --grad-batch 4 --layers all --max-group $v --windows 13-31 >> $O/gate.log 2>&1 || { echo "gate run $v failed" >> $O/gate.log; exit 1; }
done
/home/bepis/.venv/bin/python - >> $O/gate.log 2>&1 <<'PY' || { echo "GATE FAILED" >> $O/gate.log; exit 1; }
import torch, numpy as np, sys
sys.path.insert(0, '/home/bepis/prog/llm-tests/base-model-welfare/homeo')
from score_io import ScoreRun
a, b = ScoreRun('/mnt/models/homeo/score/gate_21'), ScoreRun('/mnt/models/homeo/score/gate_13')
assert a.n == b.n == 16, (a.n, b.n)
assert (np.array(a.recs['tok']) == np.array(b.recs['tok'])).all()
d = max(float(np.abs(a.G(L) - b.G(L)).max()) for L in a.layers) + max(float(np.abs(a.R(L, '13-31') - b.R(L, '13-31')).max()) for L in a.layers)
print(f'gate: max |difference| over all layers, G and R, groups 21 vs 13 (16 continuations, 4 gradient batches): {d}')
sys.exit(0 if d == 0.0 else 1)
PY
echo "gate passed; starting the sweep $(date)" >> $O/gate.log
rm -f $O/gate_*.bin
exec /home/bepis/prog/llm-tests/base-model-welfare/runs/score/sweep.sh
