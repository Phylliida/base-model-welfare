#!/usr/bin/env python3
"""H2 of the Value Lens proposal: does the model represent a forecast of its own future predictability,
beyond what it already knows about the past and the present?

Target at position s: mean surprisal of the next K tokens (x_{s+2} .. x_{s+K+1}, i.e. -l_{s+1} .. -l_{s+K}),
for K = 8 and 32. The next token's own surprisal (-l_s) is left out: its expectation is the current entropy.
Baseline features (all known at s): current entropy H_s, mean surprisal over the last 32 tokens (the slow
document variable from S1), the current token's surprisal, the last 8 tokens' mean surprisal, and position.

Reported on held-out windows (default: the 300 windows with the highest fineweb offsets, so train and test
share no document; --split index uses windows 900-1199):
  baseline R2         OLS on the baseline features
  probe R2            ridge on the layer activation h_s alone
  combined R2         baseline OLS, plus a ridge from h_s to the baseline's residual
  added R2            combined minus baseline: what the state adds beyond the known running averages
  within-window       the same with each window's mean removed from targets and predictions

With --clean (default on), positions whose 32-token horizon contains a blank-line token are dropped
(fineweb joins documents with blank lines).

usage: value_forecast.py [--value /mnt/models/homeo/value] [--probe /mnt/models/homeo/value_probe] [--layer 40]
"""
import argparse
import json
import os
import sys

import torch  # noqa: F401  (import before numpy on this box)
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from value_probe import P, P_LO, P_HI, Ridge, load_acts, r2, rows, TRAIN, VAL, TEST  # noqa: E402

H = '/mnt/models/homeo'


def blank_tokens():
    toks = json.load(open(f'{H}/value/vocab.json'))
    return {i for i, t in enumerate(toks) if t.count('Ċ') >= 2}  # byte-level BPE: U+010A is '\n'


def features(d, n_win, blank):
    """Per (window, s): targets F8, F32 and baseline features; plus the clean mask."""
    F8, F32, B, clean, offs = [], [], [], [], []
    for w in range(n_win):
        j = json.load(open(f'{d}/w{w:05d}.json'))
        s_ = -np.array(j['ll'])      # s_[i] = surprisal of token i+1
        H_ = np.array(j['entropy'])  # H_[i] = entropy of p_i
        toks = j['tokens']
        offs.append(j['offset'])
        for s in range(P_LO, P_HI + 1):
            F8.append(s_[s + 1:s + 9].mean())
            F32.append(s_[s + 1:s + 33].mean())
            B.append([H_[s], s_[s - 32:s].mean(), s_[s - 1], s_[s - 8:s].mean(), s / 192.0])
            clean.append(not any(t in blank for t in toks[s + 1:s + 34]))
    return (np.array(F8, np.float32), np.array(F32, np.float32), np.array(B, np.float32), np.array(clean),
            np.array(offs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--value', default=f'{H}/value')
    ap.add_argument('--probe', default=f'{H}/value_probe/main')
    ap.add_argument('--layer', type=int, default=40)
    ap.add_argument('--all', action='store_true', help='keep positions whose horizon crosses a blank line')
    ap.add_argument('--json', default=None)
    ap.add_argument('--split', default='offset', choices=['index', 'offset'],
                    help='offset: train/val/test are contiguous blocks of the fineweb file, so no document is split')
    a = ap.parse_args()
    torch.set_num_threads(48)
    n_win = 1200
    F8, F32, B, clean, offs = features(a.value, n_win, blank_tokens())
    o = np.sort(offs)
    print(f'window offsets: min gap {np.diff(o).min()} tokens (windows are {192}); '
          f'{(np.diff(o) < 192).sum()} overlapping pairs')
    X, base, _ = load_acts(a.probe, n_win, layer=a.layer)
    Y = np.stack([F8, F32], 1)
    names = ['next 8', 'next 32']
    keep = np.ones(len(Y), bool) if a.all else clean
    print(f'layer {a.layer}: {keep.sum()} of {len(keep)} positions used ({"all" if a.all else "clean"})')

    splits = (TRAIN, VAL, TEST)
    if a.split == 'offset':
        order = np.argsort(offs, kind='stable')
        splits = (order[:800], order[800:900], order[900:])
    tr, va, te = [np.intersect1d(rows(r), np.flatnonzero(keep)) for r in splits]
    trva = np.concatenate([tr, va])
    Bx = np.hstack([B, np.ones((len(B), 1), np.float32)])
    Bw = np.linalg.lstsq(Bx[trva], Y[trva], rcond=None)[0]
    pb = Bx @ Bw

    # probe: ridge on h alone; combined: baseline OLS plus a ridge from h to the baseline's residual
    res = {}
    for label, Yt in [('probe', Y), ('combined', Y - pb)]:
        rg = Ridge(X[tr])
        best = None
        for lam in [1e-2, 1e-1, 1.0, 10.0, 100.0]:
            W, mu = rg.fit(Yt[tr], lam)
            sc = r2(Yt[va], rg.predict(X[va], W, mu)).mean()
            if best is None or sc > best[1]:
                best = (lam, sc)
        rg = Ridge(X[trva])
        W, mu = rg.fit(Yt[trva], best[0])
        p = rg.predict(X[te], W, mu)
        res[label] = (best[0], p + (pb[te] if label == 'combined' else 0))
        del rg

    def wthn(y, idx):
        win = idx // P
        out = y.copy()
        for wv in np.unique(win):
            m = win == wv
            out[m] -= y[m].mean(0)
        return out

    yt = Y[te]
    out = {'layer': a.layer, 'n_test': int(len(te)), 'clean': not a.all, 'split': a.split}
    print(f'\n  {"target":8s} {"sd":>6s} {"base":>6s} {"probe":>6s} {"comb":>6s} {"added":>6s}   within: '
          f'{"base":>6s} {"probe":>6s} {"comb":>6s} {"added":>6s}')
    for j, n in enumerate(names):
        rb = r2(yt[:, j], pb[te][:, j])
        rp = r2(yt[:, j], res['probe'][1][:, j])
        rc = r2(yt[:, j], res['combined'][1][:, j])
        wy = wthn(yt[:, j:j + 1], te)[:, 0]
        wb = r2(wy, wthn(pb[te][:, j:j + 1], te)[:, 0])
        wp = r2(wy, wthn(res['probe'][1][:, j:j + 1], te)[:, 0])
        wc = r2(wy, wthn(res['combined'][1][:, j:j + 1], te)[:, 0])
        out[n] = dict(sd=float(yt[:, j].std()), base=float(rb), probe=float(rp), combined=float(rc), added=float(rc - rb),
                      within=dict(base=float(wb), probe=float(wp), combined=float(wc), added=float(wc - wb)),
                      lam=dict(probe=res['probe'][0], combined=res['combined'][0]))
        print(f'  {n:8s} {yt[:, j].std():6.3f} {rb:6.3f} {rp:6.3f} {rc:6.3f} {rc - rb:+6.3f}           '
              f'{wb:6.3f} {wp:6.3f} {wc:6.3f} {wc - wb:+6.3f}')
    if a.json:
        json.dump(out, open(a.json, 'w'), indent=1)


if __name__ == '__main__':
    main()
