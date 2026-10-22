#!/usr/bin/env python3
"""Steering directions for the rollout probes: each single-layer probe's activation pattern at every layer.

A probe w reads a target from the state at layer L (y = w . h_L + b). Its raw weights are a poor direction to push
along (they lean on low-variance features the model rarely uses). The activation pattern a_L = Cov(h_L, y) (Haufe et
al. 2014) is the direction along which the layer's activations actually move with the readout; pushing along it moves
the state the way the target moves in natural text. Computed from the single-layer probes of rollprobe_fit.py
(rollprobe_layers_weights.f32: next 1 / 8 / 32 / 128, added 32 / 128) and rollprobe_layers.py
(rollprobe_layers_more_weights.f32: past 8 / 32 / 128 / all, entropy, surprisal, entropy prev, excess surprisal,
log rank, log context) on a random sample of training rows. Oriented so that +a raises the readout (w . a > 0).
Writes OUT/probe_patterns.f32 (unit vectors, f32 [n_targets][61][6144]) and OUT/probe_patterns.json (names, mean |h|
per layer, each target's best layer by test R2, w . a and the readout's sd per layer).

usage: probe_patterns.py [--probes /mnt/models/homeo/rollprobe] [--acts /data2/homeo/rollprobe_acts] [--n 40000]
"""
import argparse
import json
import time

import torch
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('--probes', default='/mnt/models/homeo/rollprobe')
ap.add_argument('--acts', default='/data2/homeo/rollprobe_acts')
ap.add_argument('--out', default=None, help='default: --probes')
ap.add_argument('--n', type=int, default=40000, help='training rows sampled for the covariances')
ap.add_argument('--threads', type=int, default=64)
a = ap.parse_args()
torch.set_num_threads(a.threads)
OUT = a.out or a.probes
D, NL = 6144, 61
t0 = time.time()

z = np.load(f'{a.probes}/rollprobe_rows.npz', allow_pickle=True)
tr = np.flatnonzero(z['split'] == 0)
sel = np.sort(np.random.default_rng(11).choice(tr, size=min(a.n, len(tr)), replace=False))
chunk, srow = z['chunk'][sel], z['srow'][sel]
offs = {int(k): json.load(open(f'{a.acts}/c{k}/meta.json'))['n_samples'] for k in np.unique(z['chunk'])}

F = json.load(open(f'{a.probes}/rollprobe.json'))
M = json.load(open(f'{a.probes}/rollprobe_layers_more.json'))
sets = [(f'{a.probes}/rollprobe_layers_weights.f32', F['names'], {L: F['per_layer'][str(L)] for L in range(NL)}),
        (f'{a.probes}/rollprobe_layers_more_weights.f32', M['names'], {L: M['per_layer'][str(L)] for L in range(NL)})]
names, Wl, r2 = [], [], {}
for path, nm, pl in sets:
    raw = np.fromfile(path, dtype=np.float32)
    Wl.append(raw[:NL * len(nm) * D].reshape(NL, len(nm), D))
    names += nm
    for t in nm:
        r2[t] = [pl[L][t]['test'] for L in range(NL)]
W = np.concatenate(Wl, axis=1)  # [61][n][6144]
n = len(names)
print(f'{n} targets, {len(sel)} rows ({time.time() - t0:.0f} s)', flush=True)


def load(L):
    X = np.empty((len(sel), D), np.float32)
    for k in offs:
        m = np.memmap(f'{a.acts}/c{k}/acts_L{L:02d}.f16', dtype=np.float16, mode='r', shape=(offs[k], D))
        s = np.flatnonzero(chunk == k)
        X[s] = m[srow[s]]
    return torch.from_numpy(X)


PAT = np.zeros((n, NL, D), np.float32)
h_norm, wa, y_sd = np.zeros(NL), np.zeros((n, NL)), np.zeros((n, NL))
for L in range(NL):
    X = load(L)
    h_norm[L] = float(X.norm(dim=1).mean())
    Xc = X - X.mean(0)
    Y = Xc @ torch.from_numpy(W[L].T.copy())  # [rows][n] readouts (centered)
    A = (Xc.T @ Y / len(sel)).T.double()      # [n][6144] Cov(h_L, y)
    A /= A.norm(dim=1, keepdim=True)
    s = (A @ torch.from_numpy(W[L]).double().T).diagonal()  # w . a
    A *= torch.sign(s)[:, None]
    PAT[:, L] = A.float().numpy()
    wa[:, L] = np.abs(s.numpy())
    y_sd[:, L] = Y.std(0).double().numpy()
    if L % 10 == 0:
        print(f'L{L:02d} |h| {h_norm[L]:.1f} ({time.time() - t0:.0f} s)', flush=True)
PAT.tofile(f'{OUT}/probe_patterns.f32')
json.dump({'names': names, 'n_layer': NL, 'n_embd': D, 'h_norm': h_norm.tolist(),
           'best_layer': {t: int(np.argmax(r2[t])) for t in names}, 'test_r2': r2,
           'w_dot_a': {t: wa[i].tolist() for i, t in enumerate(names)}, 'readout_sd': {t: y_sd[i].tolist() for i, t in enumerate(names)},
           'layout': 'f32 [n_targets][61][6144] unit vectors; +a raises the target; push = dose x mean |h_L| x a',
           'method': 'activation pattern Cov(h_L, w_L . h_L) of the single-layer probe at L, over training rows'},
          open(f'{OUT}/probe_patterns.json', 'w'), indent=1)
print(f'-> {OUT}/probe_patterns.{{f32,json}} ({time.time() - t0:.0f} s)')
