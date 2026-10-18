#!/usr/bin/env python3
"""Value probe (VL2): can the value lens be read linearly off the layer-40 residual stream?

Targets per position s (homeo-value output, layer 40):
  stakes     log(|g_fut| + 1e-6), g_fut = sum_{k=1..32} d l_{s+k} / d h_s
  now        log(|g_now| + 1e-6), g_now = d l_s / d h_s
  temp fut   g_fut . u_temp1.3 (S2(c) optimized vector), nats per push of 0.1 x the residual norm
  temp now   g_now . u_temp1.3
  band fut   g_fut . u_band0.5
  pc1..pc5   g_fut projected on the top principal directions of g_fut (fit on training windows)
  level      l_s, log-likelihood of the actual next token
  entropy    H(p_s), sanity check (a function of h_s at the last layer)
Inputs: the activations h_s after block 40 (homeo-capture on the same windows, probe_capture.sh).

Ridge regression on standardized h_s: fit on 800 windows, ridge strength chosen on 100, refit on both, tested
on 300. Default split: contiguous blocks of fineweb offsets (no document in two splits); --split index uses
windows 0-799 / 800-899 / 900-1199. Reported per target: test R^2 overall and within window (window means removed
from both target and prediction), and the R^2 of two baselines: OLS on entropy, the current token's
surprisal and position, and the training mean per current token. The probes are then applied to the scenario windows (loops, fiction) without
refitting.

Writes OUT/probe.json (summary) and OUT/probe_L40.f32 ([n_targets][n_embd] weights in raw-h units, then
[n_targets] biases), so that target = W @ h + b.

usage: value_probe.py [--value /mnt/models/homeo/value] [--probe /mnt/models/homeo/value_probe]
"""
import argparse
import json

import torch
import numpy as np

H = '/mnt/models/homeo'
RESID40 = 261.1
P_LO, P_HI = 32, 158
P = P_HI - P_LO + 1
D = 6144
TRAIN, VAL, TEST = range(0, 800), range(800, 900), range(900, 1200)
SAMPLE = np.dtype([('seq', '<i4'), ('pos', '<i4'), ('token', '<i4'), ('kind', '<i4'), ('bin', '<i4'),
                   ('rank_prev', '<i4'), ('surprisal', '<f4'), ('entropy_prev', '<f4'), ('entropy', '<f4'),
                   ('pad', '<f4', 3)])
N_PC = 5


def unit(v):
    return v / np.linalg.norm(v)


def load_acts(d, n_win, layer=40):
    """h_s for s in [P_LO, P_HI] per window, plus baseline features."""
    rec = np.fromfile(f'{d}/samples.bin', dtype=SAMPLE)
    acts = np.memmap(f'{d}/acts_L{layer:02d}.f16', dtype=np.float16, mode='r', shape=(len(rec), D))
    keep = (rec['kind'] == 0) & (rec['pos'] >= P_LO) & (rec['pos'] <= P_HI)
    idx = np.flatnonzero(keep)
    r = rec[idx]
    order = np.lexsort((r['pos'], r['seq']))
    idx, r = idx[order], r[order]
    assert len(r) == n_win * P and (r['seq'].reshape(n_win, P) == np.arange(n_win)[:, None]).all()
    X = np.asarray(acts[idx], dtype=np.float32)
    base = np.stack([r['entropy'], r['surprisal'], r['pos'] / 192.0], 1).astype(np.float32)
    return X, base, r['token'].copy()


def load_grads(d, n_win):
    """g_now, g_fut at layer 40 (index 0 of the slot layers) and the next-token log-likelihood."""
    meta = json.load(open(f'{d}/meta.json'))
    assert meta['layers'][0] == 40 and meta['positions'] == [P_LO, P_HI]
    L = len(meta['layers'])
    now = np.empty((n_win, P, D), np.float32)
    fut = np.empty((n_win, P, D), np.float32)
    level = np.empty((n_win, P), np.float32)
    for w in range(n_win):
        a = np.memmap(f'{d}/w{w:05d}.bin', dtype=np.float16, mode='r', shape=(L, 3, P, D))
        now[w] = a[0, 0]
        fut[w] = a[0, 2]
        level[w] = np.array(json.load(open(f'{d}/w{w:05d}.json'))['ll'])[P_LO:P_HI + 1]
    return now.reshape(-1, D), fut.reshape(-1, D), level.reshape(-1)


def targets(now, fut, level, entropy, u_temp, u_band, pcs):
    s = 0.1 * RESID40
    cols = {'stakes': np.log(np.linalg.norm(fut, axis=1) + 1e-6), 'now': np.log(np.linalg.norm(now, axis=1) + 1e-6),
            'temp fut': fut @ u_temp * s, 'temp now': now @ u_temp * s, 'band fut': fut @ u_band * s}
    for i in range(N_PC):
        cols[f'pc{i + 1}'] = fut @ pcs[i] * s
    cols['level'] = level
    cols['entropy'] = entropy
    return list(cols), np.stack(list(cols.values()), 1).astype(np.float32)


def rows(wins):
    return np.concatenate([np.arange(w * P, (w + 1) * P) for w in wins])


class Ridge:
    def __init__(self, X):
        self.mu = X.mean(0)
        self.sd = X.std(0) + 1e-6
        Z = torch.from_numpy((X - self.mu) / self.sd).double()
        self.e, self.V = torch.linalg.eigh(Z.T @ Z)
        self.Z, self.n = Z, len(X)

    def fit(self, Y, lam):
        y_mu = Y.mean(0)
        ZtY = self.Z.T @ torch.from_numpy(Y - y_mu).double()
        W = self.V @ ((self.V.T @ ZtY) / (self.e + lam * self.n)[:, None])
        return W.numpy(), y_mu

    def predict(self, X, W, y_mu):
        return ((X - self.mu) / self.sd) @ W.astype(np.float32) + y_mu


def r2(y, p):
    return 1.0 - ((y - p) ** 2).sum(0) / ((y - y.mean(0)) ** 2).sum(0)


def within(y, n_win):
    y = y.reshape(n_win, P, -1)
    return (y - y.mean(1, keepdims=True)).reshape(n_win * P, -1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--value', default=f'{H}/value')
    ap.add_argument('--scen', default=f'{H}/value_scen')
    ap.add_argument('--probe', default=f'{H}/value_probe')
    ap.add_argument('--split', default='offset', choices=['index', 'offset'],
                    help='offset: train/val/test are contiguous blocks of the fineweb file, so no document is split')
    a = ap.parse_args()
    torch.set_num_threads(48)
    n_win = 1200
    u_temp = unit(np.fromfile(f'{H}/s2opt/vec_temp1.3_opt2_L40.f32', dtype=np.float32))
    u_band = unit(np.fromfile(f'{H}/s2opt/vec_p0.5_opt2_L40.f32', dtype=np.float32))

    X, base, tok = load_acts(f'{a.probe}/main', n_win)
    print(f'activations {X.shape}, mean |h| {np.linalg.norm(X, axis=1).mean():.1f} (S2(c) sweep: {RESID40})')
    now, fut, level = load_grads(a.value, n_win)
    splits = (TRAIN, VAL, TEST)
    if a.split == 'offset':
        offs = [json.load(open(f'{a.value}/w{w:05d}.json'))['offset'] for w in range(n_win)]
        order = np.argsort(offs, kind='stable')
        splits = (order[:800], order[800:900], order[900:])
    tr = rows(splits[0])
    f = torch.from_numpy(fut[tr]).double()
    pcs = torch.linalg.eigh(f.T @ f / len(tr))[1].flip(1)[:, :N_PC].T.numpy().astype(np.float32)
    del f
    names, Y = targets(now, fut, level, base[:, 0], u_temp, u_band, pcs)
    del now, fut

    va, te, trva = rows(splits[1]), rows(splits[2]), rows(list(splits[0]) + list(splits[1]))
    rg = Ridge(X[tr])
    lams = [1e-3, 1e-2, 1e-1, 1.0, 10.0, 100.0, 1000.0]
    best = {}
    for lam in lams:
        W, mu = rg.fit(Y[tr], lam)
        for j, s in enumerate(r2(Y[va], rg.predict(X[va], W, mu))):
            if names[j] not in best or s > best[names[j]][1]:
                best[names[j]] = (lam, s)
    del rg
    rg = Ridge(X[trva])
    W = np.zeros((D, len(names)), np.float32)
    mu = np.zeros(len(names), np.float32)
    for lam in sorted({b[0] for b in best.values()}):
        Wl, mul = rg.fit(Y[trva], lam)
        for j, n in enumerate(names):
            if best[n][0] == lam:
                W[:, j], mu[j] = Wl[:, j], mul[j]
    Xmu, Xsd = rg.mu, rg.sd
    del rg

    def predict(Xq):
        return ((Xq - Xmu) / Xsd) @ W + mu

    # baseline: entropy, current-token surprisal, position (ordinary least squares)
    B = np.hstack([base, np.ones((len(base), 1), np.float32)])
    Bw = np.linalg.lstsq(B[trva], Y[trva], rcond=None)[0]
    pt, bt = predict(X[te]), B[te] @ Bw
    # token baseline: training mean of each target per current token (shrunk toward the global mean)
    k = 5.0
    cnt = np.bincount(tok[trva], minlength=tok.max() + 1).astype(np.float32)
    g = Y[trva].mean(0)
    tt = np.stack([(np.bincount(tok[trva], weights=Y[trva, j], minlength=len(cnt)) + k * g[j]) / (cnt + k)
                   for j in range(len(names))], 1)[tok[te]]
    n_te = len(TEST)
    res = dict(split=a.split, names=names, lam={n: best[n][0] for n in names}, val_r2={n: float(best[n][1]) for n in names},
               test_r2=dict(zip(names, map(float, r2(Y[te], pt)))),
               test_r2_within=dict(zip(names, map(float, r2(within(Y[te], n_te), within(pt, n_te))))),
               base_r2=dict(zip(names, map(float, r2(Y[te], bt)))),
               base_r2_within=dict(zip(names, map(float, r2(within(Y[te], n_te), within(bt, n_te))))),
               tok_r2=dict(zip(names, map(float, r2(Y[te], tt)))),
               sd=dict(zip(names, map(float, Y[te].std(0)))))
    print(f'\n  {"target":10s} {"lambda":>7s} {"test R2":>8s} {"within":>8s} {"base R2":>8s} {"within":>8s} {"token R2":>8s} {"sd":>8s}')
    for n in names:
        print(f'  {n:10s} {res["lam"][n]:7.0e} {res["test_r2"][n]:8.3f} {res["test_r2_within"][n]:8.3f} '
              f'{res["base_r2"][n]:8.3f} {res["base_r2_within"][n]:8.3f} {res["tok_r2"][n]:8.3f} {res["sd"][n]:8.4f}')

    # scenario windows: probe trained on fineweb, applied without refitting
    manifest = json.load(open(f'{a.scen}/manifest.json'))
    ns = len(manifest)
    Xs, bs, _ = load_acts(f'{a.probe}/scen', ns)
    nows, futs, levs = load_grads(f'{a.scen}/out', ns)
    _, Ys = targets(nows, futs, levs, bs[:, 0], u_temp, u_band, pcs)
    ps = predict(Xs)
    loop = np.zeros((ns, P), bool)
    loop[:, 100 - P_LO:] = True
    res['scenarios'] = {}
    show = ['stakes', 'now', 'temp fut', 'level']
    print(f'\n  scenarios (loop region = positions 100-158), actual / probe:')
    print(f'  {"group":28s} {"n":>3s}  ' + '  '.join(f'{n:>15s}' for n in show))
    groups = [('fiction', 'fiction', False), ('fiction, positions 100-158', 'fiction', True),
              ('phrase loop, loop region', 'phrase loop', True), ('token loop, loop region', 'token loop', True)]
    for label, scen, in_loop in groups:
        ws = [i for i, m in enumerate(manifest) if m['scenario'] == scen]
        m = np.zeros((ns, P), bool)
        m[ws] = loop[ws] if in_loop else True
        m = m.reshape(-1)
        yt, yp = Ys[m], ps[m]
        cells = {n: (float(yt[:, names.index(n)].mean()), float(yp[:, names.index(n)].mean())) for n in names}
        within_r2 = dict(zip(names, map(float, r2(yt, yp))))
        res['scenarios'][label] = dict(n=len(ws), mean=cells, r2=within_r2)
        print(f'  {label:28s} {len(ws):3d}  ' + '  '.join(f'{cells[n][0]:+7.3f}/{cells[n][1]:+7.3f}' for n in show))
    cells = {n: (float(Y[te][:, names.index(n)].mean()), float(pt[:, names.index(n)].mean())) for n in names}
    res['scenarios']['fineweb test windows'] = dict(n=n_te, mean=cells)
    print(f'  {"fineweb test windows":28s} {n_te:3d}  ' + '  '.join(f'{cells[n][0]:+7.3f}/{cells[n][1]:+7.3f}' for n in show))

    # weights in raw-h units: target = (W / sd)^T h + (mu - (W / sd)^T Xmu)
    Wr = (W / Xsd[:, None]).T.astype(np.float32)
    br = (mu - Wr @ Xmu).astype(np.float32)
    np.concatenate([Wr.reshape(-1), br]).tofile(f'{a.probe}/probe_L40.f32')
    res['weights'] = dict(file=f'{a.probe}/probe_L40.f32', layout='f32 [n_targets][n_embd] then [n_targets] bias',
                          layer=40, n_embd=D)
    json.dump(res, open(f'{a.probe}/probe.json', 'w'), indent=1)
    print(f'\nwrote {a.probe}/probe.json and probe_L40.f32')


if __name__ == '__main__':
    main()
