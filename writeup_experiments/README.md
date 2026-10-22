# Writeup experiments: difficulty prediction ("Base Model Wellbeing")

Everything needed to reproduce the numbers, tables and figures of the difficulty-prediction writeup, from raw data to
LaTeX. The heavy lifting is done by scripts elsewhere in the repo (`homeo/`, `runs/`, the llama.cpp fork); this folder
lays out the order, the paths, and one small script per writeup result.

```
config.sh                      all paths (model, binaries, data, outputs); edit this first
steps/01_download_data.sh      FineWeb shard + FineWeb-2 test splits (~3 GB)
steps/02_make_sequences.sh     seeds of 7,000 rollouts + 2,333 natural windows (exactly the original files)
steps/03_generate_and_capture.sh   generate the rollouts, capture all 61 layers at the probe sites (~14 h on one 3090)
steps/04_fit_probes.sh         all probes (~7 h; GPU for kernel products, CPU for the solves)
steps/05_make_results.sh       every writeup number / table / figure into results/ (minutes)
analysis/                      the scripts behind step 05, one per result
results/                       their output from the original run (committed)
```

To regenerate the writeup's results from the data that already exists on the original machine, run only step 05.

## Requirements

- GLM-4-32B-Base-32K, Q4_K_S (`GLM-4-32B-Base-32K.i1-Q4_K_S.gguf`), one 24 GB GPU.
- The llama.cpp fork in `../llama.cpp` (branch `homeostasis`), built with CUDA:
  `cmake --build build --target llama-server homeo-capture -j`. `llama-server` serves generation and tokenization;
  `homeo-capture` records block outputs and per-token surprisal / entropy.
- Python with PyTorch (CUDA) and NumPy, pyarrow. RAM: the fit holds a 149k x 149k kernel (89 GB) and its factor at
  once (~400 GB peak); activations are ~150 GB (best on a RAM disk while fitting).

## Which script makes which result

| writeup | produced by | inputs |
|---|---|---|
| Table 1 (difficulty of kinds of text) | `analysis/difficulty_table.py` -> `results/difficulty_table.tex` | the value-lens scenario run: `runs/value/run.sh` (1,200 FineWeb windows, ~25 h) then `runs/value/followup.sh` (scenario windows: loops, fiction, FineWeb tenths; `homeo/value_scenarios.py` writes `summary.txt`) |
| Tables 2-3 (baseline ladder, next 32 / 128) and the probe / baseline / combined percentages | `analysis/baseline_ladder.py` -> `results/baseline_ladder.{tex,txt}` | step 04 (`rollprobe_rows.npz`, `rollprobe.json`) + the labels in `$ACTS` |
| Figure: single-layer R2 by layer, future difficulty | `analysis/layer_figures.py` -> `results/fig_future_layers.tex` | `rollprobe.json` (per-layer profile of step 04.1) |
| Figure: single-layer R2 by layer, past difficulty | `analysis/layer_figures.py` -> `results/fig_past_layers.tex` | `rollprobe_layers_more.json` (step 04.4) |
| Past-difficulty numbers (last 8 / 32 / 128, entire context, by depth, text before the last 128) | `analysis/past_difficulty.py` -> `results/past_difficulty.txt` | `rollprobe_past.json`, `rollprobe_past_rows.npz` (step 04.3) |
| Probe similarity matrices (cosine of standardized weights; correlation of test-set predictions) | `analysis/probe_cosine.py` -> `results/probe_similarity.{tex,txt,png}` | the weights of steps 04.1 / 04.3, `rollprobe_standardization.npz` |
| Details (data composition, split, on-policy check) | `analysis/data_composition.py` -> `results/data_composition.txt` | step 02 / 03 files in `$SEQS`, labels in `$ACTS` |

Definitions used throughout: c_t = surprisal of token t under the model. Difficulty of the next K tokens at position s
= mean of c over the K tokens *after the next one* (c_{s+2} ... c_{s+K+1}): the next token's expected surprisal is just
the entropy of the model's prediction. Past difficulty = mean of c over the last K tokens up to s, or over tokens 1..s.
R2 is on the held-out test sequences (20%); ridge strengths are chosen on the validation sequences (10%).

## What each step does

1. **Data.** `HuggingFaceFW/fineweb` `sample/10BT/000_00000.parquet` (English seeds and natural text) and the
   `HuggingFaceFW/fineweb-2` test split of Chinese (`cmn_Hani`) and nine other languages (`fra_Latn deu_Latn rus_Cyrl
   jpn_Jpan kor_Hang arb_Arab spa_Latn hin_Deva ita_Latn`).
2. **Sequences** (`homeo/gen_rollouts_ml.py`). Rollout seeds = the first 3 tokens of random documents; natural windows =
   a document's start continued through further random documents of the same language joined by `<|endoftext|>` (as
   pretraining packs them). Lengths log-uniform in [160, 2048]. Each language mix is 70% English, 15% Chinese, 15% the
   nine others. The appends reproduce the original's growth from 5,000 to 7,000 rollouts.
3. **Generation and capture** (`runs/rollprobe/run.sh`): 7 chunks of 1,000 rollouts + 333 natural windows.
   - Sampling is pure ancestral: temperature 1 with only the temperature sampler in llama-server's chain (its default
     `min_p 0.05` would truncate). When the model ends a document, the end token stays and sampling continues.
   - Probe sites (`homeo/rollprobe_sites.py`): pairs of consecutive positions (d, d+1), depths stratified over
     [16, len - 133], one pair per 56 tokens.
   - `homeo-capture` teacher-forces each sequence from its token ids, stores all 61 block outputs at the sites (f16)
     and surprisal / entropy at every position.
4. **Probes.**
   - `homeo/rollprobe_fit.py`: one ridge probe on all 61 layers concatenated (374,784 features), solved exactly in
     sample space; per-layer probes; fixed-strength reliability of the forecast change.
   - `--lams 100`: the smoother probe used for forecast changes / TD errors; saves the kernels.
   - `homeo/rollprobe_refit.py`: new targets from the saved kernels (past difficulty; decoded entropy, surprisal, ...).
   - `homeo/rollprobe_layers.py`: per-layer probes for those targets.
   - `homeo/rollprobe_td.py`: forecast change / TD error analysis. `homeo/lin_probes_export.py`: bundle for the loom.
5. **Results**: the analysis scripts above.

## Checks

- `python3 ../tests/fake_rollprobe.py` then `python3 ../homeo/rollprobe_fit.py --acts /dev/shm/rollprobe_fake --seqs
  /dev/shm/rollprobe_fake --out /tmp/fakefit --device cpu` runs the whole fit on synthetic data in a few minutes (the
  raw-weight self-check should be ~1e-7).
- Each fit ends with a self-check: predictions recomputed from the saved raw weights against the fit's own
  (1e-4 or better).
- The trained probes from the original run are in `../probes/rollout` (see `../probes/README.md`).
