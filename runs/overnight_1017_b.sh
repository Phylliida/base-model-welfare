#!/bin/sh
# Reallocation of the 2026-10-17 overnight queue (runs/overnight_1017.sh, PID given as $1).
# The queue's step 4 (VL4 second continuations, 96 windows at about 150 s each) only got 14:30-16:30. This
# ends step 3 (lean) as soon as it starts, so step 4 runs right after step 2, then lets the post-queue loom
# readout check run, then continues the lean test (resumable, same sample-size line in runs/lean/run.sh)
# until 16:10 so the GPU is idle by 16:30.
cd /home/bepis/prog/llm-tests
Q=$1
LOG=logs/overnight_1017.log
until awk '/step 3/ {f=1} END {exit !f}' $LOG; do sleep 30; done
sleep 10
P=$(ps -o pid=,args= --ppid $Q | awk '/timeout/ && /lean\/run.sh/ {print $1}')
echo "$(date) step 3 started; its timeout pid: '$P'"
[ -n "$P" ] && kill -INT $P
while kill -0 $Q 2>/dev/null; do sleep 60; done
echo "$(date) queue ended"
# the readout check (another waiter) starts when the queue ends; give it up to 40 minutes
sleep 60
i=0
while ps -eo args= | awk '/value_readout_check.py/ && !/awk/ {f=1} END {exit !f}' && [ $i -lt 40 ]; do sleep 60; i=$((i+1)); done
echo "$(date) readout check finished (or 40 min passed)"
T=$(( $(date -d "2026-10-17 16:10" +%s) - $(date +%s) ))
echo "$(date) lean continues for $T s"
[ $T -gt 300 ] && timeout --signal=INT $T base-model-welfare/runs/lean/run.sh
echo "$(date) lean done; GPU idle"
