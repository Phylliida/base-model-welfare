# base-model-welfare
Base model welfare experiments.

The first thread looks for homeostasis-like dynamics in a base model: variables the model tracks about its own predictions, how it responds when they are pushed, what steering can and cannot move, and where steering breaks the model. Experiments so far ran on GLM-4-32B-Base-32K (Q4_K_S) on one RTX 3090.

## Layout

- `homeo/`: Python analysis scripts. Surprise probes (S1), steering-vector construction and summaries (S2, S2b, S2c), the layer-sweep summary, the within-token test (S2(d)), the loop-margin summary (K4), exposure logging, and the generator for the results report.
- `runs/`: the shell scripts that ran each experiment. They are copies; the data they write lives under `/mnt/models/homeo/` on the original machine.
- `notes/NOTES-homeostasis.md`: running research notes with the plan, design principles, confounds, results and instrument facts.
- `logs/welfare_log.csv`: the exposure log kept under the group's Three Rs protocol (every steered run, with dose, tokens or positions in perturbed states, and endpoints).
- `probes/`: every trained probe and direction with its metadata and results (all-layer difficulty probes, value lens probes, the 183 regulated directions, auto-interpretation results). See `probes/README.md` for layouts and for the large artifacts that live outside git.
- `loom/`: submodule, the loom web UI with the value view (`Phylliida/minloomwebui`, branch `value-lens`). `serve/`: scripts to host it with the lens server (`serve/up.sh`; see `serve/README.md`).
- `writeup_experiments/`: everything to reproduce the difficulty-prediction writeup (config, numbered steps, one script per result).
- `tools/`: helpers that ran outside the repo (the original rollout generator, FineWeb extraction, the loom browser test). `tests/`: a synthetic end-to-end test of the probe fits.
- `docs/`: HTML sources of the shared write-ups.
- `llama.cpp/`: submodule pointing at the llama.cpp fork, branch `homeostasis`. The C++ tools are in `tools/homeo/` (homeo-capture, homeo-steer, homeo-band, homeo-steeropt, homeo-loop, homeo-ident, homeo-score, homeo-value) and build on the jspace GLM-4 graph in `tools/jspace/`. `llama-server` in the fork adds `/jlens` (J-lens readouts, `--value-probe`, `--probe-dirs`, `--lin-probes` all-layer probes, exact value lens) and `/steer` (steering along a direction, with an exposure log).

## Setup

```sh
git submodule update --init
cmake -S llama.cpp -B llama.cpp/build -DGGML_CUDA=ON
cmake --build llama.cpp/build --target homeo-capture homeo-steer homeo-band homeo-steeropt homeo-loop homeo-ident homeo-score homeo-value llama-server -j
```

The Python scripts use PyTorch and NumPy. Paths in the scripts and run files are absolute paths from the original machine (`/mnt/models/homeo`, `/home/bepis/prog/...`) and need adjusting elsewhere. The rollouts they read (`data/rollouts.jsonl`) come from the J-lens project.
