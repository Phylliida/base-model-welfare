#!/usr/bin/env python3
"""Lean test (H3 of the Value Lens proposal) on homeo-lean output.

At each position of real text the model's top-N candidates x have log p(x) and a future certainty
V(x) = -mean entropy of the model's next-token distribution over the 16 steps after x (rollouts at T = 1,
untruncated). A conditional logit over the candidates, fit to the actual next token:

    q(x) ~ exp(a * log p(x) + b * V(x) + c . Z(x))

a != 1 is miscalibration within the candidates (the temperature dial). b < 0 means the model gives more
probability to easy-future tokens than real text does: a lean toward predictability. b > 0 is the reverse
(real text goes to easier futures more often than the model expects). Only positions whose actual token is
among the candidates are used (the candidate set depends on the model only, so this conditioning is
unbiased for the conditional logit).

1. Gate (synthetic positive control): outcomes drawn from softmax(log p + beta * V_A) over the candidates,
   fit with V_B (V_A, V_B: the two halves of the rollouts), for several beta. Recovery b / beta measures the
   attenuation from rollout noise; beta = 0 is the calibrated null (outcomes are the model's own samples).
2. Real text: models with V; V split into the next step (V1 = -H_1) and later steps (V_late); covariates
   (log unigram frequency, token classes, and the token's average V over all its appearances, so that b is a
   within-token contrast); strata by the current entropy.
Standard errors: bootstrap over windows.

usage: lean_fit.py /mnt/models/homeo/lean/lean.jsonl [--boot 200] [--json out.json]
"""
import argparse
import json

import torch
import numpy as np

H = '/mnt/models/homeo'


def load(path):
    rows = []
    for line in open(path):
        if not line.endswith('}\n') and not line.endswith('}'):
            continue
        w = json.loads(line)
        for p in w['positions']:
            c = p['cands']
            rows.append(dict(w=w['w'], off=w['offset'], t=p['t'], H=p['H'], past=p['past32'], actual=p['actual'],
                             tok=np.array([x['tok'] for x in c]), lp=np.array([x['lp'] for x in c]),
                             Hk=np.array([x['Hk'] for x in c]), Hr=np.array([x['Hr'] for x in c]),
                             Sr=np.array([x['Sr'] for x in c])))
    return rows


def token_classes():
    toks = json.load(open(f'{H}/value/vocab.json'))
    cls = np.zeros((len(toks), 4), np.float32)
    for i, t in enumerate(toks):
        s = t.replace('Ġ', ' ').replace('Ċ', '\n')
        cls[i, 0] = '\n' in s
        cls[i, 1] = len(s.strip()) > 0 and all(not ch.isalnum() for ch in s.strip())
        cls[i, 2] = s.startswith(' ') and s.strip().isalpha()
        cls[i, 3] = any(ch.isdigit() for ch in s)
    return cls


def fit(feats, y, mask, iters=60):
    """Conditional logit: feats [n, N, d], y [n] index of the actual candidate, mask [n, N]. Returns theta, nll."""
    X = torch.from_numpy(feats).double()
    Y = torch.from_numpy(y).long()
    M = torch.from_numpy(mask)
    th = torch.zeros(X.shape[2], dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([th], lr=1, max_iter=iters, line_search_fn='strong_wolfe')

    def closure():
        opt.zero_grad()
        z = (X @ th).masked_fill(~M, -1e30)
        loss = -(z.gather(1, Y[:, None])[:, 0] - torch.logsumexp(z, 1)).mean()
        loss.backward()
        return loss
    opt.step(closure)
    return th.detach().numpy(), float(closure().item())


def boot(feats, y, mask, win, n_boot, rng):
    uw = np.unique(win)
    idx_of = {w: np.flatnonzero(win == w) for w in uw}
    out = []
    for _ in range(n_boot):
        ws = rng.choice(uw, len(uw))
        ii = np.concatenate([idx_of[w] for w in ws])
        out.append(fit(feats[ii], y[ii], mask[ii], iters=30)[0])
    return np.array(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--boot', type=int, default=200)
    ap.add_argument('--json', default=None)
    ap.add_argument('--ids', default='/mnt/models/jlens/fineweb_ids.bin')
    a = ap.parse_args()
    torch.set_num_threads(32)
    rng = np.random.default_rng(0)
    rows = load(a.path)
    n_all = len(rows)
    N = len(rows[0]['tok'])
    R = rows[0]['Hr'].shape[1]
    rows = [r for r in rows if r['actual'] in set(r['tok'].tolist())]
    n = len(rows)
    print(f'{n_all} positions from {len({r["w"] for r in rows})} windows; actual token in the top {N}: {n} ({n / n_all:.1%})')

    lp = np.stack([r['lp'] for r in rows])                       # [n, N]
    V = -np.stack([r['Hk'].mean(1) for r in rows])               # future certainty, all rollouts
    VA = -np.stack([r['Hr'][:, :R // 2].mean(1) for r in rows])  # rollout halves
    VB = -np.stack([r['Hr'][:, R // 2:].mean(1) for r in rows])
    V1 = -np.stack([r['Hk'][:, 0] for r in rows])                # next step only (deterministic given x)
    VL = -np.stack([r['Hk'][:, 1:].mean(1) for r in rows])       # later steps
    tok = np.stack([r['tok'] for r in rows])
    y = np.array([int(np.flatnonzero(r['tok'] == r['actual'])[0]) for r in rows])
    win = np.array([r['w'] for r in rows])
    Ht = np.array([r['H'] for r in rows])
    mask = np.ones_like(lp, bool)
    res = dict(n_positions=n_all, n_used=n, n_cand=N, n_roll=R)

    # within-position spread of V, for scale
    sdV = float(np.sqrt(((V - V.mean(1, keepdims=True)) ** 2).mean()))
    relAB = float(np.corrcoef((VA - VA.mean(1, keepdims=True)).ravel(), (VB - VB.mean(1, keepdims=True)).ravel())[0, 1])
    print(f'within-position sd of V {sdV:.3f} nats; split-half reliability of within-position V (r between halves) {relAB:.3f}')
    rel_full = 2 * relAB / (1 + relAB)  # Spearman-Brown: reliability of V from all rollouts
    sd_w = lambda X: float(np.sqrt(((X - X.mean(1, keepdims=True)) ** 2).mean()))
    res.update(sd_V1_within=sd_w(V1), sd_VL_within=sd_w(VL))
    print(f'within-position sd of V1 (next step) {sd_w(V1):.3f}, of V_late (steps 2-16) {sd_w(VL):.3f}')
    print(f'  reliability of V from all {R} rollouts (Spearman-Brown) {rel_full:.3f}: b from V is attenuated by about this factor')
    res.update(sd_V_within=sdV, split_half_r=relAB, reliability_full=rel_full)

    # ---- 1. gate: synthetic positive control ----
    print('\n1. Gate: outcomes drawn from softmax(log p + beta V_A), fit with V_B (and with V_A itself)')
    print(f'  {"beta":>6s} {"b (V_B)":>9s} {"b/beta":>7s} {"a":>6s} {"b (V_A)":>9s}')
    gate = []
    for beta in [-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 1.0]:
        z = lp + beta * VA
        pz = np.exp(z - z.max(1, keepdims=True))
        pz /= pz.sum(1, keepdims=True)
        bs, bas, as_ = [], [], []
        for rep in range(3):
            ys = np.array([rng.choice(N, p=p) for p in pz])
            th, _ = fit(np.stack([lp, VB], 2), ys, mask)
            th2, _ = fit(np.stack([lp, VA], 2), ys, mask)
            bs.append(th[1]); as_.append(th[0]); bas.append(th2[1])
        b, aa, b2 = np.mean(bs), np.mean(as_), np.mean(bas)
        gate.append(dict(beta=beta, b_VB=float(b), a=float(aa), b_VA=float(b2), b_VB_sd=float(np.std(bs))))
        print(f'  {beta:+6.2f} {b:+9.3f} {(b / beta if beta else float("nan")):7.2f} {aa:6.3f} {b2:+9.3f}')
    res['gate'] = gate

    # ---- 2. real text ----
    ids = np.fromfile(a.ids, dtype=np.int32)
    freq = np.bincount(ids, minlength=int(tok.max()) + 1).astype(np.float64)
    lf = np.log(freq[tok] + 1.0)
    lf = (lf - lf.mean()) / lf.std()
    cls = token_classes()[tok]                                    # [n, N, 4]
    # token's mean V over all its appearances as a candidate (within-token contrast)
    flat_t, flat_v = tok.ravel(), V.ravel()
    sums = np.bincount(flat_t, weights=flat_v, minlength=int(tok.max()) + 1)
    cnts = np.bincount(flat_t, minlength=int(tok.max()) + 1)
    k = 5.0
    tokV = ((sums + k * flat_v.mean()) / (cnts + k))[tok]

    models = {
        'calibration only': [lp],
        'V': [lp, V],
        'V1 + V_late': [lp, V1, VL],
        'V + frequency + classes': [lp, V, lf] + [cls[:, :, i] for i in range(4)],
        'V + token mean V (within-token)': [lp, V, tokV],
        'V + all covariates': [lp, V, lf, tokV] + [cls[:, :, i] for i in range(4)],
        'realized surprisal instead of entropy': [lp, -np.stack([r['Sr'].mean(1) for r in rows])],
    }
    names = {'calibration only': ['a'], 'V': ['a', 'b'], 'V1 + V_late': ['a', 'b1', 'b_late'],
             'V + frequency + classes': ['a', 'b', 'freq', 'newline', 'punct', 'word', 'digit'],
             'V + token mean V (within-token)': ['a', 'b', 'tokV'],
             'V + all covariates': ['a', 'b', 'freq', 'tokV', 'newline', 'punct', 'word', 'digit'],
             'realized surprisal instead of entropy': ['a', 'b']}
    print(f'\n2. Real text (bootstrap SE over windows, {a.boot} resamples)')
    res['real'] = {}
    for mname, cols in models.items():
        F = np.stack(cols, 2)
        th, nll = fit(F, y, mask)
        B = boot(F, y, mask, win, a.boot if mname in ('V', 'V1 + V_late', 'V + all covariates') else max(50, a.boot // 4), rng)
        se = B.std(0)
        res['real'][mname] = dict(theta=dict(zip(names[mname], map(float, th))), se=dict(zip(names[mname], map(float, se))),
                                  nll=nll)
        cells = '  '.join(f'{nm} {v:+.3f} ({s:.3f})' for nm, v, s in zip(names[mname], th, se))
        print(f'  {mname:40s} nll {nll:.4f}  {cells}')
        if mname == 'V':
            res['b_corrected'] = float(th[1] / rel_full)
            print(f'  {"":40s} b / reliability {th[1] / rel_full:+.3f} ({se[1] / rel_full:.3f}); per within-position sd of V: '
                  f'{th[1] * sdV:+.3f} nats of log-odds')

    # strata by the current entropy
    print('\n  by current entropy (model V):')
    res['strata'] = {}
    for lo, hi in [(0, 1), (1, 2.5), (2.5, 99)]:
        m = (Ht >= lo) & (Ht < hi)
        if m.sum() < 200:
            continue
        F = np.stack([lp, V], 2)[m]
        th, _ = fit(F, y[m], mask[m])
        B = boot(F, y[m], mask[m], win[m], max(50, a.boot // 4), rng)
        res['strata'][f'{lo}-{hi}'] = dict(n=int(m.sum()), a=float(th[0]), b=float(th[1]), se_b=float(B[:, 1].std()))
        print(f'  H in [{lo}, {hi}): n {m.sum():6d}  a {th[0]:+.3f}  b {th[1]:+.3f} ({B[:, 1].std():.3f})')
    if a.json:
        json.dump(res, open(a.json, 'w'), indent=1)


if __name__ == '__main__':
    main()
