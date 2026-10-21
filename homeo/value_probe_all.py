#!/usr/bin/env python3
"""All-layer value probe: the VL2 / H2 readouts from every layer's state at the current position, in one probe.

Inputs: runs/value/probe_capture_all.sh (block outputs of layers 0-60 on the 1200 VL1 windows, in RAM), the value-lens
targets (homeo-value output) and the forecast targets of value_forecast.py. Per position s (32-158):
  stakes, now   log |g_fut|, log |g_now| at layer 40 (VL2)
  next 8/32     difficulty: mean surprisal of the next 8 / 32 tokens after the next one, clean positions only (H2)
  added 8/32    what the state adds beyond an OLS baseline of what is known at s (entropy, recent surprisal, position),
                H2's definition: a probe fit to the baseline's residual, reported as R2(F, baseline + probe) - R2(F,
                baseline) on the test windows
Split as value_probe.py (contiguous blocks of fineweb offsets: 800 train / 100 val / 300 test windows). All positions of
the training windows are used. Ridge on standardized features, strength chosen on val, test used once.
  all layers  dual (kernel) ridge on all 61 layers' features concatenated (374,784 features; K = sum over layers of
              Z Z^T, the exact ridge solution in sample space). Every layer gets equal weight under one strength.
  per layer   primal ridge on each layer alone, as a profile of where the signal sits (nothing is selected from it)
Saved: OUT/probe_all.json (results, strengths, val R2, baseline coefficients), OUT/probe_all.txt, OUT/probe_all_pred.npz
(test predictions), OUT/probe_all_weights.f32 (all-layer weights in raw activation units: [n_targets][61][6144], then
[n_targets] biases; target = sum over layers of w_L . h_L + b; the "added" targets predict the baseline's residual) and
OUT/probe_layers_weights.f32 ([61][n_targets][6144] then [61][n_targets] biases). A self-check predicts the test windows
from the saved raw weights and compares with the fit's own predictions.

usage: value_probe_all.py [--acts /dev/shm/vlprobe_all] [--out /mnt/models/homeo/value_probe] [--layers 0-60] [--no-joint]
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
ap.add_argument('--layers', default='0-60')
ap.add_argument('--no-joint', action='store_true')
ap.add_argument('--threads', type=int, default=64)
a = ap.parse_args()
torch.set_num_threads(a.threads)
lo_, hi_ = map(int, a.layers.split('-'))
LAYERS = list(range(lo_, hi_ + 1))
n_win = 1200
t0 = time.time()
lines = []
say = lambda s='': (print(s, flush=True), lines.append(s))

# ---- targets ----
stakes = np.empty((n_win, P), np.float32)
now = np.empty((n_win, P), np.float32)
meta = json.load(open(f'{a.value}/meta.json'))
nL = len(meta['layers'])
for w in range(n_win):
    g = np.memmap(f'{a.value}/w{w:05d}.bin', dtype=np.float16, mode='r', shape=(nL, 3, P, D))
    now[w] = np.log(np.linalg.norm(np.asarray(g[0, 0], np.float32), axis=1) + 1e-6)
    stakes[w] = np.log(np.linalg.norm(np.asarray(g[0, 2], np.float32), axis=1) + 1e-6)
F8, F32, B, clean, offs = features(a.value, n_win, blank_tokens())
order = np.argsort(offs, kind='stable')
splits = (order[:800], order[800:900], order[900:])
tr, va, te = rows(splits[0]), rows(splits[1]), rows(splits[2])
cl = np.flatnonzero(clean)
RS = {False: (tr, va, te), True: tuple(np.intersect1d(r, cl) for r in (tr, va, te))}
Bx = np.hstack([B, np.ones((len(B), 1), np.float32)])
Bw = np.linalg.lstsq(Bx[RS[True][0]], np.stack([F8, F32], 1)[RS[True][0]], rcond=None)[0]
pb = Bx @ Bw
Y = np.stack([stakes.reshape(-1), now.reshape(-1), F8, F32, F8 - pb[:, 0], F32 - pb[:, 1]], 1).astype(np.float64)
NAMES = ['stakes', 'now', 'next 8', 'next 32', 'added 8', 'added 32']
CLEAN_T = [False, False, True, True, True, True]
ADDED = {4: 2, 5: 3}  # added target -> its difficulty target (column of Y); its baseline column is that minus 2
say(f'targets ready ({time.time() - t0:.0f} s): train {len(tr)} positions, val {len(va)}, test {len(te)}; '
    f'clean {len(RS[True][0])}/{len(RS[True][1])}/{len(RS[True][2])}')


def r2(y, p):
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def demean_win(v, rws):
    win = rws // P
    out = v.copy()
    for wv in np.unique(win):
        m = win == wv
        out[m] -= out[m].mean()
    return out


def r2w(y, p, rws):
    """R2 with each window's mean removed from target and prediction"""
    return r2(demean_win(y, rws), demean_win(p, rws))


def score(j, pt, rte):
    """test score of target j's predictions pt on rows rte: R2 and within-window R2; for the added targets H2's
    definition, R2(F, baseline + probe) - R2(F, baseline) (and the residual's own R2 as partial_r2)"""
    if j in ADDED:
        f = ADDED[j]
        base = pb[rte, f - 2]
        return {'test': r2(Y[rte, f], base + pt) - r2(Y[rte, f], base),
                'within': r2w(Y[rte, f], base + pt, rte) - r2w(Y[rte, f], base, rte),
                'partial_r2': r2(Y[rte, j], pt)}
    return {'test': r2(Y[rte, j], pt), 'within': r2w(Y[rte, j], pt, rte)}


base_r2 = {NAMES[f]: r2(Y[RS[True][2], f], pb[RS[True][2], f - 2]) for f in (2, 3)}
say(f'baseline (entropy, recent surprisal, position) test R2: next 8 {base_r2["next 8"]:.3f}, next 32 {base_r2["next 32"]:.3f}')

# ---- activations ----
rec = np.fromfile(f'{a.acts}/samples.bin', dtype=SAMPLE)
keep = (rec['kind'] == 0) & (rec['pos'] >= P_LO) & (rec['pos'] <= P_HI)
idx = np.flatnonzero(keep)
r_ = rec[idx]
o_ = np.lexsort((r_['pos'], r_['seq']))
idx, r_ = idx[o_], r_[o_]
assert len(r_) == n_win * P and (r_['seq'].reshape(n_win, P) == np.arange(n_win)[:, None]).all()
LAMS = [float(10 ** (e / 2)) for e in range(-6, 7)]          # per layer: 1e-3 .. 1e3, half-decade steps
JLAMS_COARSE = [1.0, 10.0, 100.0, 1000.0]                   # all layers: then the half-decade neighbours of each best


def load(L):
    X = np.memmap(f'{a.acts}/acts_L{L:02d}.f16', dtype=np.float16, mode='r', shape=(len(rec), D))
    return torch.from_numpy(np.asarray(X[idx], dtype=np.float32))


per_layer, stats = {}, {}
WL = np.zeros((len(LAYERS), len(NAMES), D), np.float32)
BL = np.zeros((len(LAYERS), len(NAMES)), np.float32)
n_tr = len(tr)
Ktr = None if a.no_joint else torch.zeros((n_tr, n_tr), dtype=torch.float32)
Kva = None if a.no_joint else torch.zeros((len(va), n_tr), dtype=torch.float32)
Kte = None if a.no_joint else torch.zeros((len(te), n_tr), dtype=torch.float32)
BLK = 16384
blocks = [(s, min(s + BLK, n_tr)) for s in range(0, n_tr, BLK)]
for li, L in enumerate(LAYERS):
    tl = time.time()
    X = load(L)
    mu = X[tr].mean(0)
    sd = X[tr].std(0) + 1e-6
    stats[L] = (mu, sd)
    Z = (X - mu) / sd
    del X
    # per-layer primal ridge, both row sets
    res = {}
    for cflag in (False, True):
        rtr, rva, rte = RS[cflag]
        Zt = Z[rtr].double()
        A = Zt.T @ Zt
        n = len(rtr)
        js = [j for j in range(len(NAMES)) if CLEAN_T[j] == cflag]
        Yt = torch.from_numpy(Y[rtr][:, js])
        ym = Yt.mean(0)
        Bm = Zt.T @ (Yt - ym)
        Zv, Ze = Z[rva].double(), Z[rte].double()
        pv, pe, Ws = {}, {}, {}
        for lam in LAMS:
            M = A.clone()
            M.diagonal().add_(lam * n)
            W = torch.cholesky_solve(Bm, torch.linalg.cholesky(M))
            pv[lam], pe[lam], Ws[lam] = (Zv @ W + ym).numpy(), (Ze @ W + ym).numpy(), W
        for k, j in enumerate(js):
            lam = max(LAMS, key=lambda l_: r2(Y[rva, j], pv[l_][:, k]))
            res[NAMES[j]] = dict(score(j, pe[lam][:, k], rte), lam=lam, val=r2(Y[rva, j], pv[lam][:, k]),
                                 lam_edge=lam in (LAMS[0], LAMS[-1]))
            w = (Ws[lam][:, k].float() / sd).numpy()
            WL[li, j], BL[li, j] = w, float(ym[k]) - float(w.astype(np.float64) @ mu.numpy().astype(np.float64))
            if L == 40:
                res[NAMES[j]]['_pred'] = pe[lam][:, k]
        del Zt, A, Zv, Ze, Ws
    per_layer[L] = res
    # all-layer kernel blocks: lower triangle of train x train (filled by symmetry later), val and test x train
    if not a.no_joint:
        Zt = Z[tr]
        for bi, (i0, i1) in enumerate(blocks):
            for (j0, j1) in blocks[:bi + 1]:
                Ktr[i0:i1, j0:j1].add_(Zt[i0:i1] @ Zt[j0:j1].T)
        Kva.add_(Z[va] @ Zt.T)
        Kte.add_(Z[te] @ Zt.T)
        del Zt
    del Z
    say(f'L{L:02d}: ' + ', '.join(f'{nm} {res[nm]["test"]:.3f}' for nm in NAMES) + f'  ({time.time() - tl:.0f} s, total {time.time() - t0:.0f} s)')

out = {'layers': LAYERS, 'names': NAMES, 'baseline_r2': base_r2,
       'baseline_coef': {'features': ['entropy', 'mean surprisal last 32', 'current surprisal', 'mean surprisal last 8',
                                      'position / 192', 'intercept'], 'next 8': Bw[:, 0].tolist(), 'next 32': Bw[:, 1].tolist()},
       'n_train': n_tr, 'split': 'fineweb offset blocks 800 / 100 / 300 windows, all positions',
       'per_layer': {str(L): {nm: {k: v for k, v in r.items() if k != '_pred'} for nm, r in res.items()} for L, res in per_layer.items()}}
preds = {'test_rows': te, 'test_rows_clean': RS[True][2], 'Y_test': Y[te], 'Y_test_clean': Y[RS[True][2]]}
if 40 in per_layer:
    for nm, r in per_layer[40].items():
        preds[f'L40 {nm}'] = r['_pred']
np.concatenate([WL.reshape(-1), BL.reshape(-1)]).tofile(f'{a.out}/probe_layers_weights.f32')
out['layers_weights'] = {'file': f'{a.out}/probe_layers_weights.f32', 'layout': f'f32 [{len(LAYERS)}][n_targets][6144] then '
                         f'[{len(LAYERS)}][n_targets] bias; target = w . h + b (raw block output)'}

# ---- the all-layer probe ----
if not a.no_joint:
    for bi, (i0, i1) in enumerate(blocks):  # fill the upper triangle from the lower
        for (j0, j1) in blocks[:bi]:
            Ktr[j0:j1, i0:i1] = Ktr[i0:i1, j0:j1].T
    pos_tr = {r: i for i, r in enumerate(tr)}
    pos_va = {r: i for i, r in enumerate(va)}
    pos_te = {r: i for i, r in enumerate(te)}
    joint, alphas = {}, {}
    for cflag in (False, True):
        rtr, rva, rte = RS[cflag]
        it = np.array([pos_tr[r] for r in rtr])
        iv = np.array([pos_va[r] for r in rva])
        ie = np.array([pos_te[r] for r in rte])
        Ks = Ktr if len(it) == n_tr else Ktr[it][:, it]
        Kv_, Ke_ = Kva[iv][:, it], Kte[ie][:, it]
        n = len(it)
        js = [j for j in range(len(NAMES)) if CLEAN_T[j] == cflag]
        Yt = torch.from_numpy(Y[rtr][:, js]).float()
        ym = Yt.mean(0)
        sols, pv, pe = {}, {}, {}

        def solve(lam):
            if lam in sols:
                return
            M = Ks.clone()
            M.diagonal().add_(lam * n)
            # float32 Cholesky: the ridge term on the diagonal keeps the system well conditioned (audit: |dR2| <= 1e-6)
            sols[lam] = torch.cholesky_solve(Yt - ym, torch.linalg.cholesky(M))
            del M
            pv[lam] = (Kv_ @ sols[lam] + ym).double().numpy()
            pe[lam] = (Ke_ @ sols[lam] + ym).double().numpy()
            say(f'  all layers, {"clean" if cflag else "all"} rows, lambda {lam:g}: val R2 ' +
                ', '.join(f'{NAMES[j]} {r2(Y[rva, j], pv[lam][:, k]):.4f}' for k, j in enumerate(js)) + f' ({time.time() - t0:.0f} s)')

        for lam in JLAMS_COARSE:
            solve(lam)
        best = {k: max(sols, key=lambda l_: r2(Y[rva, j], pv[l_][:, k])) for k, j in enumerate(js)}
        for lam in sorted({b * f for b in best.values() for f in (10 ** -0.5, 10 ** 0.5)}):
            solve(lam)
        for k, j in enumerate(js):
            lam = max(sols, key=lambda l_: r2(Y[rva, j], pv[l_][:, k]))
            joint[NAMES[j]] = dict(score(j, pe[lam][:, k], rte), lam=lam, val=r2(Y[rva, j], pv[lam][:, k]),
                                   lam_edge=lam in (min(sols), max(sols)))
            preds[f'all {NAMES[j]}'] = pe[lam][:, k]
            alphas[j] = (it, sols[lam][:, k].clone(), float(ym[k]))
        del Ks, Kv_, Ke_, sols
    out['joint'] = joint
    del Ktr, Kva, Kte

    # weights in raw units, w_L = (Z_L,train^T alpha) / sd_L, and the self-check on the test windows
    WJ = np.zeros((len(NAMES), len(LAYERS), D), np.float32)
    bj = np.array([alphas[j][2] for j in range(len(NAMES))], np.float64)
    pos_in_te = {r: i for i, r in enumerate(te)}
    pchk = {j: np.zeros(len(te)) for j in range(len(NAMES))}
    for li, L in enumerate(LAYERS):
        X = load(L)
        mu, sd = stats[L]
        Zt = (X[tr] - mu) / sd
        Xte = X[te].double().numpy()
        for j in range(len(NAMES)):
            it, al, _ = alphas[j]
            w = ((Zt[it].T @ al) / sd).numpy()
            WJ[j, li] = w
            bj[j] -= float(w.astype(np.float64) @ mu.numpy().astype(np.float64))
            pchk[j] += Xte @ w.astype(np.float64)
        del X, Zt
    with open(f'{a.out}/probe_all_weights.f32', 'wb') as fh:
        WJ.reshape(-1).tofile(fh)
        bj.astype(np.float32).tofile(fh)
    chk = {}
    for j in range(len(NAMES)):
        rte = RS[CLEAN_T[j]][2]
        p_raw = (pchk[j] + bj[j])[np.array([pos_in_te[r] for r in rte])]
        chk[NAMES[j]] = float(np.abs(p_raw - preds[f'all {NAMES[j]}']).max())
    out['weights'] = {'file': f'{a.out}/probe_all_weights.f32', 'layout': f'f32 [n_targets][{len(LAYERS)}][6144] then [n_targets] bias; '
                      'target = sum_L w_L . h_L + b (raw block outputs); the added targets predict the residual of baseline_coef',
                      'selfcheck_max_abs_diff': chk}
    say(f'self-check, raw weights vs kernel predictions on the test windows (max |diff|): ' + ', '.join(f'{k} {v:.2e}' for k, v in chk.items()))

say()
say('test R2 (within-window in parentheses); "added" = R2(baseline + probe) - R2(baseline), as H2')
say(f'{"probe":12s} ' + ' '.join(f'{nm:>17s}' for nm in NAMES))
for lab, rr in [('layer 40', per_layer.get(40)), ('all layers', out.get('joint'))]:
    if rr:
        say(f'{lab:12s} ' + ' '.join(f'{rr[nm]["test"]:7.3f} ({rr[nm]["within"]:6.3f})' for nm in NAMES))
if 'joint' in out:
    say('all-layer strengths: ' + ', '.join(f'{nm} {out["joint"][nm]["lam"]:g}' + (' (grid edge)' if out['joint'][nm]['lam_edge'] else '') for nm in NAMES))
json.dump(out, open(f'{a.out}/probe_all.json', 'w'), indent=1)
np.savez(f'{a.out}/probe_all_pred.npz', **{k.replace(' ', '_'): v for k, v in preds.items()})
open(f'{a.out}/probe_all.txt', 'w').write('\n'.join(lines) + '\n')
say(f'-> {a.out}/probe_all.json ({time.time() - t0:.0f} s)')
