#!/usr/bin/env python3
"""FineWeb reference distributions for the loom's actual-difficulty metrics, added to its token stats file.

surp8 / surp32 at position s: mean surprisal of the 8 / 32 tokens after the next one (-log p(x_{s+2}) ...), i.e. the
target of the forecast probes (value_forecast.py), so the loom can show forecast and actual side by side. From the
1200 VL1 windows (homeo-value log-likelihoods, positions 32-158, all positions). Other entries of the stats file
are kept.

usage: token_stats_difficulty.py [--stats /mnt/models/homeo/value_probe/token_stats_fineweb.json]
"""
import argparse
import json
import os
import sys

import torch  # noqa: F401  (before numpy: this venv's numpy needs torch's libz)
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from value_forecast import features, blank_tokens  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--stats', default='/mnt/models/homeo/value_probe/token_stats_fineweb.json')
ap.add_argument('--value', default='/mnt/models/homeo/value')
a = ap.parse_args()
F8, F32, _, _, _ = features(a.value, 1200, blank_tokens())
st = json.load(open(a.stats))
PCT = [1, 5, 25, 50, 75, 95, 99]
for key, v in (('surp8', F8), ('surp32', F32)):
    st['stats'][key] = {'mean': float(v.mean()), 'sd': float(v.std()), 'n': int(len(v)),
                        'pct': {str(p): float(q) for p, q in zip(PCT, np.percentile(v, PCT))},
                        'source': 'mean surprisal of the 8 / 32 tokens after the next one; 1200 VL1 fineweb windows, positions 32-158'}
    print(key, {k: round(x, 3) for k, x in st['stats'][key]['pct'].items()})
json.dump(st, open(a.stats, 'w'), indent=1)
print(f'-> {a.stats}')
