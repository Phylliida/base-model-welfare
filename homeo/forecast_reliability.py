#!/usr/bin/env python3
"""How much training data a difficulty-forecast probe needs before its token-to-token change is signal, not noise.

The forecast f_i (value_forecast.py's target: mean surprisal of the 8 / 32 tokens after the next one, predicted
linearly from the state at token i) and its change df_i = f_i - f_{i-1} (how much token i moved the model's expectation
of how hard the text will be; the TD error adds the realized log p of the token, which has no estimation noise).
For training sizes n (windows), two probes are fit on DISJOINT sets of n training windows (strength chosen on the val
windows) and both predict the same test windows. Their agreement estimates the reliability of a probe trained on n
windows: corr(f_A, f_B) for the forecast, corr(df_A, df_B) for its change (two parallel measures of reliability rho
correlate at rho). Repeated over random partitions. Reliability is fit as rho(n) = n / (n + c) (estimation error
shrinking as 1/n; Spearman-Brown), which gives the n needed for 0.8 and 0.9. Also the test R2 learning curve of f
(clean positions), which shows whether more data still improves the forecast itself.
Per layer (primal ridge, 6144 features) at --layers, and optionally for the all-layer probe (--joint; dual ridge,
every other training position). Split as value_probe_all.py (fineweb offset blocks 800 / 100 / 300).
Writes OUT/forecast_reliability.json and .txt.

usage: forecast_reliability.py [--acts /dev/shm/vlprobe_all] [--layers 20,30,40,43,50,56,60] [--joint]
"""
import argparse
import json
import os
import sys
import time

import torch
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from value_probe import P, P_LO, P_HI, D, SAMPLE, rows  # noqa: E402
from value_forecast import features, blank_tokens  # noqa: E402

H = '/mnt/models/homeo'
ap = argparse.ArgumentParser()
ap.add_argument('--acts', default='/dev/shm/vlprobe_all')
ap.add_argument('--value', default=f'{H}/value')
ap.add_argument('--out', default=f'{H}/value_probe')
ap.add_argument('--layers', default='20,30,40,43,50,56,60')
ap.add_argument('--sizes', default='50,100,200,400')
ap.add_argument('--repeats', type=int, default=3)
ap.add_argument('--joint', action='store_true')
ap.add_argument('--joint-sizes', default='100,200,400')
ap.add_argument('--threads', type=int, default=64)
a = ap.parse_args()
torch.set_num_threads(a.threads)
rng = np.random.default_rng(3)
n_win = 1200
t0 = time.time()
lines = []
say = lambda s='': (print(s, flush=True), lines.append(s))

F8, F32, B, clean, offs = features(a.value, n_win, blank_tokens())
Y = np.stack([F8, F32], 1).astype(np.float64)
NAMES = ['next 8', 'next 32']
order = np.argsort(offs, kind='stable')
train_w, val_w, test_w = order[:800], order[800:900], order[900:]
va, te = rows(val_w), rows(test_w)
cl = clean
va_c, te_c = va[cl[va]], te[cl[te]]
# consecutive test positions within a window (i-1, i), both in the test windows
te_prev = te.reshape(len(test_w), P)[:, :-1].reshape(-1)
te_next = te.reshape(len(test_w), P)[:, 1:].reshape(-1)
LAMS = [1e-2, 1e-1, 1.0, 10.0, 100.0, 1000.0, 1e4]
sizes = [int(x) for x in a.sizes.split(',')]

rec = np.fromfile(f'{a.acts}/samples.bin', dtype=SAMPLE)
keep = (rec['kind'] == 0) & (rec['pos'] >= P_LO) & (rec['pos'] <= P_HI)
idx = np.flatnonzero(keep)
r_ = rec[idx]
o_ = np.lexsort((r_['pos'], r_['seq']))
idx, r_ = idx[o_], r_[o_]
assert len(r_) == n_win * P and (r_['seq'].reshape(n_win, P) == np.arange(n_win)[:, None]).all()


def corr(x, y):
    x, y = x - x.mean(0), y - y.mean(0)
    return (x * y).sum(0) / np.sqrt((x * x).sum(0) * (y * y).sum(0))


def r2(y, p):
    return 1 - ((y - p) ** 2).sum(0) / ((y - y.mean(0)) ** 2).sum(0)


def fit_primal(X, wins):
    """ridge on the clean positions of `wins`; strength per target on val; returns predictions on all test rows"""
    tr = rows(wins)
    tr = tr[cl[tr]]
    Xt = X[tr]
    mu, sd = Xt.mean(0), Xt.std(0) + 1e-6
    Zt = ((Xt - mu) / sd).double()
    A = Zt.T @ Zt
    ym = torch.from_numpy(Y[tr]).mean(0)
    Bm = Zt.T @ (torch.from_numpy(Y[tr]) - ym)
    Zv = ((X[va_c] - mu) / sd).double()
    Ze = ((X[te] - mu) / sd).double()
    best = [None, None]
    for lam in LAMS:
        M = A.clone()
        M.diagonal().add_(lam * len(tr))
        W = torch.cholesky_solve(Bm, torch.linalg.cholesky(M))
        sv = r2(Y[va_c], (Zv @ W + ym).numpy())
        pe = (Ze @ W + ym).numpy()
        for j in range(2):
            if best[j] is None or sv[j] > best[j][0]:
                best[j] = (sv[j], pe[:, j])
    return np.stack([b[1] for b in best], 1)  # [len(te), 2], aligned with te


def summarize(label, res):
    """res[n] = list of (f_A, f_B) test predictions; prints reliability of f and df, R2, and the fit n/(n+c)"""
    out = {}
    pos_in_te = {r: i for i, r in enumerate(te)}
    ip, inx = np.array([pos_in_te[r] for r in te_prev]), np.array([pos_in_te[r] for r in te_next])
    ic = np.array([pos_in_te[r] for r in te_c])
    for n, pairs in res.items():
        rf, rd, rr = [], [], []
        for fa, fb in pairs:
            rf.append(corr(fa, fb))
            rd.append(corr(fa[inx] - fa[ip], fb[inx] - fb[ip]))
            rr.append((r2(Y[te_c], fa[ic]) + r2(Y[te_c], fb[ic])) / 2)
        out[n] = {'rel_f': np.mean(rf, 0).tolist(), 'rel_df': np.mean(rd, 0).tolist(), 'r2': np.mean(rr, 0).tolist(),
                  'rel_df_sd': np.std(rd, 0).tolist(), 'n_pairs': len(pairs)}
    fitc = {}
    for j, nm in enumerate(NAMES):
        ns = np.array(sorted(out))
        rho = np.array([out[n]['rel_df'][j] for n in ns])
        ok = (rho > 0) & (rho < 1)
        # rho = n / (n + c)  ->  c = n (1 - rho) / rho, pooled by least squares on 1/rho = 1 + c/n
        c = float(np.sum((1 / rho[ok] - 1) * (1 / ns[ok])) / np.sum(1 / ns[ok] ** 2)) if ok.any() else float('nan')
        fitc[nm] = {'c_windows': c, 'n_for_0.8': 4 * c, 'n_for_0.9': 9 * c}
    say()
    say(f'== {label}')
    say(f'  {"windows":>8s} | ' + ' | '.join(f'{nm}: R2 f   rel f  rel df' for nm in NAMES))
    for n in sorted(out):
        o = out[n]
        say(f'  {n:8d} | ' + ' | '.join(f'      {o["r2"][j]:.3f}  {o["rel_f"][j]:.3f}  {o["rel_df"][j]:.3f}' for j in range(2)))
    for nm in NAMES:
        f = fitc[nm]
        say(f'  {nm}: rel df ~ n / (n + {f["c_windows"]:.0f}); 0.8 at ~{f["n_for_0.8"]:.0f} windows, 0.9 at ~{f["n_for_0.9"]:.0f} '
            f'(each window ~{P} positions; we have 800 training windows)')
    return {'by_size': {str(k): v for k, v in out.items()}, 'fit': fitc}


results = {'layers': {}, 'sizes': sizes}
say(f'Reliability of a difficulty-forecast probe and of its token-to-token change, vs training windows. ({time.time() - t0:.0f} s)')
for L in [int(x) for x in a.layers.split(',')]:
    X = np.memmap(f'{a.acts}/acts_L{L:02d}.f16', dtype=np.float16, mode='r', shape=(len(rec), D))
    X = torch.from_numpy(np.asarray(X[idx], dtype=np.float32))
    res = {}
    for n in sizes:
        res[n] = []
        for rep in range(a.repeats if 2 * n < len(train_w) else max(1, a.repeats)):
            perm = rng.permutation(train_w)
            res[n].append((fit_primal(X, perm[:n]), fit_primal(X, perm[n:2 * n])))
    results['layers'][str(L)] = summarize(f'layer {L} ({time.time() - t0:.0f} s)', res)
    del X
    json.dump(results, open(f'{a.out}/forecast_reliability.json', 'w'), indent=1)

if a.joint:
    # all-layer probe: dual ridge on every other clean training position; kernels built per training subset
    jsizes = [int(x) for x in a.joint_sizes.split(',')]
    perms = {n: rng.permutation(train_w) for n in jsizes}
    subsets = {(n, h): (lambda w: (lambda t: t[cl[t]][::2])(rows(w)))(perms[n][h * n:(h + 1) * n]) for n in jsizes for h in (0, 1)}
    K = {k: None for k in subsets}
    Kv = {k: None for k in subsets}
    Ke = {k: None for k in subsets}
    for L in range(61):
        X = np.memmap(f'{a.acts}/acts_L{L:02d}.f16', dtype=np.float16, mode='r', shape=(len(rec), D))
        X = torch.from_numpy(np.asarray(X[idx], dtype=np.float32))
        for k, tr in subsets.items():
            mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-6
            Zt = (X[tr] - mu) / sd
            kt, kv, ke = Zt @ Zt.T, ((X[va_c] - mu) / sd) @ Zt.T, ((X[te] - mu) / sd) @ Zt.T
            K[k] = kt if K[k] is None else K[k].add_(kt)
            Kv[k] = kv if Kv[k] is None else Kv[k].add_(kv)
            Ke[k] = ke if Ke[k] is None else Ke[k].add_(ke)
        del X
        if L % 10 == 0:
            say(f'  joint kernels: layer {L} ({time.time() - t0:.0f} s)')
    res = {}
    for n in jsizes:
        preds = []
        for h in (0, 1):
            tr = subsets[(n, h)]
            Yt = torch.from_numpy(Y[tr]).float()
            ym = Yt.mean(0)
            best = [None, None]
            for lam in [1.0, 10.0, 100.0, 1000.0, 1e4, 1e5]:
                M = K[(n, h)].clone()
                M.diagonal().add_(lam * len(tr))
                al = torch.cholesky_solve(Yt - ym, torch.linalg.cholesky(M))
                sv = r2(Y[va_c], (Kv[(n, h)] @ al + ym).double().numpy())
                pe = (Ke[(n, h)] @ al + ym).double().numpy()
                for j in range(2):
                    if best[j] is None or sv[j] > best[j][0]:
                        best[j] = (sv[j], pe[:, j])
            preds.append(np.stack([b[1] for b in best], 1))
        res[n] = [tuple(preds)]
    results['joint'] = summarize(f'all 61 layers jointly ({time.time() - t0:.0f} s)', res)

json.dump(results, open(f'{a.out}/forecast_reliability.json', 'w'), indent=1)
open(f'{a.out}/forecast_reliability.txt', 'w').write('\n'.join(lines) + '\n')
say(f'-> {a.out}/forecast_reliability.json ({time.time() - t0:.0f} s)')
