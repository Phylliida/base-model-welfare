"""Check llama-server --probe-dirs against the natural-text capture (score/sense).

Sends whole captured rollouts (token ids) to a running server's /jlens with "dirs": true and compares u.h / |h| at
every captured position with the same quantity from the capture's projections (proj_LNN.f32: the block output on
the layer's capacity basis, which contains every exported direction). The server uses the jspace forward graph,
the capture llama.cpp's, so small differences are expected.

usage: score_probe_check.py [--url http://127.0.0.1:8056] [--n-seq 4]
"""
import argparse
import json
import os
import sys
import time
import urllib.request

import torch  # noqa: F401  (before numpy: this venv's numpy needs torch's libz)
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from value_probe import SAMPLE  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--url', default='http://127.0.0.1:8056')
ap.add_argument('--n-seq', type=int, default=4)
ap.add_argument('--dirs', default='/mnt/models/homeo/score/probe_dirs')
ap.add_argument('--sense', default='/mnt/models/homeo/score/sense')
ap.add_argument('--sweep', default='/mnt/models/homeo/score/sweep')
a = ap.parse_args()

P = json.load(open(a.dirs + '.json'))
meta = json.load(open(f'{a.sense}/meta.json'))
D, K, F, n = meta['n_embd'], meta['proj_k'], meta['n_extra'], meta['n_samples']
U = np.fromfile(a.dirs + '.f32', dtype=np.float32).reshape(len(P['names']), D).astype(np.float64)
samp = np.fromfile(f'{a.sense}/samples.bin', dtype=SAMPLE)
LAB = np.dtype([('seq', '<i4'), ('pos', '<i4'), ('token', '<i4'), ('rank_prev', '<i4'), ('surprisal', '<f4'),
                ('entropy_prev', '<f4'), ('entropy', '<f4'), ('pad', '<f4')])
lab = np.fromfile(f'{a.sense}/labels.bin', dtype=LAB)
seqs = np.unique(samp['seq'])[:a.n_seq]
layers = sorted(set(P['layers']))

# expected u.h / |h| per (seq, pos) and direction, from the capture
expect = {}
for L in layers:
    pr = np.fromfile(f'{a.sense}/proj_L{L:02d}.f32', dtype=np.float32, count=n * (K + F + 1)).reshape(n, K + F + 1)
    B = np.fromfile(f'{a.sweep}.L{L}.capbasis.f32', dtype=np.float32, count=K * D).reshape(K, D).astype(np.float64)
    idx = [k for k, l in enumerate(P['layers']) if l == L]
    m = np.isin(samp['seq'], seqs)
    cos = pr[m, :K].astype(np.float64) @ (B @ U[idx].T) / pr[m, -1:].astype(np.float64)
    for row, (sq, ps) in enumerate(zip(samp['seq'][m], samp['pos'][m])):
        for j, k in enumerate(idx):
            expect[int(sq), int(ps), k] = cos[row, j]

diffs, xs, ys = [], [], []
for sq in seqs:
    ml = lab['seq'] == sq
    toks = lab['token'][ml][np.argsort(lab['pos'][ml])].tolist()
    t0 = time.time()
    req = urllib.request.Request(a.url + '/jlens', data=json.dumps({'tokens': toks, 'dirs': True, 'readouts_only': True}).encode(),
                                 headers={'Content-Type': 'application/json'})
    out = json.load(urllib.request.urlopen(req, timeout=600))
    dt = time.time() - t0
    d = out['dirs']
    assert d['names'] == P['names'], 'server directions differ from the export'
    got = np.array(d['cos'])
    for (s_, ps, k), v in expect.items():
        if s_ == int(sq):
            xs.append(v); ys.append(got[ps, k])
    print(f'seq {sq}: {len(toks)} tokens, {len(d["names"])} directions at {len(layers)} layers, {dt:.1f} s', flush=True)

xs, ys = np.array(xs), np.array(ys)
err = np.abs(xs - ys)
print(f'{len(xs)} (position, direction) pairs: mean |diff| {err.mean():.5f}, max {err.max():.5f}, corr {np.corrcoef(xs, ys)[0, 1]:.6f}, '
      f'sd of the capture values {xs.std():.4f}')
