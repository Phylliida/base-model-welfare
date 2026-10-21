#!/usr/bin/env python3
"""New targets for the all-layer rollout probe from saved kernels (rollprobe_fit.py --save-kernels): only the solves.

--targets past (default): past difficulty, the mean surprisal of the tokens up to and including the current one (c_t =
surprisal of token t under the model): past 8 / 32 / 128 and past all (tokens 1..s, the entire past context).
--targets baseline: the fit's baseline features and their relatives, read from the state at s: next-token entropy H_s,
current surprisal c_s, entropy before the current token H_{s-1}, excess surprisal c_s - H_{s-1}, log(1 + rank of the
current token under p_{s-1}), log context length log(s + 1). Same split, same
standardization and kernels as the fit; strength per target on val (--lams); test R2 overall, within sequence, by
depth and by language group x kind; raw weights in the fit's layout and a self-check.
Writes OUT/rollprobe{TAG}.json / .txt, rollprobe{TAG}_rows.npz (targets + val/test predictions), rollprobe{TAG}_weights.f32
(f32 [n_targets][61][6144] then [n_targets] bias; target = sum_L w_L . h_L + b, raw block outputs).

usage: rollprobe_refit.py [--kernels /dev/shm/rollprobe_kernels] [--rows /mnt/models/homeo/rollprobe/rollprobe_rows.npz]
                          [--acts /data2/homeo/rollprobe_acts] [--tag _past] [--lams 1,10,100,1000]
"""
import argparse
import json
import os
import time

import torch
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('--kernels', default='/dev/shm/rollprobe_kernels')
ap.add_argument('--rows', default='/mnt/models/homeo/rollprobe/rollprobe_rows.npz')
ap.add_argument('--acts', default='/data2/homeo/rollprobe_acts')
ap.add_argument('--out', default='/mnt/models/homeo/rollprobe')
ap.add_argument('--targets', default='past', choices=['past', 'baseline'])
ap.add_argument('--tag', default=None, help='default: _past / _baseline')
ap.add_argument('--lams', default='1,10,100,1000')
ap.add_argument('--threads', type=int, default=64)
a = ap.parse_args()
torch.set_num_threads(a.threads)
D, NL = 6144, 61
LABEL = np.dtype([('seq', '<i4'), ('pos', '<i4'), ('token', '<i4'), ('rank_prev', '<i4'), ('surprisal', '<f4'),
                  ('entropy_prev', '<f4'), ('entropy', '<f4'), ('pad', '<f4')])
t0 = time.time()
lines = []
say = lambda s='': (print(s, flush=True), lines.append(s))

z = np.load(a.rows, allow_pickle=True)
kr = np.load(f'{a.kernels}/rows.npz', allow_pickle=True)
kj = json.load(open(f'{a.kernels}/kernels.json'))
tr, va, te = kr['tr'], kr['va'], kr['te']
assert (z['split'][tr] == 0).all() and (z['split'][va] == 1).all() and (z['split'][te] == 2).all()
N = len(z['pos'])
chunk, srow, seq, pos = z['chunk'], z['srow'], z['seq'], z['pos']

# ---- targets ----
a.tag = a.tag if a.tag is not None else f'_{a.targets}'
past_all, ent_prev, rank_prev = np.empty(N), np.empty(N), np.empty(N)
for k in np.unique(chunk):
    lab = np.fromfile(f'{a.acts}/c{k}/labels.bin', dtype=LABEL)
    starts = list(np.flatnonzero(lab['pos'] == 0)) + [len(lab)]
    for i in np.flatnonzero(chunk == k):
        L_ = lab[starts[seq[i]]:starts[seq[i] + 1]]
        assert L_['pos'][pos[i]] == pos[i]
        past_all[i] = L_['surprisal'][1:pos[i] + 1].astype(np.float64).mean()
        ent_prev[i], rank_prev[i] = L_['entropy_prev'][pos[i]], L_['rank_prev'][pos[i]]
if a.targets == 'past':
    NAMES = ['past 8', 'past 32', 'past 128', 'past all']
    Y = np.stack([z['m8'], z['m32'], z['m128'], past_all], 1)
else:
    NAMES = ['entropy', 'surprisal', 'entropy prev', 'excess surprisal', 'log rank', 'log context']
    Y = np.stack([z['ent'], z['cur'], ent_prev, z['cur'] - ent_prev, np.log1p(rank_prev), z['logd']], 1)
uid = z['chunk'].astype(np.int64) * 100000 + z['seq']
LG, KIND = z['lang_group'], z['kind']
say(f'{N} rows; train {len(tr)}, val {len(va)}, test {len(te)}; targets {", ".join(NAMES)} ({time.time() - t0:.0f} s)')


def r2(y, p):
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def demean_seq(v, rows):
    _, inv = np.unique(uid[rows], return_inverse=True)
    return v - (np.bincount(inv, v) / np.bincount(inv))[inv]


def score(j, p, rows):
    return {'test': r2(Y[rows, j], p), 'within': r2(demean_seq(Y[rows, j], rows), demean_seq(p, rows))}


# ---- solves ----
n_tr = len(tr)
Ktr = np.memmap(f'{a.kernels}/Ktr.f32', dtype=np.float32, mode='r', shape=tuple(kj['Ktr']))
Kva = torch.from_numpy(np.fromfile(f'{a.kernels}/Kva.f32', dtype=np.float32).reshape(kj['Kva']))
Kte = torch.from_numpy(np.fromfile(f'{a.kernels}/Kte.f32', dtype=np.float32).reshape(kj['Kte']))
Yt = torch.from_numpy(Y[tr]).float()
ym = Yt.mean(0)
sols, pv, pe = {}, {}, {}


def solve(lam):
    M = torch.from_numpy(np.array(Ktr))  # a fresh copy each time
    M.diagonal().add_(lam * n_tr)
    sols[lam] = torch.cholesky_solve(Yt - ym, torch.linalg.cholesky(M))
    del M
    pv[lam], pe[lam] = (Kva @ sols[lam] + ym).double().numpy(), (Kte @ sols[lam] + ym).double().numpy()
    say(f'  lambda {lam:g}: val R2 ' + ', '.join(f'{nm} {r2(Y[va, j], pv[lam][:, j]):.4f}' for j, nm in enumerate(NAMES)) + f' ({time.time() - t0:.0f} s)')


for lam in [float(x) for x in a.lams.split(',')]:
    solve(lam)
for _ in range(2):  # a best strength at the edge of the grid: one decade further out
    best = [max(sols, key=lambda l_: r2(Y[va, j], pv[l_][:, j])) for j in range(len(NAMES))]
    ext = sorted({b * (10.0 if b == max(sols) else 0.1) for b in best if b in (min(sols), max(sols))})
    if not ext:
        break
    for lam in ext:
        solve(lam)
res, lam_of = {}, {}
PRED = np.full((N, len(NAMES)), np.nan)
for j, nm in enumerate(NAMES):
    lam = max(sols, key=lambda l_: r2(Y[va, j], pv[l_][:, j]))
    lam_of[j] = lam
    res[nm] = dict(score(j, pe[lam][:, j], te), lam=lam, val=r2(Y[va, j], pv[lam][:, j]), lam_edge=lam in (min(sols), max(sols)))
    PRED[va, j], PRED[te, j] = pv[lam][:, j], pe[lam][:, j]
groups = {}
DEPTH = [(16, 64), (64, 256), (256, 1024), (1024, 2048)]
for j, nm in enumerate(NAMES):
    g_ = {}
    for lo, hi in DEPTH:
        m = te[(pos[te] >= lo) & (pos[te] < hi)]
        if len(m) > 50:
            g_[f'depth {lo}-{hi}'] = dict(score(j, PRED[m, j], m), n=int(len(m)))
    for g in ('en', 'zh', 'other'):
        for kd in ('rollout', 'pretrain'):
            m = te[(LG[te] == g) & (KIND[te] == kd)]
            if len(m) > 50:
                g_[f'{g} {kd}'] = dict(score(j, PRED[m, j], m), n=int(len(m)))
    groups[nm] = g_

# ---- raw weights + self-check ----
offs = {int(k): json.load(open(f'{a.acts}/c{k}/meta.json'))['n_samples'] for k in np.unique(chunk)}


def load(L):
    X = np.empty((N, D), np.float32)
    for k in offs:
        m = np.memmap(f'{a.acts}/c{k}/acts_L{L:02d}.f16', dtype=np.float16, mode='r', shape=(offs[k], D))
        sel = np.flatnonzero(chunk == k)
        X[sel] = m[srow[sel]]
    return torch.from_numpy(X)


AL = torch.stack([sols[lam_of[j]][:, j] for j in range(len(NAMES))], 1)
WJ = np.zeros((len(NAMES), NL, D), np.float32)
bj = np.array([float(ym[j]) for j in range(len(NAMES))], np.float64)
pchk = np.zeros((len(te), len(NAMES)))
mu_all, sd_all = torch.from_numpy(kr['mu']), torch.from_numpy(kr['sd'])
for L in range(NL):
    X = load(L)
    mu, sd = mu_all[L], sd_all[L]
    W = ((((X[tr] - mu) / sd).T @ AL) / sd[:, None]).numpy()
    WJ[:, L] = W.T
    bj -= mu.numpy().astype(np.float64) @ W.astype(np.float64)
    pchk += (X[te].double() @ torch.from_numpy(W).double()).numpy()
    del X
with open(f'{a.out}/rollprobe{a.tag}_weights.f32', 'wb') as fh:
    WJ.reshape(-1).tofile(fh)
    bj.astype(np.float32).tofile(fh)
chk = {nm: float(np.abs(pchk[:, j] + bj[j] - PRED[te, j]).max()) for j, nm in enumerate(NAMES)}

say()
say(f'self-check, raw weights vs kernel predictions (max |diff|): ' + ', '.join(f'{k} {v:.1e}' for k, v in chk.items()))
say('test R2 of the all-layer probe (within-sequence in parentheses), strength chosen on val:')
for nm, r in res.items():
    say(f'  {nm:9s} {r["test"]:.3f} ({r["within"]:.3f})  lambda {r["lam"]:g}' + (' (grid edge)' if r['lam_edge'] else ''))
say('by depth / group:')
for nm, g_ in groups.items():
    say(f'  {nm}: ' + ', '.join(f'{g} {v["test"]:.3f}' for g, v in g_.items()))
out = {'names': NAMES, 'results': res, 'groups': groups, 'lams': list(sols), 'kernels': a.kernels,
       'weights': {'file': f'{a.out}/rollprobe{a.tag}_weights.f32', 'layout': 'f32 [n_targets][61][6144] then [n_targets] bias; '
                   'target = sum_L w_L . h_L + b (raw block outputs)', 'selfcheck_max_abs_diff': chk}}
json.dump(out, open(f'{a.out}/rollprobe{a.tag}.json', 'w'), indent=1)
np.savez(f'{a.out}/rollprobe{a.tag}_rows.npz', Y=Y, pred=PRED, names=np.array(NAMES), split=z['split'])
open(f'{a.out}/rollprobe{a.tag}.txt', 'w').write('\n'.join(lines) + '\n')
say(f'-> {a.out}/rollprobe{a.tag}.json ({time.time() - t0:.0f} s)')
