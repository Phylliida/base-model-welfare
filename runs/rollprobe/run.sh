#!/bin/sh
# Overnight rollout probe (notes: "Plan for the overnight run"): up to NCHUNK (7) chunks, each 1000 pure ancestral rollouts
# (homeo/gen_rollouts_ml.py, llama-server on :8056) + 333 natural windows, then all 61 block outputs at the probe sites
# (homeo/rollprobe_sites.py -> homeo-capture, f16 in RAM under /dev/shm/rollprobe/cK). Chunks alternate generation and
# capture on the one GPU, so whatever is done by the deadline is a complete, representative sample. A chunk starts
# only if the previous chunk's duration still fits before DEADLINE (default 10:15 tomorrow; the user starts at 13:00,
# the fit takes ~2.5 h). Then the fit (CPU).
# Sample size: 7000 rollouts + 2333 natural windows (~215k rows) if all chunks finish; the probe needs ~100k training
# rows to match the VL1 all-layer fit. Exposure: none (unsteered sampling and forward passes).
# usage: run.sh [GEN0_PID]   (GEN0_PID: an already running generator for chunk 0 to wait for)
R=/home/bepis/prog/llm-tests
B=$R/base-model-welfare
M=/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf
O=/mnt/models/homeo/rollouts2
S=/dev/shm/rollprobe
DEADLINE=${DEADLINE:-$(date -d 'tomorrow 10:15' +%s)}
NCHUNK=${NCHUNK:-7}
cd $B
log() { echo "$(date '+%F %T') $*"; }
server_pid() { ss -ltnp | command grep -F ':8056 ' | sed -E 's/.*pid=([0-9]+).*/\1/' | head -1; }
start_server() {
  [ -n "$(server_pid)" ] && return
  nohup $R/llama.cpp/build-avx2/bin/llama-server -m $M -ngl 99 -c 66560 -np 32 --port 8056 --host 127.0.0.1 --no-webui \
    >> $O/server_gen.log 2>&1 &
  for i in $(seq 100); do sleep 3; curl -s -m 2 localhost:8056/health | command grep -q ok && break; done
  log "server up"
}
stop_server() {
  p=$(server_pid); [ -z "$p" ] && return
  kill $p; while kill -0 $p 2>/dev/null; do sleep 1; done; sleep 2; log "server stopped"
}
mkdir -p $S
if [ -n "$1" ]; then log "waiting for chunk-0 generator $1"; while kill -0 $1 2>/dev/null; do sleep 30; done; fi
last=0
for k in $(seq 0 $((NCHUNK - 1))); do
  [ -f $S/c$k/meta.json ] && { log "chunk $k already captured"; continue; }
  t0=$(date +%s)
  if [ $k -gt 0 ] && [ $((t0 + last)) -gt $DEADLINE ]; then log "chunk $k would end after the deadline (last chunk took $last s); stopping"; break; fi
  start_server
  for try in 1 2 3; do
    python3 homeo/gen_rollouts_ml.py run $O --from $((1000 * k)) --to $((1000 * (k + 1))) >> $O/gen_c$k.log 2>&1 && break
    log "generator chunk $k failed (try $try)"; stop_server; start_server
  done
  stop_server
  python3 homeo/rollprobe_sites.py $k --out $O --n-chunks $NCHUNK >> $O/sites.log 2>&1 || { log "sites chunk $k failed"; break; }
  mkdir -p $S/c$k; echo 600 > $S/c$k/pause_ms
  $R/llama.cpp/build-avx2/bin/homeo-capture -m $M --rollouts $O/capture_c$k.jsonl --out $S/c$k --layers $(seq -s, 0 60) \
    --n-forced 0 --max-len 2048 --ubatch 512 --pause-ms 600 > $O/capture_c$k.log 2>&1 &
  cp=$!
  sh runs/rollprobe/fan_guard.sh $S/c$k/pause_ms $cp >> $O/capture_fan_guard.log 2>&1 &
  wait $cp || { log "capture chunk $k failed"; break; }
  last=$(( $(date +%s) - t0 ))
  log "chunk $k done in $last s: $(tail -1 $O/sites.log)"
done
log "GPU phase done"
if python3 homeo/rollprobe_fit.py > $O/fit.log 2>&1; then log "fit done"
else log "GPU fit failed, refitting on the CPU"; python3 homeo/rollprobe_fit.py --device cpu > $O/fit_cpu.log 2>&1 && log "fit done (CPU)"; fi
