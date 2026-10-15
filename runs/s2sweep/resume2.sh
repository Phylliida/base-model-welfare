#!/bin/sh
# resume the S2(c) layer sweep: run only layers missing from each band's JSON (outputs go to *_rN prefixes)
cd /home/bepis/prog/llm-tests
M=/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf
D=/mnt/models/homeo/s2sweep
B=./llama.cpp/build-avx2/bin/homeo-steeropt
OPT="--accum 4 --lr-frac 0.006 --steps 60 --eval-every 30"
PY=~/.venv/bin/python
missing() { # band, wanted layer list -> comma list of layers not yet in any $D/p<band>*.json
  $PY - "$1" "$2" <<'PYEOF'
import glob, json, sys
band, want = sys.argv[1], [int(x) for x in sys.argv[2].split(',')]
done = set()
for f in glob.glob(f'/mnt/models/homeo/s2sweep/p{band}*.json'):
    try:
        done |= {L['layer'] for L in json.load(open(f)).get('layers', [])}
    except Exception:
        pass
print(','.join(str(x) for x in want if x not in done))
PYEOF
}
run_band() { # band, wanted layers
  todo=$(missing "$1" "$2")
  [ -z "$todo" ] && { echo "#### band $1: complete"; return; }
  n=1; while [ -e "$D/p$1_r$n.json" ]; do n=$((n+1)); done
  echo "#### band $1: layers $todo -> p$1_r$n"
  $B -m $M --rollouts data/rollouts.jsonl $OPT --band $1 --layers $todo --out $D/p$1_r$n 2>&1 | tee -a $D/raw_resume2.log | awk '/^test|^==|^  test/'
}
run_band 0.25 "$(seq -s, 0 60)"
run_band 0.1  "$(seq -s, 0 60)"
run_band 0.5  "$(seq -s, 0 4 60)"
run_band 0.03 "$(seq -s, 0 4 60)"
