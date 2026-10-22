# Trained probes, directions and their results

Everything here was fitted on GLM-4-32B-Base-32K (Q4_K_S, `GLM-4-32B-Base-32K.i1-Q4_K_S.gguf`; n_embd 6144, 61 blocks).
Weights are little-endian float32 on **raw block outputs** (`l_out-L`, the residual stream after block L; no
normalization needed), unless noted. The notes (`notes/NOTES-homeostasis.md`) describe each experiment; the section
names below match them. Larger artifacts that are not in git (per-row predictions, per-layer capacity bases, the
J-lens matrices, the captured activations) are listed at the end with where they live.

## `rollout/`: all-layer probes on rollouts and natural text (notes: "Rollout probe results", "Rollout probe follow-ups")

Data: 7,000 pure ancestral rollouts + 2,333 natural windows (FineWeb / FineWeb-2; 70% English, 15% Chinese, 15% nine
other languages), 213,704 positions, split by sequence 70 / 10 / 20. Dual ridge on all 61 block outputs concatenated.

| file | targets | layout | made by |
|---|---|---|---|
| `rollprobe_weights.f32` | next 1, next 8, next 32, next 128, added 32, added 128 (strength chosen on val: 10; added 31.6) | f32 [6][61][6144] then [6] bias; value = sum_L w_L . h_L + b | `homeo/rollprobe_fit.py` |
| `rollprobe_l100_weights.f32` | same, strength 100 (forecast change ~90% reliable; use for TD work) | same | `rollprobe_fit.py --lams 100 --tag _l100` |
| `rollprobe_past_weights.f32` | past 8, past 32, past 128, past all | f32 [4][61][6144] then [4] | `homeo/rollprobe_refit.py` |
| `rollprobe_baseline_weights.f32` | entropy, surprisal, entropy prev, excess surprisal, log rank, log context | f32 [6][61][6144] then [6] | `rollprobe_refit.py --targets baseline` |
| `rollprobe_standardization.npz` | mean and sd of every raw block-output feature over the training rows (mu, sd: [61][6144]); multiply raw weights by sd for the standardized coordinates the fits worked in | npz | `writeup_experiments/analysis/probe_cosine.py` (from the saved kernels) |
| `rollprobe_layers_weights.f32` | the six forecast targets, one probe per layer (profile) | f32 [61][6][6144] then [61][6] | `rollprobe_fit.py` |
| `rollprobe*.json`, `*.txt` | names, test / val R2, strengths, by-group and by-depth results, baseline coefficients, reliability, self-checks | | |
| `rollprobe_td.{json,txt}` | forecast change / TD error analysis | | `homeo/rollprobe_td.py` |
| `lin_probes.json` | the bundle served by `llama-server --lin-probes` and shown in the loom: keys, labels, test R2, color-scale percentiles | the matching `lin_probes.f32` is rebuilt from the weights here: `python3 homeo/lin_probes_export.py --dir probes/rollout` | `homeo/lin_probes_export.py` |

Targets: c_t = surprisal of token t. "next K" at position s = mean of c over the K tokens after the next one
(c_{s+2} ...); "next 1" = c_{s+1}; "past K" = mean of c over the last K tokens up to s; "added K" predicts the
residual of the OLS baseline in `rollprobe.json` (`baseline_coef`). Forecasts are in nats per token.

## `value_lens/`: value lens probes on FineWeb windows (notes: VL1-VL5, H2, "All-layer value probe")

| file | what | layout |
|---|---|---|
| `readout_L40.{f32,json}` | layer-40 readouts served by `llama-server --value-probe` (stakes, now, forecasts) | f32 [n][6144] then [n] bias; json: layer, names |
| `probe_L40.f32`, `probe.json` | VL2 linear probe of the value lens at layer 40 | see `homeo/value_probe.py` |
| `probe_all_weights.f32` | all-layer value probe v2: stakes, now, next 8, next 32, added 8, added 32 | f32 [6][61][6144] then [6] |
| `probe_layers_weights.f32` | per-layer probes of the same targets | f32 [61][6][6144] then [61][6] |
| `probe_all*.json/txt`, `forecast_L40.*`, `forecast_reliability.json`, `summary.txt`, `readout_check.txt` | results and checks (`*_v1` = the audited first version) | |
| `token_stats_fineweb.json` | FineWeb percentiles of surprisal, entropy and difficulty used by the loom's color scales | |
| `mean_h_L40.npy` | mean layer-40 state over the probe data | f32 [6144] |
| `value_dirs/` | value-lens gradient directions at layer 40 (VL1: `fut_dirs_L40*.npy`, summaries) | npy |

## `directions/`: regulated directions (notes: plan B, B2, "Sensor side at every layer", causal tests A-C)

| file | what |
|---|---|
| `score/probe_dirs.{f32,json}` | the 183 regulated directions (layers 27-60) used by the loom and `/steer` (`llama-server --probe-dirs`): unit directions f32 [183][6144]; json: names, layers, family, orientation, readings, effect sizes, percentiles |
| `score/screen.capbasis.{f32,json}` | layer-40 capacity basis from the screen (f32 [256][6144]) |
| `score/sweep_capbasis/sweep.L*.capbasis.{f32,json}` | the layer sweep's capacity basis at every layer 0-60 (f32 [128][6144] each; json: per-direction capacities, held-out effects); the 183 directions in `probe_dirs` were selected from these |
| `score/sweep.describe_cap64.*`, `score/sweep.crosslayer.json`, `score/screen.*` | layer-sweep descriptions, cross-layer matches, screen fits |
| `ident/basis_pca256_L40.{f32,json}` | PCA basis used by the closed-loop identification (f32 [256][6144]) |
| `ident/main_1000.fit*`, `ident/main.fit*`, `ident/*_M.npy`, `ident/capacity_bound.json` | identified feedback matrices M and fits (plan B main run) |
| `ident/main_1000_dirs/` | top directions of the main run, saved for steering (`dir_*.f32`, f32 [6144]) |

## `autointerp/`: causal interpretation (notes: (B) scored auto-interpretation, (C) interchange interventions)

`data.json` (evidence per direction), `tasks/` (the anonymized explainer / judge files), `keys.json` (held-out answers),
`results.json` (the workflow's output), `scores.{json,txt}`, `interchange.{json,txt}`. The workflow script is
`runs/autointerp/autointerp-directions.workflow.js` (args next to it).

## Not in git (large)

| what | where (original machine) | backup copy |
|---|---|---|
| captured activations of the rollout probe (all 61 layers at 213,704 positions, f16) + rollouts / sequences / logs | `/data2/homeo/rollprobe_acts` (150 GB) | (is itself the copy; the `/dev/shm` original was freed) |
| per-row targets and predictions of the rollout probes (`rollprobe*_rows.npz`), `lin_probes.f32`, `probe_all_pred.npz` | `/mnt/models/homeo/rollprobe`, `/mnt/models/homeo/value_probe` | `/data2/homeo/artifacts/` |
| J-lens matrices used by the loom / server (`rlens_rollout_mixed.jlns`, 9.2 GB) | `/mnt/models/jlens/` | `/data2/homeo/artifacts/jlens/` |
| raw captures of earlier experiments (S1, value lens gradients, score records; ~90 GB) | `/mnt/models/homeo/*` | regenerable with the run scripts in `runs/` |
