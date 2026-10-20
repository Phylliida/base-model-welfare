#!/usr/bin/env python3
"""FineWeb reference distributions for the loom's actual-difficulty metrics, added to its token stats file.

surpK at position s: mean surprisal of the K tokens after the next one (-log p(x_{s+2}) ...), K = 8, 32, 64, 128;
for K = 8 and 32 the target of the forecast probes (value_forecast.py), so the loom can show forecast and actual side
by side. From the 1200 VL1 windows (homeo-value log-likelihoods of 192-token fineweb windows, positions 32 on, every
position with the full horizon: 152k for K <= 32, 112k for 64, 36k for 128). Other entries of the stats file are
kept.

usage: token_stats_difficulty.py [--stats /mnt/models/homeo/value_probe/token_stats_fineweb.json]
"""
import argparse
import json
import os
import sys

import torch  # noqa: F401  (before numpy: this venv's numpy needs torch's libz)
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ap = argparse.ArgumentParser()
ap.add_argument('--stats', default='/mnt/models/homeo/value_probe/token_stats_fineweb.json')
ap.add_argument('--value', default='/mnt/models/homeo/value')
a = ap.parse_args()
st = json.load(open(a.stats))
PCT = [1, 5, 25, 50, 75, 95, 99]
vals = {8: [], 32: [], 64: [], 128: []}
for w in range(1200):
    s_ = -np.array(json.load(open(f'{a.value}/w{w:05d}.json'))['ll'])  # s_[i] = surprisal of token i+1
    for K, out in vals.items():
        for s in range(32, len(s_) - K):
            out.append(s_[s + 1:s + K + 1].mean())
for key, v in ((f'surp{K}', np.array(x)) for K, x in vals.items()):
    st['stats'][key] = {'mean': float(v.mean()), 'sd': float(v.std()), 'n': int(len(v)),
                        'pct': {str(p): float(q) for p, q in zip(PCT, np.percentile(v, PCT))},
                        'source': f'mean surprisal of the {key[4:]} tokens after the next one; 1200 VL1 fineweb windows (192 tokens), positions 32 on with the full horizon'}
    print(key, {k: round(x, 3) for k, x in st['stats'][key]['pct'].items()})
json.dump(st, open(a.stats, 'w'), indent=1)
print(f'-> {a.stats}')
