# tools

Helpers that lived outside the repo while the experiments ran (copied here so everything can be reproduced):

- `gen_rollouts.py`: the original rollout generator (FineWeb-seeded rollouts, `data/rollouts.jsonl`; used by S1, the
  J-lens fits and the value lens). Fixed on 2026-10-20 to sample purely (temperature-only sampler chain, `min_p 0`):
  every rollout made before that date was clipped by llama-server's default `min_p 0.05`. The multilingual rollout
  probe uses `homeo/gen_rollouts_ml.py` instead.
- `extract_fineweb.py`: FineWeb parquet shard -> plain-text corpus (input of the J-lens tokenization).
- `gen_speed.py`: throughput check of a llama-server generation setup (N parallel requests x T tokens).
- `loom_bidi_test.py`: headless Firefox (WebDriver BiDi) test of the loom value view against a scratch loom server on
  :5055 and llama-server on :8056; requests to :8055 are blocked. Steps are JSON on the command line, e.g.
  `python3 tools/loom_bidi_test.py '[{"color": "lintd:fc100:next 128", "hover": 40, "shot": "td"}]'`.
