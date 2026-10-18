#!/bin/sh
# Keep the GPU fan near or below 45% during a throttled run: every 60 s, if the fan was above 45% for the last 3
# samples, lengthen the pause in $1 (a homeo-ident OUT.pause_ms file) by 1000 ms (up to 15000); if it was below 38%
# for the last 10 samples, shorten it by 500 ms (down to 2000). Stops when process $2 exits.
F=$1; P=$2; hi=0; lo=0
while kill -0 $P 2>/dev/null; do
  sleep 60
  fan=$(nvidia-smi --query-gpu=fan.speed --format=csv,noheader,nounits | tr -d ' ')
  cur=$(cat $F)
  if [ "$fan" -gt 45 ]; then hi=$((hi + 1)); lo=0; elif [ "$fan" -lt 38 ]; then lo=$((lo + 1)); hi=0; else hi=0; lo=0; fi
  if [ $hi -ge 3 ] && [ $cur -lt 15000 ]; then echo $((cur + 1000)) > $F; hi=0; echo "$(date +%T) fan $fan%: pause $cur -> $((cur + 1000)) ms"; fi
  if [ $lo -ge 10 ] && [ $cur -gt 2000 ]; then echo $((cur - 500)) > $F; lo=0; echo "$(date +%T) fan $fan%: pause $cur -> $((cur - 500)) ms"; fi
done
echo "$(date +%T) run ended"
