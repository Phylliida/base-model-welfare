#!/bin/bash
# Stop what serve/up.sh started (by pid file).
source "$(dirname "$0")/config.sh"
for n in loom lens_server; do
  f="$SV/logs/$n.pid"
  [ -f "$f" ] || continue
  p=$(cat "$f")
  pkill -P "$p" 2>/dev/null; kill "$p" 2>/dev/null && echo "stopped $n ($p)"
  rm -f "$f"
done
