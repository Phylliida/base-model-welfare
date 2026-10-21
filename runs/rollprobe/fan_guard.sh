#!/bin/sh
# Keep the GPU fan near 45% during a homeo-capture run: every 30 s read the fan; after 3 readings above 45% lengthen the
# per-sequence pause in $1 (a homeo-capture OUT/pause_ms file) by 400 ms (up to 8000); after 10 readings below 39%
# shorten it by 200 ms (down to 0). Stops when process $2 exits.
F=$1; P=$2; hi=0; lo=0
while kill -0 $P 2>/dev/null; do
  sleep 30
  fan=$(nvidia-smi --query-gpu=fan.speed --format=csv,noheader,nounits | tr -d ' ')
  cur=$(cat $F 2>/dev/null || echo 0)
  if [ "$fan" -gt 45 ]; then hi=$((hi + 1)); lo=0; elif [ "$fan" -lt 39 ]; then lo=$((lo + 1)); hi=0; else hi=0; lo=0; fi
  if [ $hi -ge 3 ] && [ $cur -lt 8000 ]; then echo $((cur + 400)) > $F; hi=0; echo "$(date +%T) fan $fan%: pause $cur -> $((cur + 400)) ms"; fi
  if [ $lo -ge 10 ] && [ $cur -gt 0 ]; then n=$((cur - 200)); [ $n -lt 0 ] && n=0; echo $n > $F; lo=0; echo "$(date +%T) fan $fan%: pause $cur -> $n ms"; fi
done
echo "$(date +%T) run ended"
