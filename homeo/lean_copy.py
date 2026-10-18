#!/usr/bin/env python3
"""H3 follow-up: is the real-text b > 0 a copying effect?

A candidate that repeats earlier text (an induction continuation) leads to an easy future, so if human text
copies more than the model expects, b > 0 without any lean toward easy futures as such. Per candidate x at
position t (context = window tokens 0..t, x would be token t+1):
  inctx    x occurs anywhere in the context
  bigram   x followed the current token somewhere earlier in the context
  trigram  x followed the last two tokens somewhere earlier
Fits q(x) ~ exp(a log p + b V + copy terms) and the plain model at positions where no candidate continues an
earlier bigram (copying can't drive b there). Bootstrap SE over windows as in lean_fit.py.

usage: lean_copy.py /mnt/models/homeo/lean/lean.jsonl [--boot 200] [--json out.json]
"""
import argparse
import json
import os
import sys

import torch
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lean_fit import boot, fit, load  # noqa: E402


def copy_feats(r, ids):
    ctx = np.asarray(ids[r['off']:r['off'] + r['t'] + 1])
    t = len(ctx) - 1
    inctx = np.isin(r['tok'], ctx)
    nxt_bi = set(ctx[1:][ctx[:-1] == ctx[t]].tolist()) if t > 0 else set()  # earlier j < t only
    m3 = (ctx[:-2] == ctx[t - 1]) & (ctx[1:-1] == ctx[t]) if t > 1 else np.zeros(0, bool)
    nxt_tri = set(ctx[2:][m3].tolist()) if t > 1 else set()
    bi = np.array([x in nxt_bi for x in r['tok'].tolist()])
    tri = np.array([x in nxt_tri for x in r['tok'].tolist()])
    return np.stack([inctx, bi, tri], 1).astype(np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--boot', type=int, default=200)
    ap.add_argument('--json', default=None)
    ap.add_argument('--ids', default='/mnt/models/jlens/fineweb_ids.bin')
    a = ap.parse_args()
    torch.set_num_threads(32)
    rng = np.random.default_rng(1)
    ids = np.memmap(a.ids, dtype=np.int32, mode='r')
    rows = [r for r in load(a.path) if r['actual'] in set(r['tok'].tolist())]
    lp = np.stack([r['lp'] for r in rows])
    V = -np.stack([r['Hk'].mean(1) for r in rows])
    y = np.array([int(np.flatnonzero(r['tok'] == r['actual'])[0]) for r in rows])
    win = np.array([r['w'] for r in rows])
    C = np.stack([copy_feats(r, ids) for r in rows])            # [n, N, 3]
    mask = np.ones_like(lp, bool)
    n = len(rows)
    act = C[np.arange(n), y]
    print(f'{n} positions. Share of candidates / of actual tokens that are: '
          + ', '.join(f'{nm} {C[:, :, i].mean():.3f} / {act[:, i].mean():.3f}' for i, nm in enumerate(['in context', 'bigram copy', 'trigram copy'])))
    # V of copy vs non-copy candidates, within position
    Vc = V - V.mean(1, keepdims=True)
    print(f'within-position V of bigram-copy candidates {Vc[C[:, :, 1] > 0].mean():+.3f}, others {Vc[C[:, :, 1] == 0].mean():+.3f}')

    res = dict(n=n, share_cand=C.mean((0, 1)).tolist(), share_actual=act.mean(0).tolist())
    no_copy = C[:, :, 1].sum(1) == 0
    specs = {
        'V': (np.stack([lp, V], 2), mask, ['a', 'b'], np.ones(n, bool)),
        'copy only': (np.concatenate([lp[:, :, None], C], 2), mask, ['a', 'inctx', 'bigram', 'trigram'], np.ones(n, bool)),
        'V + copy': (np.concatenate([lp[:, :, None], V[:, :, None], C], 2), mask, ['a', 'b', 'inctx', 'bigram', 'trigram'], np.ones(n, bool)),
        'V, no candidate is a bigram copy': (np.stack([lp, V], 2), mask, ['a', 'b'], no_copy),
        'V, some candidate is a bigram copy': (np.stack([lp, V], 2), mask, ['a', 'b'], ~no_copy),
    }
    res['fits'] = {}
    for nm, (F, M, names, sel) in specs.items():
        th, nll = fit(F[sel], y[sel], M[sel])
        B = boot(F[sel], y[sel], M[sel], win[sel], a.boot, rng)
        se = B.std(0)
        res['fits'][nm] = dict(n=int(sel.sum()), theta=dict(zip(names, map(float, th))), se=dict(zip(names, map(float, se))), nll=nll)
        print(f'  {nm:36s} n {sel.sum():5d}  nll {nll:.4f}  ' + '  '.join(f'{k} {v:+.3f} ({s:.3f})' for k, v, s in zip(names, th, se)))
    if a.json:
        json.dump(res, open(a.json, 'w'), indent=1)


if __name__ == '__main__':
    main()
