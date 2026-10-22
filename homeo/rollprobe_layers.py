#!/usr/bin/env python3
"""Per-layer profile of the rollout probes for the past-difficulty and decoded-statistics targets (the forecast
targets got theirs in rollprobe_fit.py): one ridge probe per layer on that block's output alone, on the CPU.

Targets at position s (c_t = surprisal of token t): past 8 / 32 / 128 / all (mean c of the last K tokens up to s, or
of tokens 1..s), next-token entropy H_s, current surprisal c_s, entropy before the current token H_{s-1}, excess
surprisal c_s - H_{s-1}, log(1 + rank of the current token), log context length. Same rows, split and
standardization as the fit (kernel rows.npz from rollprobe_fit.py --save-kernels); strength per target and layer on
val (1e-3 .. 1e3, half decades); test R2 overall and within sequence.
Writes OUT/rollprobe_layers_more.json (per layer and target: test, within, val, strength) and
OUT/rollprobe_layers_more_weights.f32 ([61][n_targets][6144] then [61][n_targets] bias, raw block outputs).

usage: rollprobe_layers.py [--rows /mnt/models/homeo/rollprobe/rollprobe_rows.npz] [--acts /data2/homeo/rollprobe_acts]
                           [--kernels /dev/shm/rollprobe_kernels]
"""
import argparse
import json
import time

import torch
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('--rows', default='/mnt/models/homeo/rollprobe/rollprobe_rows.npz')
ap.add_argument('--acts', default='/data2/homeo/rollprobe_acts')
ap.add_argument('--kernels', default='/dev/shm/rollprobe_kernels', help='only rows.npz (split, mean / sd) is read')
ap.add_argument('--out', default='/mnt/models/homeo/rollprobe')
ap.add_argument('--threads', type=int, default=64)
a = ap.parse_args()
torch.set_num_threads(a.threads)
D, NL = 6144, 61
LABEL = np.dtype([('seq', '<i4'), ('pos', '<i4'), ('token', '<i4'), ('rank_prev', '<i4'), ('surprisal', '<f4'),
                  ('entropy_prev', '<f4'), ('entropy', '<f4'), ('pad', '<f4')])
t0 = time.time()
z = np.load(a.rows, allow_pickle=True)
kr = np.load(f'{a.kernels}/rows.npz', allow_pickle=True)
tr, va, te = kr['tr'], kr['va'], kr['te']
N = len(z['pos'])
chunk, srow, seq, pos = z['chunk'], z['srow'], z['seq'], z['pos']
past_all, ent_prev, rank_prev = np.empty(N), np.empty(N), np.empty(N)
for k in np.unique(chunk):
    lab = np.fromfile(f'{a.acts}/c{k}/labels.bin', dtype=LABEL)
    starts = list(np.flatnonzero(lab['pos'] == 0)) + [len(lab)]
    for i in np.flatnonzero(chunk == k):
        L_ = lab[starts[seq[i]]:starts[seq[i] + 1]]
        past_all[i] = L_['surprisal'][1:pos[i] + 1].astype(np.float64).mean()
        ent_prev[i], rank_prev[i] = L_['entropy_prev'][pos[i]], L_['rank_prev'][pos[i]]
NAMES = ['past 8', 'past 32', 'past 128', 'past all', 'entropy', 'surprisal', 'entropy prev', 'excess surprisal', 'log rank', 'log context']
Y = np.stack([z['m8'], z['m32'], z['m128'], past_all, z['ent'], z['cur'], ent_prev, z['cur'] - ent_prev, np.log1p(rank_prev), z['logd']], 1)
uid = chunk.astype(np.int64) * 100000 + seq
offs = {int(k): json.load(open(f'{a.acts}/c{k}/meta.json'))['n_samples'] for k in np.unique(chunk)}
print(f'{N} rows, targets ready ({time.time() - t0:.0f} s)', flush=True)


def r2(y, p):
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def demean_seq(v, rows):
    _, inv = np.unique(uid[rows], return_inverse=True)
    return v - (np.bincount(inv, v) / np.bincount(inv))[inv]


def load(L):
    X = np.empty((N, D), np.float32)
    for k in offs:
        m = np.memmap(f'{a.acts}/c{k}/acts_L{L:02d}.f16', dtype=np.float16, mode='r', shape=(offs[k], D))
        sel = np.flatnonzero(chunk == k)
        X[sel] = m[srow[sel]]
    return torch.from_numpy(X)


LAMS = [float(10 ** (e / 2)) for e in range(-6, 7)]
n_tr = len(tr)
Yt = torch.from_numpy(Y[tr])
ym = Yt.mean(0)
res = {}
WL = np.zeros((NL, len(NAMES), D), np.float32)
BL = np.zeros((NL, len(NAMES)), np.float32)
for L in range(NL):
    tl = time.time()
    X = load(L)
    mu, sd = torch.from_numpy(kr['mu'][L]), torch.from_numpy(kr['sd'][L])
    X.sub_(mu).div_(sd)
    Zt = X[tr]
    A = (Zt.T @ Zt).double()
    Bm = (Zt.T @ (Yt - ym).float()).double()
    del Zt
    Zv, Ze = X[va].double(), X[te].double()
    del X
    pv, pe, Ws = {}, {}, {}
    for lam in LAMS:
        M = A.clone()
        M.diagonal().add_(lam * n_tr)
        W = torch.cholesky_solve(Bm, torch.linalg.cholesky(M))
        pv[lam], pe[lam], Ws[lam] = (Zv @ W + ym).numpy(), (Ze @ W + ym).numpy(), W
    r = {}
    for j, nm in enumerate(NAMES):
        lam = max(LAMS, key=lambda l_: r2(Y[va, j], pv[l_][:, j]))
        p = pe[lam][:, j]
        r[nm] = {'test': r2(Y[te, j], p), 'within': r2(demean_seq(Y[te, j], te), demean_seq(p, te)),
                 'val': r2(Y[va, j], pv[lam][:, j]), 'lam': lam, 'lam_edge': lam in (LAMS[0], LAMS[-1])}
        w = (Ws[lam][:, j].float() / sd).numpy()
        WL[L, j], BL[L, j] = w, float(ym[j]) - float(w.astype(np.float64) @ mu.numpy().astype(np.float64))
    res[str(L)] = r
    print(f'L{L:02d}: ' + ', '.join(f'{nm} {r[nm]["test"]:.3f}' for nm in NAMES) + f'  ({time.time() - tl:.0f} s, total {time.time() - t0:.0f} s)', flush=True)
    json.dump({'names': NAMES, 'per_layer': res}, open(f'{a.out}/rollprobe_layers_more.json', 'w'), indent=1)
np.concatenate([WL.reshape(-1), BL.reshape(-1)]).tofile(f'{a.out}/rollprobe_layers_more_weights.f32')
peaks = {nm: max(res, key=lambda L: res[L][nm]['test']) for nm in NAMES}
json.dump({'names': NAMES, 'per_layer': res, 'peaks': peaks,
           'weights': {'file': f'{a.out}/rollprobe_layers_more_weights.f32',
                       'layout': f'[61][{len(NAMES)}][6144] then [61][{len(NAMES)}] bias; target = w . h + b (raw block output)'}},
          open(f'{a.out}/rollprobe_layers_more.json', 'w'), indent=1)
print('peaks: ' + ', '.join(f'{nm} L{L} {res[L][nm]["test"]:.3f}' for nm, L in peaks.items()) + f' ({time.time() - t0:.0f} s)', flush=True)
