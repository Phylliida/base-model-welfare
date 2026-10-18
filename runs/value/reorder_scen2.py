#!/usr/bin/env python3
"""Put each prompt's first continuation before the second ones, so a partial run covers every prompt once."""
import json
import sys

import torch  # noqa: F401  (import before numpy on this box)
import numpy as np

d = sys.argv[1]
man = json.load(open(f'{d}/manifest.json'))
ids = np.fromfile(f'{d}/scenario_ids.bin', dtype=np.int32).reshape(len(man), 192)
seen, first, second = set(), [], []
for i, m in enumerate(man):
    key = (m['scenario'], m['prompt'])
    (second if key in seen else first).append(i)
    seen.add(key)
order = first + second
ids[order].tofile(f'{d}/scenario_ids.bin')
json.dump([dict(man[i], rep=int(i in second)) for i in order], open(f'{d}/manifest.json', 'w'), indent=1)
print(f'{len(first)} first continuations, then {len(second)} second')
