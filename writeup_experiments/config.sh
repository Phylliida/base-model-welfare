# Paths for the writeup experiments. Edit for your machine; every step script sources this file.
# Defaults are the original machine's (GLM-4-32B-Base Q4_K_S on one RTX 3090, 64 cores, ~1 TB RAM).
WX=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
export REPO=${REPO:-$(cd "$WX/.." && pwd)}
export R=${R:-$(cd "$REPO/.." && pwd)}                    # parent of the repo (runs/rollprobe/run.sh uses $R/base-model-welfare)
export B=$REPO
export MODEL=${MODEL:-/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf}
export LLAMA_BIN=${LLAMA_BIN:-$R/llama.cpp/build-avx2/bin}  # llama-server + homeo-capture from the llama.cpp fork (branch homeostasis)
export GEN_PORT=${GEN_PORT:-8056}                          # llama-server port for generation / tokenization

# inputs (step 01 downloads them)
export FINEWEB=${FINEWEB:-$R/data/fineweb_000.parquet}     # HuggingFaceFW/fineweb sample/10BT/000_00000.parquet (2.1 GB)
export FINEWEB2_DIR=${FINEWEB2_DIR:-$R/data/fineweb2}      # HuggingFaceFW/fineweb-2 test splits, 10 languages (~750 MB)

# outputs
export SEQS=${SEQS:-/mnt/models/homeo/rollouts2}           # seeds, rollouts, natural windows, probe sites, logs (~220 MB)
export ACTS=${ACTS:-/data2/homeo/rollprobe_acts}           # captured activations, all 61 layers at the probe sites (~150 GB);
                                                           # use a RAM disk (e.g. /dev/shm/rollprobe) for a fresh run: the fit reads it many times
export PROBES=${PROBES:-/mnt/models/homeo/rollprobe}       # fitted probes, predictions, results
export KERNELS=${KERNELS:-/dev/shm/rollprobe_kernels}      # saved kernel matrices for new targets (~128 GB, RAM disk)
export VALUE_SCEN=${VALUE_SCEN:-/mnt/models/homeo/value_scen}  # value-lens scenario run (Table 1)
export RESULTS=${RESULTS:-$WX/results}                     # numbers, tables and figures for the writeup
