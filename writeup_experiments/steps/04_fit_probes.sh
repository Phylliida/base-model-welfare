#!/bin/bash
# All probes. GPU for the kernel products (stop other GPU jobs first), CPU for the solves; ~4 h + ~1 h + 2 x ~1 h + 0.5 h.
set -e
source "$(dirname "$0")/../config.sh"
cd "$REPO"
mkdir -p "$PROBES"
F="--acts $ACTS --seqs $SEQS --out $PROBES"
# 1. future difficulty (next 1 / 8 / 32 / 128, added 32 / 128): all-layer probe with strength chosen on val, per-layer
#    profile, fixed-strength forecast-change reliability -> rollprobe.{json,txt}, rollprobe_weights.f32, rollprobe_rows.npz
python3 homeo/rollprobe_fit.py $F > "$PROBES/fit.log" 2>&1
# 2. the same at strength 100 (reliable forecast change), saving the kernels for the new targets below
python3 homeo/rollprobe_fit.py $F --lams 100 --tag _l100 --no-layers --no-reliability --save-kernels "$KERNELS" > "$PROBES/fit_l100.log" 2>&1
# 3. past difficulty and decoded text statistics from the saved kernels (solves only)
python3 homeo/rollprobe_refit.py --kernels "$KERNELS" --rows "$PROBES/rollprobe_rows.npz" --acts "$ACTS" --out "$PROBES" --targets past > "$PROBES/fit_past.log" 2>&1
python3 homeo/rollprobe_refit.py --kernels "$KERNELS" --rows "$PROBES/rollprobe_rows.npz" --acts "$ACTS" --out "$PROBES" --targets baseline > "$PROBES/fit_baseline.log" 2>&1
# 4. per-layer profile of the past and decoded targets (CPU)
python3 homeo/rollprobe_layers.py --rows "$PROBES/rollprobe_rows.npz" --acts "$ACTS" --kernels "$KERNELS" --out "$PROBES" > "$PROBES/fit_layers_more.log" 2>&1
# 5. forecast change / TD error analysis
python3 homeo/rollprobe_td.py --out "$PROBES" --meta "$SEQS" > "$PROBES/td.log" 2>&1
# 6. the bundle for llama-server --lin-probes (loom)
python3 homeo/lin_probes_export.py --dir "$PROBES"
