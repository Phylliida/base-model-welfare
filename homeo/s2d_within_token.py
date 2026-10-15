#!/usr/bin/env python3
"""S2(d) within-token test: does a band vector boost tokens because of their probability in context
(reading p), or because of what they are (token-type bias)?

Input: homeo-steer --dump-topn N --dump-prefix PREFIX files, one per scale: for every eval position
the N most likely unsteered tokens as (int32 id, f32 log p, f32 log q).

Per position the steering boost of token x is d(x) = log q(x) - log p(x), centered over the position's
N tokens (removes the shift of the normalizer). Temperature gives d linear in log p, so the question is
whether d has a bump near the target band on top of a straight line, and whether that bump survives
within token (subtracting each token's mean boost across contexts).

usage: s2d_within_token.py PREFIX_s4.bin --n 64 --band 0.03 [--width 1.5]
"""
import argparse
import torch  # noqa: F401  (import before numpy on this box)
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--n', type=int, default=64)
    ap.add_argument('--band', type=float, required=True)
    ap.add_argument('--width', type=float, default=1.5)
    ap.add_argument('--min-count', type=int, default=3, help='min contexts per token for the within-token curve')
    a = ap.parse_args()

    rec = np.fromfile(a.path, dtype=np.dtype([('id', '<i4'), ('lp', '<f4'), ('lq', '<f4')]))
    P = len(rec) // a.n
    rec = rec[:P * a.n].reshape(P, a.n)
    ids, lp, lq = rec['id'], rec['lp'].astype(np.float64), rec['lq'].astype(np.float64)
    d = lq - lp
    l10 = lp / np.log(10)
    keep = l10 > -3.5
    # exact temperature gives d = a ln p + c_pos with a per-position constant c_pos, so center both d and ln p
    # per position (over the kept tokens) before fitting the shared slope; otherwise c_pos leaks into the residual
    cnt_pos = keep.sum(axis=1, keepdims=True)
    dm = (d * keep).sum(axis=1, keepdims=True) / cnt_pos
    lm = (lp * keep).sum(axis=1, keepdims=True) / cnt_pos
    dc, lc = d - dm, lp - lm

    ids, l10, d, lpf = ids[keep], l10[keep], dc[keep], lc[keep]

    # straight-line (temperature) fit through the origin of the centered values, then residual by log p bin
    slope = (d * lpf).sum() / (lpf * lpf).sum()
    coef = (0.0, slope)
    res = d - slope * lpf

    # within token: subtract each token's mean residual over its contexts
    uniq, inv, cnt = np.unique(ids, return_inverse=True, return_counts=True)
    tok_mean = np.bincount(inv, weights=res) / cnt
    multi = cnt[inv] >= a.min_count
    res_w = res - tok_mean[inv]

    lo, hi = np.log10(a.band / a.width), np.log10(a.band * a.width)
    in_band = (l10 >= lo) & (l10 <= hi)
    edges = np.arange(-3.5, 0.01, 0.25)
    print(f'{a.path}: {P} positions x {a.n} tokens, {len(uniq)} token types; line fit d = {coef[1]:+.4f} * ln p (per-position centered)')
    print(f'  (temperature T would give slope 1/T - 1; slope {coef[1]:+.4f} ~ T = {1 / (1 + coef[1]):.3f})')
    print('  log10 p bin     n   resid boost   within-token resid (tokens seen >= %d times)' % a.min_count)
    for i in range(len(edges) - 1):
        m = (l10 >= edges[i]) & (l10 < edges[i + 1])
        mw = m & multi
        tag = ' <- band' if edges[i] < hi and edges[i + 1] > lo else ''
        if m.sum() < 20:
            continue
        print(f'  [{edges[i]:+.2f},{edges[i + 1]:+.2f})  {m.sum():6d}   {res[m].mean():+.4f}      '
              f'{(res_w[mw].mean() if mw.sum() else float("nan")):+.4f} (n {mw.sum()}){tag}')
    out_b = ~in_band
    print(f'  band minus rest, raw residual:          {res[in_band].mean() - res[out_b].mean():+.4f} nats')
    print(f'  band minus rest, within-token residual: {res_w[in_band & multi].mean() - res_w[out_b & multi].mean():+.4f} nats')
    # variance split: token identity vs p (after the line)
    ss_tot = ((res - res.mean()) ** 2).sum()
    ss_tok = (cnt * (tok_mean - res.mean()) ** 2).sum()
    print(f'  share of residual variance explained by token identity: {ss_tok / ss_tot:.3f}')


if __name__ == '__main__':
    main()
