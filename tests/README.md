# tests

- `fake_rollprobe.py`: writes synthetic data in the real homeo-capture formats (`/dev/shm/rollprobe_fake`: labels,
  samples, 61 f16 activation files, capture jsonl) with a planted linear signal, to test `homeo/rollprobe_fit.py` and
  `homeo/rollprobe_refit.py` end to end in minutes, e.g.
  `python3 tests/fake_rollprobe.py && python3 homeo/rollprobe_fit.py --acts /dev/shm/rollprobe_fake --seqs /dev/shm/rollprobe_fake --out /tmp/fakefit --device cpu`
  (the raw-weight self-check should be ~1e-7).
