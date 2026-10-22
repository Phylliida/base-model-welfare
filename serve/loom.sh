#!/bin/bash
# The loom web UI (loom/loom_server.py, Flask) with the probe metadata from the repo. Foreground.
set -e
source "$(dirname "$0")/config.sh"
[ -f "$LOOM_DIR/loom_server.py" ] || { echo "no loom in $LOOM_DIR: run 'git submodule update --init loom' (or set LOOM_DIR)"; exit 1; }
# metadata for the color menu (names, readings, color scales); the weights themselves are in the lens server
export LOOM_VALUE_READOUT="$VALUE_PROBE.json" LOOM_PROBE_DIRS="$PROBE_DIRS.json" LOOM_LIN_PROBES="$LIN_PROBES.json" LOOM_TOKEN_STATS="$TOKEN_STATS" LOOM_PROBE_PATTERNS="$PROBE_PATTERNS"
[ -f "$LOOM_LIN_PROBES" ] || python3 "$REPO/homeo/lin_probes_export.py" --dir "$REPO/probes/rollout" --out "$(dirname "$LIN_PROBES")"
cd "$LOOM_DIR"
exec python3 -m flask --app loom_server run --host "$LOOM_HOST" --port "$LOOM_PORT"
