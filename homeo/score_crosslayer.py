"""Layer-to-layer kappa (plan B2): is a regulated direction regulated the same way at other layers?

For every source layer L, the top --n-dir pushed-back and amplified directions are fitted on half the prompts (in L's
top-64 capacity basis, as score_describe.py does), and their kappa is measured at every target layer M on the other
half: push u at M, read u at M, kappa_M(u) = -mean[(u.R_M - b)(u.G_M)] with b the leave-one-out prompt mean. Fitting
and measuring on different prompts keeps sample noise shared across layers out of the off-diagonal entries.
--n-split random prompt splits, each used both ways, averaged. The diagonal reproduces the held-out values of
score_describe.py.
Writes PREFIX.crosslayer.json: kappa[side][rank][source][target] (mean over splits) and its spread.

usage: score_crosslayer.py [PREFIX] [--n-dir 3] [--n-split 4] [--k 64] [--window 13-31]
"""
import argparse
import json
import os
import sys
import time

import torch
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score_io import ScoreRun  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('prefix', nargs='?', default='/mnt/models/homeo/score/sweep')
ap.add_argument('--n-dir', type=int, default=3)
ap.add_argument('--n-split', type=int, default=4)
ap.add_argument('--k', type=int, default=64)
ap.add_argument('--window', default='13-31')
a = ap.parse_args()
torch.set_grad_enabled(False)
rng = np.random.default_rng(0)

run = ScoreRun(a.prefix)
keep = np.flatnonzero(np.isin(run.prompt, run.whole_prompts()))
prompt = run.prompt[keep]
prompts = np.unique(prompt)
groups = [np.flatnonzero(prompt == q) for q in prompts]
D, K, ND = run.D, a.k, a.n_dir
layers = run.layers
t0 = time.time()


def loo(x):
    out = np.empty_like(x)
    for idx in groups:
        s = x[idx].sum(0)
        out[idx] = x[idx] - (s[None] - x[idx]) / (len(idx) - 1)
    return out


# all layers in memory (f32): G and the readout minus its leave-one-out prompt mean
G, R = {}, {}
for L in layers:
    G[L] = run.G(L, keep).astype(np.float32)
    R[L] = loo(run.R(L, a.window, keep).astype(np.float32))
print(f'loaded {len(layers)} layers ({time.time() - t0:.0f} s)', flush=True)

# evaluations: (fit half, test half) for each split, both ways
evals = []
for _ in range(a.n_split):
    perm = rng.permutation(len(prompts))
    A = np.isin(prompt, prompts[perm[:len(prompts) // 2]])
    evals += [(A, ~A), (~A, A)]

# phase 1: directions per (evaluation, source layer, side, rank), fitted on the fit half
U = np.zeros((len(evals), len(layers), 2, ND, D), np.float32)
for li, L in enumerate(layers):
    B = np.fromfile(f'{a.prefix}.L{L}.capbasis.f32', dtype=np.float32, count=K * D).reshape(K, D)
    g, r = G[L] @ B.T, R[L] @ B.T
    for e, (fit, _) in enumerate(evals):
        M = r[fit].T.astype(np.float64) @ g[fit].astype(np.float64) / fit.sum()
        ev, V = np.linalg.eigh((M + M.T) / 2)
        for rank in range(ND):
            U[e, li, 0, rank] = B.T @ V[:, rank]            # most pushed back (most negative eigenvalue of M)
            U[e, li, 1, rank] = B.T @ V[:, -1 - rank]       # most amplified
print(f'directions fitted ({time.time() - t0:.0f} s)', flush=True)

# phase 2: kappa of every direction at every target layer, on the test half
KAP = np.zeros((len(evals), len(layers), 2, ND, len(layers)))
Uf = U.reshape(len(evals), -1, D)
for mi, Mt in enumerate(layers):
    for e, (_, test) in enumerate(evals):
        pg = G[Mt][test] @ Uf[e].T
        pr = R[Mt][test] @ Uf[e].T
        KAP[e, :, :, :, mi] = (-(pr.astype(np.float64) * pg).mean(0)).reshape(len(layers), 2, ND)
    if mi % 10 == 0:
        print(f'target layer {Mt} ({time.time() - t0:.0f} s)', flush=True)

mean, sd = KAP.mean(0), KAP.std(0)
out = {'layers': layers, 'window': a.window, 'k': K, 'n_dir': ND, 'n_evals': len(evals),
       'kappa': {s: [mean[:, si, r, :].tolist() for r in range(ND)] for si, s in enumerate(('pushback', 'amplify'))},
       'kappa_sd': {s: [sd[:, si, r, :].tolist() for r in range(ND)] for si, s in enumerate(('pushback', 'amplify'))}}
json.dump(out, open(f'{a.prefix}.crosslayer.json', 'w'))

# summary: top direction of each source layer, its held-out kappa across target layers
print('\nsource L | side | kappa at L | peak over targets (layer) | targets with |kappa| >= half the peak')
for si, s in enumerate(('pushback', 'amplify')):
    for li, L in enumerate(layers):
        row = mean[li, si, 0]
        sg = 1 if s == 'pushback' else -1
        pk = int(np.argmax(sg * row))
        half = np.flatnonzero(sg * row >= 0.5 * sg * row[pk]) if sg * row[pk] > 0 else []
        span = f'{layers[half[0]]}-{layers[half[-1]]}' if len(half) else '-'
        if L % 3 == 0 or L >= 57:
            print(f'{L:3d} | {s[:4]} | {row[li]:+.3f} | {row[pk]:+.3f} ({layers[pk]}) | {span}')
print(f'-> {a.prefix}.crosslayer.json ({time.time() - t0:.0f} s)')
