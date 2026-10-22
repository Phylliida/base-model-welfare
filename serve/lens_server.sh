#!/bin/bash
# llama-server with the J-lens and every probe the loom shows: --value-probe (layer-40 readouts), --probe-dirs (183
# regulated directions, steering via /steer with an exposure log), --lin-probes (22 all-layer probes: difficulty
# forecasts, past difficulty, decoded text statistics). Foreground; serve/up.sh runs it in the background.
set -e
source "$(dirname "$0")/config.sh"
if [ ! -f "$LIN_PROBES.f32" ]; then
  echo "building the all-layer probe bundle -> $LIN_PROBES.{f32,json}"
  python3 "$REPO/homeo/lin_probes_export.py" --dir "$REPO/probes/rollout" --out "$(dirname "$LIN_PROBES")"
fi
for f in "$MODEL" "$JLENS" "$VALUE_PROBE.f32" "$PROBE_DIRS.f32" "$LIN_PROBES.f32" "$LLAMA_BIN/llama-server"; do
  [ -e "$f" ] || { echo "missing: $f (edit serve/config.sh)"; exit 1; }
done
exec "$LLAMA_BIN/llama-server" -m "$MODEL" -ngl 99 -c "$LENS_CTX" --host "$LENS_HOST" --port "$LENS_PORT" \
  --jlens "$JLENS" --value-probe "$VALUE_PROBE" --probe-dirs "$PROBE_DIRS" --lin-probes "$LIN_PROBES" \
  --steer-log "$STEER_LOG" -ot token_embd.weight=CUDA0
