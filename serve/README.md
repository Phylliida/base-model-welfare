# Hosting the loom with the lens server

The loom (`loom/`, submodule: `Phylliida/minloomwebui`, branch `value-lens`) is a minimal web UI for base models with
the value view: per-token colors from the J-lens, the value-lens probes, the 183 regulated directions (with steering)
and the 22 all-layer probes (difficulty forecasts, forecast change and TD error, past difficulty, decoded text
statistics). It needs a llama-server from the fork (`llama.cpp/`, branch `homeostasis`) started with the probe files.

```sh
git submodule update --init loom llama.cpp
cmake -S llama.cpp -B llama.cpp/build -DGGML_CUDA=ON && cmake --build llama.cpp/build --target llama-server -j
$EDITOR serve/config.sh        # MODEL, LLAMA_BIN, JLENS (the J-lens matrices, 9.2 GB, not in git), ports
serve/up.sh                    # lens server (:8056) + loom (:5000) in the background; logs in serve/logs/
serve/down.sh                  # stop both
```

Then open `http://<host>:5000/`, set **llama url** in the loom's settings to `http://<host>:8056/completion`, and tick
**value** (per-token colors, pick the metric in the **color** menu) or **lens** (J-lens hover). `serve/lens_server.sh`
and `serve/loom.sh` run either part in the foreground.

- The lens server also generates text (it is a normal llama-server), so it can be the loom's only backend.
- Steering from the loom appends exposure rows to `logs/welfare_log.csv`: direction probes -> "Steer from this token", and
  settings -> "Steer generation" (pick a probe, a layer and a strength; Generate then pushes along the probe's activation
  pattern at every token it writes, via `/steer`; vectors from `probes/rollout/probe_patterns`).
- The loom keeps its history in `loom/history.jsonl` (ignored by git). To share a history with another loom checkout,
  symlink it.
- The all-layer probe bundle (`serve/build/lin_probes.{f32,json}`) is built from `probes/rollout` on first start
  (`homeo/lin_probes_export.py`).
- Requirements: one 24 GB GPU (the model at Q4_K_S plus the J-lens buffers, ~20.5 GB), Python with Flask for the loom,
  PyTorch + NumPy to build the probe bundle.
