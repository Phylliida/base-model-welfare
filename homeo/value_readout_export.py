#!/usr/bin/env python3
"""Export the value-lens linear readouts for live use (llama-server --value-probe, the loom's value view).

Refits the layer-40 ridge probes on all 1200 VL1 windows with the ridge strengths chosen on held-out data
(value_probe.py, value_forecast.py):
  stakes   log |g_fut|: how much the next 32 tokens' log-likelihood depends on the state here (test R2 0.38)
  now      log |g_now|: how much the next token's log-likelihood depends on it (test R2 0.56)
  next8    mean surprisal of the next 8 tokens after the next one, from the state alone (test R2 0.18)
  next32   the same over 32 tokens (test R2 0.25)
Writes OUT.f32 ([n][n_embd] weights in raw-h units, then [n] biases; target = W h + b) and OUT.json (layer,
names, test R2, and each readout's fineweb distribution of predictions for color scales).

usage: value_readout_export.py [--out /mnt/models/homeo/value_probe/readout_L40]
"""
import argparse
import json
import os
import sys

import torch
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from value_probe import Ridge, load_acts, load_grads, D  # noqa: E402
from value_forecast import blank_tokens, features  # noqa: E402

H = '/mnt/models/homeo'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=f'{H}/value_probe/readout_L40')
    a = ap.parse_args()
    torch.set_num_threads(48)
    n_win = 1200
    X, _, _ = load_acts(f'{H}/value_probe/main', n_win)
    now, fut, _ = load_grads(f'{H}/value', n_win)
    Y = {'stakes': np.log(np.linalg.norm(fut, axis=1) + 1e-6), 'now': np.log(np.linalg.norm(now, axis=1) + 1e-6)}
    del now, fut
    F8, F32, _, clean, _ = features(f'{H}/value', n_win, blank_tokens())
    Y['next8'], Y['next32'] = F8, F32
    lam = {'stakes': 1.0, 'now': 0.1, 'next8': 1.0, 'next32': 1.0}
    r2 = {'stakes': 0.382, 'now': 0.564, 'next8': 0.177, 'next32': 0.248}
    desc = {'stakes': 'log |g_fut|: how much the next 32 tokens depend on this state',
            'now': 'log |g_now|: how much the next token depends on this state',
            'next8': 'forecast mean surprisal (nats) of the next 8 tokens after the next one',
            'next32': 'forecast mean surprisal (nats) of the next 32 tokens after the next one'}
    names = list(Y)
    rg = Ridge(X)
    W = np.zeros((len(names), D), np.float32)
    b = np.zeros(len(names), np.float32)
    stats = {}
    for i, n in enumerate(names):
        rows = clean if n.startswith('next') else np.ones(len(X), bool)
        if rows.all():
            Wn, mu = rg.fit(Y[n][:, None].astype(np.float32), lam[n])
            mu_x, sd_x = rg.mu, rg.sd
        else:
            r = Ridge(X[rows])
            Wn, mu = r.fit(Y[n][rows][:, None].astype(np.float32), lam[n])
            mu_x, sd_x = r.mu, r.sd
            del r
        W[i] = (Wn[:, 0] / sd_x).astype(np.float32)
        b[i] = float(mu[0] - W[i] @ mu_x)
        pred = X @ W[i] + b[i]
        stats[n] = dict(mean=float(pred.mean()), sd=float(pred.std()),
                        pct={str(q): float(np.percentile(pred, q)) for q in (1, 5, 25, 50, 75, 95, 99)})
        print(f'{n:7s} lambda {lam[n]:g}  fineweb predictions mean {pred.mean():+.3f} sd {pred.std():.3f}')
    np.concatenate([W.reshape(-1), b]).astype(np.float32).tofile(a.out + '.f32')
    json.dump(dict(layer=40, n_embd=D, names=names, desc=desc, test_r2=r2, lam=lam, stats=stats,
                   layout='f32 [n][n_embd] weights then [n] biases; readout = W h + b, h = block-40 output',
                   source='homeo/value_readout_export.py (VL2, H2)'), open(a.out + '.json', 'w'), indent=1)
    print(f'wrote {a.out}.f32 and .json')


if __name__ == '__main__':
    main()
