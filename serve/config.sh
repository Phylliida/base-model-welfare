# Hosting the loom with the lens server. Edit for your machine; serve/*.sh source this file.
SV=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
export REPO=${REPO:-$(cd "$SV/.." && pwd)}
export MODEL=${MODEL:-/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf}   # GLM-4-32B-Base-32K Q4_K_S
export LLAMA_BIN=${LLAMA_BIN:-$REPO/../llama.cpp/build-avx2/bin}  # llama-server from the fork (submodule llama.cpp, branch homeostasis)
export JLENS=${JLENS:-/mnt/models/jlens/rlens_rollout_mixed.jlns} # J-lens matrices (9.2 GB; backup in /data2/homeo/artifacts/jlens)
export LENS_HOST=${LENS_HOST:-0.0.0.0}
export LENS_PORT=${LENS_PORT:-8056}
export LENS_CTX=${LENS_CTX:-4096}
export LOOM_DIR=${LOOM_DIR:-$REPO/loom}                          # submodule: Phylliida/minloomwebui, branch value-lens
export LOOM_HOST=${LOOM_HOST:-0.0.0.0}
export LOOM_PORT=${LOOM_PORT:-5000}
export STEER_LOG=${STEER_LOG:-$REPO/logs/welfare_log.csv}        # exposure log for steering from the loom (Three Rs protocol)
# probe files, all in the repo (probes/); the all-layer bundle is built into serve/build on first start
export VALUE_PROBE=${VALUE_PROBE:-$REPO/probes/value_lens/readout_L40}
export PROBE_DIRS=${PROBE_DIRS:-$REPO/probes/directions/score/probe_dirs}
export LIN_PROBES=${LIN_PROBES:-$SV/build/lin_probes}
export TOKEN_STATS=${TOKEN_STATS:-$REPO/probes/value_lens/token_stats_fineweb.json}
