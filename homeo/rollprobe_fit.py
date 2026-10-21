#!/usr/bin/env python3
"""All-layer difficulty-forecast probe on rollouts and natural text (notes: "Plan for the overnight run").

Data: runs/rollprobe/run.sh chunks in /dev/shm/rollprobe/cK (homeo-capture: block outputs of layers 0-60 at the probe
sites, labels at every position), sequences listed in OUT/capture_cK.jsonl (75% pure ancestral rollouts, 25% natural
windows; 70% English, 15% Chinese, 15% nine other languages). Each site is a pair of consecutive positions (d, d+1).
Targets at a site s (the state after token s; c_t = surprisal of token t under the model):
  next 1        c_{s+1}, the next token's surprisal
  next 8/32/128 difficulty: mean c over the 8 / 32 / 128 tokens after the next one (c_{s+2} ...)
  added 32/128  what the state adds beyond an OLS baseline of what is known at s (next-token entropy, current
                surprisal, mean surprisal of the last 8 / 32 / 128 tokens, log context length): a probe of the
                baseline's residual, reported as R2(baseline + probe) - R2(baseline) (H2's definition)
Split by sequence, stratified by language group and kind: 70% train / 10% val / 20% test. Ridge on standardized
features; strength per target on val; test used once.
  all layers  dual ridge on all 61 layers concatenated (374,784 features; K = sum over layers of Z Z^T)
  per layer   primal ridge on each layer alone (profile)
Forecast-change reliability (all-layer probe, strengths FIXED at the full probe's choice and one decade either side):
probes on disjoint quarters and halves of the training sequences predict the test pairs; agreement of their forecast
change df = f(s+1) - f(s) and of the TD error delta = -c_{s+1} - 128 df (reward log p, value -128 f) estimates the
reliability of a probe trained on that many sequences (parallel measures correlate at their reliability).
Saved in OUT: rollprobe.json / .txt, rollprobe_rows.npz (every row: sequence, position, language, kind, split, targets,
baseline features, all-layer predictions on val/test), rollprobe_weights.f32 (all-layer, raw units: f32
[n_targets][61][6144] then [n_targets] bias; added targets predict the baseline residual), rollprobe_layers_weights.f32
([61][n_targets][6144] then [61][n_targets]). A self-check predicts the test rows from the saved raw weights.

usage: rollprobe_fit.py [--acts /dev/shm/rollprobe] [--seqs /mnt/models/homeo/rollouts2] [--out /mnt/models/homeo/rollprobe]
"""
import argparse
import glob
import json
import os
import time

import torch
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('--acts', default='/dev/shm/rollprobe')
ap.add_argument('--seqs', default='/mnt/models/homeo/rollouts2')
ap.add_argument('--out', default='/mnt/models/homeo/rollprobe')
ap.add_argument('--threads', type=int, default=64)
ap.add_argument('--no-layers', action='store_true', help='skip the per-layer profile')
a = ap.parse_args()
torch.set_num_threads(a.threads)
os.makedirs(a.out, exist_ok=True)
D, NL = 6144, 61
SAMPLE = np.dtype([('seq', '<i4'), ('pos', '<i4'), ('token', '<i4'), ('kind', '<i4'), ('bin', '<i4'), ('rank_prev', '<i4'),
                   ('surprisal', '<f4'), ('entropy_prev', '<f4'), ('entropy', '<f4'), ('pad', '<f4', 3)])
LABEL = np.dtype([('seq', '<i4'), ('pos', '<i4'), ('token', '<i4'), ('rank_prev', '<i4'), ('surprisal', '<f4'),
                  ('entropy_prev', '<f4'), ('entropy', '<f4'), ('pad', '<f4')])
t0 = time.time()
lines = []
say = lambda s='': (print(s, flush=True), lines.append(s))

# ---- rows, labels, targets ----
chunks = sorted(int(p.rsplit('/c', 1)[1]) for p in glob.glob(f'{a.acts}/c*') if os.path.exists(f'{p}/meta.json'))
R = {k: [] for k in ('chunk', 'srow', 'seq', 'pos', 'rid', 'lang', 'kind', 'n_end', 'ent', 'cur', 'm8', 'm32', 'm128', 'logd',
                     'next 1', 'next 8', 'next 32', 'next 128', 'pair')}
for k in chunks:
    seqs = [json.loads(l) for l in open(f'{a.seqs}/capture_c{k}.jsonl', encoding='utf-8')]
    lab = np.fromfile(f'{a.acts}/c{k}/labels.bin', dtype=LABEL)
    smp = np.fromfile(f'{a.acts}/c{k}/samples.bin', dtype=SAMPLE)
    starts = np.flatnonzero(lab['pos'] == 0)
    assert len(starts) == len(seqs) and (smp['kind'] == 0).all()
    bounds = list(starts) + [len(lab)]
    for i, s in enumerate(smp):
        q = s['seq']
        L = lab[bounds[q]:bounds[q + 1]]
        c = L['surprisal'].astype(np.float64)  # c[t] = surprisal of token t; c[0] = nan
        d = int(s['pos'])
        assert L['pos'][d] == d and L['token'][d] == s['token'] and d + 129 < len(L)
        R['chunk'].append(k); R['srow'].append(i); R['seq'].append(q); R['pos'].append(d)
        meta = seqs[q]
        R['rid'].append(meta['rid']); R['lang'].append(meta['lang']); R['kind'].append(meta['kind']); R['n_end'].append(meta['n_end'])
        R['ent'].append(float(L['entropy'][d])); R['cur'].append(float(c[d]))
        for K in (8, 32, 128):
            R[f'm{K}'].append(float(c[max(1, d - K + 1):d + 1].mean()))
        R['logd'].append(float(np.log(d + 1)))
        R['next 1'].append(float(c[d + 1]))
        for K in (8, 32, 128):
            R[f'next {K}'].append(float(c[d + 2:d + 2 + K].mean()))
        R['pair'].append(0)
R = {k: np.array(v) for k, v in R.items()}
N = len(R['pos'])
# pair index: rows (d, d+1) of the same sequence
key = R['chunk'].astype(np.int64) * 10**9 + R['seq'].astype(np.int64) * 10**4 + R['pos']
order = np.argsort(key)
nxt = np.full(N, -1)
ks = key[order]
hit = np.flatnonzero(ks[1:] == ks[:-1] + 1)
nxt[order[hit]] = order[hit + 1]
R['pair'] = nxt  # row index of position d+1 for the first row of a pair, else -1
LG = np.where(R['lang'] == 'eng_Latn', 'en', np.where(R['lang'] == 'cmn_Hani', 'zh', 'other'))

# split by sequence, stratified by language group and kind
uid = R['chunk'].astype(np.int64) * 100000 + R['seq']
seq_ids, first = np.unique(uid, return_index=True)
rng = np.random.default_rng(20261021)
split_of = {}
for g in ('en', 'zh', 'other'):
    for kd in ('rollout', 'pretrain'):
        ss = seq_ids[(LG[first] == g) & (R['kind'][first] == kd)]
        ss = ss[rng.permutation(len(ss))]
        n_tr, n_va = int(round(0.7 * len(ss))), int(round(0.1 * len(ss)))
        for i, s in enumerate(ss):
            split_of[s] = 0 if i < n_tr else 1 if i < n_tr + n_va else 2
SPLIT = np.array([split_of[u] for u in uid])
tr, va, te = (np.flatnonzero(SPLIT == i) for i in range(3))
say(f'{len(chunks)} chunks, {len(seq_ids)} sequences, {N} rows ({time.time() - t0:.0f} s); train {len(tr)}, val {len(va)}, test {len(te)}')
for g in ('en', 'zh', 'other'):
    say(f'  {g}: ' + ', '.join(f'{kd} {len(np.unique(uid[(LG == g) & (R["kind"] == kd)]))} seqs' for kd in ('rollout', 'pretrain')))

Bx = np.stack([R['ent'], R['cur'], R['m8'], R['m32'], R['m128'], R['logd'], np.ones(N)], 1)
BASE_FEATS = ['next-token entropy', 'current surprisal', 'mean surprisal last 8', 'last 32', 'last 128', 'log context length', 'intercept']
Bw = np.linalg.lstsq(Bx[tr], np.stack([R['next 32'], R['next 128']], 1)[tr], rcond=None)[0]
pb = Bx @ Bw
NAMES = ['next 1', 'next 8', 'next 32', 'next 128', 'added 32', 'added 128']
Y = np.stack([R['next 1'], R['next 8'], R['next 32'], R['next 128'], R['next 32'] - pb[:, 0], R['next 128'] - pb[:, 1]], 1)
ADDED = {4: (2, 0), 5: (3, 1)}  # added target -> (its difficulty column of Y, baseline column of pb)


def r2(y, p):
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def demean_seq(v, rows):
    u = uid[rows]
    _, inv = np.unique(u, return_inverse=True)
    m = np.bincount(inv, v) / np.bincount(inv)
    return v - m[inv]


def score(j, pt, rows):
    if j in ADDED:
        f, b = ADDED[j]
        base = pb[rows, b]
        return {'test': r2(Y[rows, f], base + pt) - r2(Y[rows, f], base),
                'within': r2(demean_seq(Y[rows, f], rows), demean_seq(base + pt, rows)) - r2(demean_seq(Y[rows, f], rows), demean_seq(base, rows)),
                'partial_r2': r2(Y[rows, j], pt)}
    return {'test': r2(Y[rows, j], pt), 'within': r2(demean_seq(Y[rows, j], rows), demean_seq(pt, rows))}


base_r2 = {NAMES[f]: r2(Y[te, f], pb[te, b]) for j, (f, b) in ADDED.items()}
say(f'baseline ({", ".join(BASE_FEATS[:-1])}) test R2: next 32 {base_r2["next 32"]:.3f}, next 128 {base_r2["next 128"]:.3f}')

# ---- activations ----
offs = {}
for k in chunks:
    offs[k] = json.load(open(f'{a.acts}/c{k}/meta.json'))['n_samples']


def load(L):
    X = np.empty((N, D), np.float32)
    for k in chunks:
        m = np.memmap(f'{a.acts}/c{k}/acts_L{L:02d}.f16', dtype=np.float16, mode='r', shape=(offs[k], D))
        sel = np.flatnonzero(R['chunk'] == k)
        X[sel] = m[R['srow'][sel]]
    return torch.from_numpy(X)


LAMS = [float(10 ** (e / 2)) for e in range(-6, 7)]
JLAMS_COARSE = [float(10 ** (e / 2)) for e in (0, 2, 4, 6)]
n_tr = len(tr)
Ktr = torch.zeros((n_tr, n_tr), dtype=torch.float32)
Kva = torch.zeros((len(va), n_tr), dtype=torch.float32)
Kte = torch.zeros((len(te), n_tr), dtype=torch.float32)
BLK = 16384
blocks = [(s, min(s + BLK, n_tr)) for s in range(0, n_tr, BLK)]
per_layer, stats = {}, {}
WL = np.zeros((NL, len(NAMES), D), np.float32)
BL = np.zeros((NL, len(NAMES)), np.float32)
Yt_all = torch.from_numpy(Y[tr])
for L in range(NL):
    tl = time.time()
    X = load(L)
    mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-6
    stats[L] = (mu, sd)
    Z = (X - mu) / sd
    del X
    if not a.no_layers:
        Zt = Z[tr].double()
        A = Zt.T @ Zt
        ym = Yt_all.mean(0)
        Bm = Zt.T @ (Yt_all - ym)
        del Zt
        Zv, Ze = Z[va].double(), Z[te].double()
        pv, pe, Ws = {}, {}, {}
        for lam in LAMS:
            M = A.clone()
            M.diagonal().add_(lam * n_tr)
            W = torch.cholesky_solve(Bm, torch.linalg.cholesky(M))
            pv[lam], pe[lam], Ws[lam] = (Zv @ W + ym).numpy(), (Ze @ W + ym).numpy(), W
        res = {}
        for j in range(len(NAMES)):
            lam = max(LAMS, key=lambda l_: r2(Y[va, j], pv[l_][:, j]))
            res[NAMES[j]] = dict(score(j, pe[lam][:, j], te), lam=lam, val=r2(Y[va, j], pv[lam][:, j]), lam_edge=lam in (LAMS[0], LAMS[-1]))
            w = (Ws[lam][:, j].float() / sd).numpy()
            WL[L, j], BL[L, j] = w, float(ym[j]) - float(w.astype(np.float64) @ mu.numpy().astype(np.float64))
        per_layer[L] = res
        del A, Zv, Ze, Ws, pv, pe
    Zt = Z[tr]
    for bi, (i0, i1) in enumerate(blocks):
        for (j0, j1) in blocks[:bi + 1]:
            Ktr[i0:i1, j0:j1].add_(Zt[i0:i1] @ Zt[j0:j1].T)
    Kva.add_(Z[va] @ Zt.T)
    Kte.add_(Z[te] @ Zt.T)
    del Zt, Z
    say(f'L{L:02d}: ' + (', '.join(f'{nm} {per_layer[L][nm]["test"]:.3f}' for nm in NAMES) if L in per_layer else '') +
        f'  ({time.time() - tl:.0f} s, total {time.time() - t0:.0f} s)')

out = {'names': NAMES, 'baseline_r2': base_r2, 'chunks': chunks, 'n_rows': N, 'n_sequences': int(len(seq_ids)),
       'baseline_coef': {'features': BASE_FEATS, 'next 32': Bw[:, 0].tolist(), 'next 128': Bw[:, 1].tolist()},
       'n_train': n_tr, 'n_val': len(va), 'n_test': len(te),
       'split': 'by sequence, stratified by language group x kind: 70 / 10 / 20',
       'per_layer': {str(L): r for L, r in per_layer.items()}}
if per_layer:
    np.concatenate([WL.reshape(-1), BL.reshape(-1)]).tofile(f'{a.out}/rollprobe_layers_weights.f32')
    out['layers_weights'] = {'file': f'{a.out}/rollprobe_layers_weights.f32',
                             'layout': '[61][n_targets][6144] then [61][n_targets] bias; target = w . h + b (raw block output)'}

# ---- the all-layer probe ----
for bi, (i0, i1) in enumerate(blocks):
    for (j0, j1) in blocks[:bi]:
        Ktr[j0:j1, i0:i1] = Ktr[i0:i1, j0:j1].T
Yt = torch.from_numpy(Y[tr]).float()
ym = Yt.mean(0)
sols, pv, pe = {}, {}, {}


def solve(lam):
    if lam in sols:
        return
    M = Ktr.clone()
    M.diagonal().add_(lam * n_tr)
    sols[lam] = torch.cholesky_solve(Yt - ym, torch.linalg.cholesky(M))
    del M
    pv[lam] = (Kva @ sols[lam] + ym).double().numpy()
    pe[lam] = (Kte @ sols[lam] + ym).double().numpy()
    say(f'  all layers, lambda {lam:g}: val R2 ' + ', '.join(f'{nm} {r2(Y[va, j], pv[lam][:, j]):.4f}' for j, nm in enumerate(NAMES)) +
        f' ({time.time() - t0:.0f} s)')


for lam in JLAMS_COARSE:
    solve(lam)
best = {j: max(sols, key=lambda l_: r2(Y[va, j], pv[l_][:, j])) for j in range(len(NAMES))}
hd = lambda e: float(10 ** (e / 2))  # half-decade grid, exact keys
for e in sorted({round(2 * np.log10(b_)) + s_ for b_ in best.values() for s_ in (-1, 1)}):
    solve(hd(e))
joint, lam_of = {}, {}
PRED = np.full((N, len(NAMES)), np.nan)
for j, nm in enumerate(NAMES):
    lam = max(sols, key=lambda l_: r2(Y[va, j], pv[l_][:, j]))
    lam_of[j] = lam
    joint[nm] = dict(score(j, pe[lam][:, j], te), lam=lam, val=r2(Y[va, j], pv[lam][:, j]), lam_edge=lam in (min(sols), max(sols)))
    PRED[va, j], PRED[te, j] = pv[lam][:, j], pe[lam][:, j]
out['joint'] = joint

# by group (test rows): language group x kind, and depth
groups = {}
DEPTH = [(16, 64), (64, 256), (256, 1024), (1024, 2048)]
for j in (2, 3, 5):
    nm = NAMES[j]
    g_ = {}
    for g in ('en', 'zh', 'other'):
        for kd in ('rollout', 'pretrain'):
            m = te[(LG[te] == g) & (R['kind'][te] == kd)]
            if len(m) > 50:
                g_[f'{g} {kd}'] = dict(score(j, PRED[m, j], m), n=int(len(m)))
    for lo, hi in DEPTH:
        m = te[(R['pos'][te] >= lo) & (R['pos'][te] < hi)]
        if len(m) > 50:
            g_[f'depth {lo}-{hi}'] = dict(score(j, PRED[m, j], m), n=int(len(m)))
    groups[nm] = g_
out['groups'] = groups

# ---- forecast-change reliability at fixed strengths (disjoint quarters / halves of the training sequences) ----
tr_uid = uid[tr]
tseq = np.unique(tr_uid)
tseq = tseq[np.random.default_rng(5).permutation(len(tseq))]
qid = {s: i % 4 for i, s in enumerate(tseq)}
Q = np.array([qid[s] for s in tr_uid])
subsets = {'q0': Q == 0, 'q1': Q == 1, 'q2': Q == 2, 'q3': Q == 3, 'h0': Q < 2, 'h1': Q >= 2}
pr_first = te[R['pair'][te] >= 0]
pr_first = pr_first[np.isin(R['pair'][pr_first], te)]
pos_te = {r: i for i, r in enumerate(te)}
i0_, i1_ = np.array([pos_te[r] for r in pr_first]), np.array([pos_te[R['pair'][r]] for r in pr_first])
c_next = R['next 1'][pr_first + 0]  # c_{s+1} for the first row of the pair = surprisal of token d+1
rel = {}
JREL = [2, 3]
for lamc in [hd(round(2 * np.log10(lam_of[3])) + s_) for s_ in (-2, 0, 2)]:
    preds_sub = {}
    for nm_s, msk in subsets.items():
        it = torch.from_numpy(np.flatnonzero(msk))
        Ks = Ktr.index_select(0, it).index_select(1, it)
        Ks.diagonal().add_(lamc * len(it))
        ys = Yt[it][:, JREL]
        yms = ys.mean(0)
        al = torch.cholesky_solve(ys - yms, torch.linalg.cholesky(Ks))
        del Ks
        preds_sub[nm_s] = (Kte.index_select(1, it) @ al + yms).double().numpy()
    rr = {}
    for size, plist in (('quarter', [('q0', 'q1'), ('q2', 'q3')]), ('half', [('h0', 'h1')])):
        for k2, j in enumerate(JREL):
            vals = {'f': [], 'df': [], 'td': [], 'r2': []}
            for x, y in plist:
                fa, fb = preds_sub[x][:, k2], preds_sub[y][:, k2]
                dfa, dfb = fa[i1_] - fa[i0_], fb[i1_] - fb[i0_]
                K_ = int(NAMES[j].split()[1])
                tda, tdb = -c_next - K_ * dfa, -c_next - K_ * dfb
                vals['f'].append(np.corrcoef(fa, fb)[0, 1])
                vals['df'].append(np.corrcoef(dfa, dfb)[0, 1])
                vals['td'].append(np.corrcoef(tda, tdb)[0, 1])
                vals['r2'].append((r2(Y[te, j], fa) + r2(Y[te, j], fb)) / 2)
            rr[f'{size} {NAMES[j]}'] = {k3: float(np.mean(v)) for k3, v in vals.items()}
    nseq = {'quarter': len(tseq) / 4, 'half': len(tseq) / 2}
    for j in JREL:
        for what in ('df', 'td'):
            rq, rh = rr[f'quarter {NAMES[j]}'][what], rr[f'half {NAMES[j]}'][what]
            # rho(n) = n / (n + c), least squares on 1/rho - 1 = c / n over the two sizes
            pts = [(nseq['quarter'], rq), (nseq['half'], rh)]
            ok = [(n_, r_) for n_, r_ in pts if 0 < r_ < 1]
            cc = float(sum((1 / r_ - 1) / n_ for n_, r_ in ok) / sum(1 / n_ ** 2 for n_, _ in ok)) if ok else float('nan')
            rr[f'fit {NAMES[j]} {what}'] = {'c_sequences': cc, 'rho_full_train': len(tseq) / (len(tseq) + cc),
                                            'n_for_0.8': 4 * cc, 'n_for_0.9': 9 * cc}
    rel[f'{lamc:g}'] = rr
out['reliability'] = {'lambdas': list(rel), 'n_train_sequences': int(len(tseq)), 'n_test_pairs': int(len(pr_first)), 'by_lambda': rel}

# ---- raw weights + self-check ----
WJ = np.zeros((len(NAMES), NL, D), np.float32)
bj = np.array([float(ym[j]) for j in range(len(NAMES))], np.float64)
pchk = np.zeros((len(te), len(NAMES)))
AL = torch.stack([sols[lam_of[j]][:, j] for j in range(len(NAMES))], 1)
del Ktr, Kva, Kte
for L in range(NL):
    X = load(L)
    mu, sd = stats[L]
    W = ((((X[tr] - mu) / sd).T @ AL) / sd[:, None]).numpy()  # [D, n_targets]
    WJ[:, L] = W.T
    bj -= (mu.numpy().astype(np.float64) @ W.astype(np.float64))
    pchk += X[te].double().numpy() @ W.astype(np.float64)
    del X
with open(f'{a.out}/rollprobe_weights.f32', 'wb') as fh:
    WJ.reshape(-1).tofile(fh)
    bj.astype(np.float32).tofile(fh)
chk = {nm: float(np.abs(pchk[:, j] + bj[j] - PRED[te, j]).max()) for j, nm in enumerate(NAMES)}
out['weights'] = {'file': f'{a.out}/rollprobe_weights.f32', 'layout': 'f32 [n_targets][61][6144] then [n_targets] bias; '
                  'target = sum_L w_L . h_L + b (raw block outputs); added targets predict the residual of baseline_coef',
                  'selfcheck_max_abs_diff': chk}

say()
say(f'self-check, raw weights vs kernel predictions (max |diff|): ' + ', '.join(f'{k} {v:.1e}' for k, v in chk.items()))
say('test R2 (within-sequence in parentheses); "added" = R2(baseline + probe) - R2(baseline)')
say(f'{"probe":12s} ' + ' '.join(f'{nm:>17s}' for nm in NAMES))
for lab_, rr_ in [('layer 40', per_layer.get(40)), ('all layers', joint)]:
    if rr_:
        say(f'{lab_:12s} ' + ' '.join(f'{rr_[nm]["test"]:7.3f} ({rr_[nm]["within"]:6.3f})' for nm in NAMES))
say('all-layer strengths: ' + ', '.join(f'{nm} {joint[nm]["lam"]:g}' + (' (edge)' if joint[nm]['lam_edge'] else '') for nm in NAMES))
if per_layer:
    for nm in NAMES:
        bl = max(per_layer, key=lambda L: per_layer[L][nm]['test'])
        say(f'  single-layer peak, {nm}: L{bl} {per_layer[bl][nm]["test"]:.3f}')
say()
say('test R2 by group (all-layer probe):')
for nm, g_ in groups.items():
    say(f'  {nm}: ' + ', '.join(f'{g} {v["test"]:.3f} (n {v["n"]})' for g, v in g_.items()))
say()
say(f'forecast-change reliability, {len(tseq)} training sequences, {len(pr_first)} test pairs; strengths fixed:')
for lamc, rr in rel.items():
    say(f'  lambda {lamc}:')
    for size in ('quarter', 'half'):
        say(f'    {size} ({len(tseq) // (4 if size == "quarter" else 2)} seqs each): ' + '; '.join(
            f'{NAMES[j]}: R2 {rr[f"{size} {NAMES[j]}"]["r2"]:.3f}, rel f {rr[f"{size} {NAMES[j]}"]["f"]:.3f}, '
            f'rel df {rr[f"{size} {NAMES[j]}"]["df"]:.3f}, rel TD {rr[f"{size} {NAMES[j]}"]["td"]:.3f}' for j in JREL))
    for j in JREL:
        say('    ' + '; '.join(f'{NAMES[j]} {what}: rho = n / (n + {rr[f"fit {NAMES[j]} {what}"]["c_sequences"]:.0f}), '
                               f'full train {rr[f"fit {NAMES[j]} {what}"]["rho_full_train"]:.2f}, 0.9 at {rr[f"fit {NAMES[j]} {what}"]["n_for_0.9"]:.0f} seqs'
                               for what in ('df', 'td')))
json.dump(out, open(f'{a.out}/rollprobe.json', 'w'), indent=1)
np.savez(f'{a.out}/rollprobe_rows.npz', **{k.replace(' ', '_'): v for k, v in R.items()}, lang_group=LG, split=SPLIT,
         baseline=pb, Y=Y, pred=PRED, names=np.array(NAMES))
open(f'{a.out}/rollprobe.txt', 'w').write('\n'.join(lines) + '\n')
say(f'-> {a.out}/rollprobe.json ({time.time() - t0:.0f} s)')
