#!/bin/bash
# Seeds for 7,000 rollouts and 2,333 natural windows (75% / 25%; each 70% English, 15% Chinese, 15% nine languages;
# lengths log-uniform in [160, 2048]). The order below reproduces the original files exactly: the run started with
# 5,000 + 1,667 and was extended twice by 1,000 + 333 (each extension draws from unused documents with its own seed).
# Needs a llama-server for tokenization (started here if none answers on $GEN_PORT).
set -e
source "$(dirname "$0")/../config.sh"
cd "$REPO"
U=http://127.0.0.1:$GEN_PORT
if ! curl -s -m 2 $U/health | grep -q ok; then
  nohup "$LLAMA_BIN/llama-server" -m "$MODEL" -ngl 99 -c 66560 -np 32 --port $GEN_PORT --host 127.0.0.1 --no-webui > "$SEQS/server_tokenize.log" 2>&1 &
  for i in $(seq 100); do sleep 3; curl -s -m 2 $U/health | grep -q ok && break; done
fi
mkdir -p "$SEQS"
G="python3 homeo/gen_rollouts_ml.py"
$G jobs "$SEQS" --n 5000 --server $U
$G pretrain "$SEQS" --n-pretrain 1667 --server $U
$G jobs "$SEQS" --append --n 1000 --server $U
$G pretrain "$SEQS" --append --n-pretrain 333 --server $U
$G jobs "$SEQS" --append --n 1000 --server $U
$G pretrain "$SEQS" --append --n-pretrain 333 --server $U
wc -l "$SEQS/jobs.jsonl" "$SEQS/pretrain.jsonl"
