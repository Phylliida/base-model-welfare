#!/bin/bash
# Start the lens server and the loom in the background (logs and pids in serve/logs), wait until both answer.
set -e
source "$(dirname "$0")/config.sh"
mkdir -p "$SV/logs"
busy() { ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$1\$"; }
if busy "$LENS_PORT"; then echo "port $LENS_PORT is in use (lens server already running?)"; else
  nohup bash "$SV/lens_server.sh" > "$SV/logs/lens_server.log" 2>&1 & echo $! > "$SV/logs/lens_server.pid"
  echo -n "lens server starting on :$LENS_PORT (model load ~1 min)"
  for i in $(seq 200); do sleep 3; curl -s -m 2 "http://127.0.0.1:$LENS_PORT/health" | grep -q ok && break; echo -n .; done; echo
  curl -s -m 2 "http://127.0.0.1:$LENS_PORT/health" | grep -q ok || { echo "lens server did not come up; see $SV/logs/lens_server.log"; exit 1; }
fi
if busy "$LOOM_PORT"; then echo "port $LOOM_PORT is in use (loom already running?)"; else
  nohup bash "$SV/loom.sh" > "$SV/logs/loom.log" 2>&1 & echo $! > "$SV/logs/loom.pid"
  for i in $(seq 30); do sleep 1; curl -s -m 2 -o /dev/null "http://127.0.0.1:$LOOM_PORT/" && break; done
fi
H=$(hostname)
echo "loom:        http://$H:$LOOM_PORT/   (or http://localhost:$LOOM_PORT/)"
echo "lens server: http://$H:$LENS_PORT    (in the loom: settings -> llama url = http://<this host>:$LENS_PORT/completion, then tick 'value' or 'lens')"
