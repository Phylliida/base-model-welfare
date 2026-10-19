"""Fit the closed-loop response of plan B (homeo-ident output): which state directions does the model push back on?

For each dose and probe p (unit push u_p = Q^T z_p in the K-dim basis), the odd part of the paired arms,
r_p(lag) = (dproj(+) - dproj(-)) / (2 * dose * |h|), is the token-mediated response of the pre-steer layer-L
state, per unit push, in basis coordinates (the even part (dproj(+) + dproj(-)) / 2 is the nonlinearity check).
Averaged over prefixes and a lag window, r_p ~ M z_p; M is fitted by least squares over probes.
  kappa(u) = -u^T M u   the fraction of a sustained push along u that the model undoes through what it writes:
                        > 0 pushed back (candidate regulation), < 0 amplified, 0 ignored
Eigen-directions of the symmetric part of M give the most pushed-back / amplified directions. Nulls:
  - probe permutation (shuffle z against r): the eigenvalue spread that noise alone produces
  - split halves: directions found on half the prefixes, kappa measured on the other half
Checks: the lag-0 response must be exactly 0 (the last prefix token sees no generated token).

usage: ident_fit.py PREFIX [--windows 1-4,5-12,13-31] [--n-perm 200] [--out PREFIX.fit]
"""
import argparse
import json

import torch  # noqa: F401  (import before numpy on this box)
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('prefix')
ap.add_argument('--windows', default='1-4,5-12,13-31')
ap.add_argument('--n-perm', type=int, default=200)
ap.add_argument('--out', default=None)
a = ap.parse_args()
out = a.out or a.prefix + '.fit'

meta = json.load(open(a.prefix + '.meta.json'))
NP, G, K, P = meta['n_prefix'], meta['n_gen'], meta['k'], meta['n_probe']
doses, hn = meta['doses'], meta['resid_norm']
Z = np.fromfile(a.prefix + '.z.f32', dtype=np.float32).reshape(P, K)
REC = np.dtype([('dproj', np.float16, (NP, G, K)), ('dnorm', np.float32, (NP, G)), ('ent', np.float32, (NP, G)),
                ('tok', np.int32, (NP, G)), ('first_div', np.int32, (NP,)), ('endpoint', np.int32, (NP,))])
assert REC.itemsize == meta['record_bytes'], (REC.itemsize, meta['record_bytes'])
recs = np.memmap(a.prefix + '.bin', dtype=REC, mode='r')
n_done = len(recs)
windows = [tuple(int(x) for x in w.split('-')) for w in a.windows.split(',')]
rng = np.random.default_rng(0)
lines, res = [], {'meta': {k: meta[k] for k in ('layer', 'k', 'n_probe', 'n_prefix', 'n_gen', 'doses', 'resid_norm')},
                  'records_done': int(n_done), 'doses': {}}


def say(s=''):
    print(s)
    lines.append(s)


def fit_M(R, Zp):
    """least squares R (P x K) ~ Zp (P x K) M^T"""
    Mt, *_ = np.linalg.lstsq(Zp, R, rcond=None)
    return Mt.T


def sym_eig(M):
    S = (M + M.T) / 2
    w, V = np.linalg.eigh(S)
    return w, V  # ascending: most negative (pushed back) first


base = recs[0]
say(f'{a.prefix}: layer {meta["layer"]}, K {K}, {P} probes, {NP} prefixes x {G} generated tokens, |h| {hn:.1f}; '
    f'{n_done} of {1 + len(doses) * P * 2} records')
say(f'unsteered: endpoints {int((base["endpoint"] != 0).sum())}/{NP}, mean entropy {np.nanmean(base["ent"]):.2f} nats')

for di, dose in enumerate(doses):
    lo = 1 + di * P * 2
    n_pairs = max(0, min(P, (n_done - lo) // 2))
    if n_pairs < 4:
        continue
    plus = recs[lo:lo + 2 * n_pairs:2]
    minus = recs[lo + 1:lo + 2 * n_pairs:2]
    dp = plus['dproj'].astype(np.float32)   # [p, NP, G, K]
    dm = minus['dproj'].astype(np.float32)
    scale = 2 * dose * hn
    odd = (dp - dm) / scale                  # response per unit push, basis coords
    even = (dp + dm) / 2 / (dose * hn)
    Zp = Z[:n_pairs]
    say()
    say(f'=== dose {dose} (push {dose * hn:.1f} = {dose:.2f} x |h|), {n_pairs} probe pairs')
    lag0 = float(np.nanmax(np.abs(np.concatenate([dp[:, :, 0], dm[:, :, 0]]))))
    say(f'lag-0 check (must be 0): max |dproj| at lag 0 = {lag0:.3g}')
    fd = np.concatenate([plus['first_div'], minus['first_div']])
    div_by = [float(np.mean((fd >= 0) & (fd <= k))) for k in range(G)]
    say('fraction of sequences diverged from the unsteered tokens by lag: ' +
        ', '.join(f'{k}:{div_by[k]:.2f}' for k in (0, 1, 2, 4, 8, 16, G - 1) if k < G))
    ep = np.concatenate([plus['endpoint'], minus['endpoint']])
    say(f'endpoints: loop {int((ep == 1).sum())}, incoherence {int((ep == 2).sum())} of {ep.size}')
    say(f'entropy: unsteered {np.nanmean(base["ent"]):.2f}, + {np.nanmean(plus["ent"]):.2f}, - {np.nanmean(minus["ent"]):.2f} nats')
    dres = {'n_pairs': int(n_pairs), 'lag0_max': lag0, 'diverged_by_lag': div_by, 'windows': {}}
    # self-projection kappa_p = -z_p . r_p (no matrix needed): its mean is -trace(M)/K
    for (w0, w1) in windows:
        if w0 >= G:
            continue
        w1 = min(w1, G - 1)
        R_np = np.nanmean(odd[:, :, w0:w1 + 1], axis=2)       # [p, NP, K]
        E_np = np.nanmean(even[:, :, w0:w1 + 1], axis=2)
        R = np.nanmean(R_np, axis=1)                          # [p, K]
        kap = -(R * Zp).sum(1)
        # in-subspace response size vs. its odd/even split
        say(f'-- lags {w0}-{w1}: |odd response| {np.linalg.norm(R, axis=1).mean():.3f}, |even| {np.linalg.norm(np.nanmean(E_np, axis=1), axis=1).mean():.3f} '
            f'(per unit push, in-subspace); self-kappa mean {kap.mean():+.3f} +- {kap.std(ddof=1) / np.sqrt(len(kap)):.3f}')
        wres = {'odd_norm': float(np.linalg.norm(R, axis=1).mean()), 'self_kappa_mean': float(kap.mean()),
                'self_kappa_se': float(kap.std(ddof=1) / np.sqrt(len(kap)))}
        if n_pairs >= K:
            M = fit_M(R, Zp)
            w, V = sym_eig(M)
            nul_lo, nul_hi = [], []
            for _ in range(a.n_perm):
                wn, _ = sym_eig(fit_M(R, Zp[rng.permutation(n_pairs)]))
                nul_lo.append(wn[0]); nul_hi.append(wn[-1])
            nul_lo, nul_hi = np.array(nul_lo), np.array(nul_hi)
            # split halves over prefixes: directions from half A, kappa on half B
            half = rng.permutation(NP)
            A, B = half[:NP // 2], half[NP // 2:]
            MA = fit_M(np.nanmean(R_np[:, A], axis=1), Zp)
            MB = fit_M(np.nanmean(R_np[:, B], axis=1), Zp)
            wA, VA = sym_eig(MA)
            cross = [float(-(VA[:, i] @ MB @ VA[:, i])) for i in range(3)]
            cross_amp = [float(-(VA[:, -1 - i] @ MB @ VA[:, -1 - i])) for i in range(3)]
            say(f'   M fitted ({K}x{K}): mean kappa of a random direction (-trace/K) {-np.trace(M) / K:+.4f}; most pushed back kappa {-w[0]:+.3f} '
                f'(null 95%: {-np.percentile(nul_lo, 5):+.3f}), most amplified {-w[-1]:+.3f} (null 5%: {-np.percentile(nul_hi, 95):+.3f})')
            say(f'   split halves: top-3 pushed-back directions of half A have kappa on half B {", ".join(f"{x:+.3f}" for x in cross)}; '
                f'top-3 amplified {", ".join(f"{x:+.3f}" for x in cross_amp)}')
            wres.update({'trace_over_k': float(np.trace(M) / K), 'kappa_eigs': [float(-x) for x in w],
                         'null_pushback_95': float(-np.percentile(nul_lo, 5)), 'null_amplify_5': float(-np.percentile(nul_hi, 95)),
                         'split_half_pushback': cross, 'split_half_amplify': cross_amp})
            np.save(f'{out}_d{dose}_w{w0}-{w1}_M.npy', M)
        dres['windows'][f'{w0}-{w1}'] = wres
    res['doses'][str(dose)] = dres

json.dump(res, open(out + '.json', 'w'), indent=1)
open(out + '.txt', 'w').write('\n'.join(lines) + '\n')
print(f'-> {out}.txt / .json')
