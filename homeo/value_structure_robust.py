#!/usr/bin/env python3
"""Robustness of VL1's "g_fut has about ten stable directions" (split-half subspace overlap 0.30 for the top 10).

VL1 split the windows into even and odd and used the raw second moment of g_fut. Two problems found in VL3:
the top directions are dominated by a few extreme positions (projections of +300 sd), and windows overlap or
share documents, so the same document can sit in both halves. Here the overlap is recomputed with
  splits:   even/odd windows (as VL1), and contiguous offset blocks (no document in both halves)
  variants: raw; trimmed (positions above the 99.9th percentile of |g| dropped); unit-normalized (g / |g|)
for g_fut and g_now at layer 40, on clean positions. Chance overlap for the top n is about n / 6144.

usage: value_structure_robust.py [--value /mnt/models/homeo/value] [--json out.json]
"""
import argparse
import json
import os
import sys

import torch
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from value_forecast import blank_tokens  # noqa: E402

P_LO, P_HI, D = 32, 158, 6144
P = P_HI - P_LO + 1


def top_vecs(G):
    G = torch.from_numpy(G).double()
    e, V = torch.linalg.eigh(G.T @ G)
    return e.flip(0).numpy(), V.flip(1)[:, :50].numpy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--value', default='/mnt/models/homeo/value')
    ap.add_argument('--json', default=None)
    a = ap.parse_args()
    torch.set_num_threads(48)
    meta = json.load(open(f'{a.value}/meta.json'))
    L, n_win = len(meta['layers']), meta['n_windows']
    blank = blank_tokens()
    res = {}
    offs = np.array([json.load(open(f'{a.value}/w{w:05d}.json'))['offset'] for w in range(n_win)])
    rank = np.empty(n_win, int)
    rank[np.argsort(offs, kind='stable')] = np.arange(n_win)
    for ki, kind in ((2, 'fut'), (0, 'now')):
        G = np.empty((n_win, P, D), np.float32)
        clean = np.zeros((n_win, P), bool)
        for w in range(n_win):
            G[w] = np.memmap(f'{a.value}/w{w:05d}.bin', dtype=np.float16, mode='r', shape=(L, 3, P, D))[0, ki]
            tk = json.load(open(f'{a.value}/w{w:05d}.json'))['tokens']
            clean[w] = [not any(t in blank for t in tk[s + 1:s + 34]) for s in range(P_LO, P_HI + 1)]
        nrm = np.linalg.norm(G, axis=2)
        sq = np.sort((nrm[clean] ** 2))[::-1]
        conc = {f'top {q}%': float(sq[:max(1, int(len(sq) * q / 100))].sum() / sq.sum()) for q in (0.01, 0.1, 1)}
        print(f'\n{kind}: share of the second moment in the largest-|g| positions: '
              + ', '.join(f'{k} {v:.1%}' for k, v in conc.items()))
        cut = np.percentile(nrm[clean], 99.9)
        res[kind] = {'concentration': conc}
        for split in ('even/odd', 'offset blocks'):
            half = (np.arange(n_win) % 2) if split == 'even/odd' else (rank >= n_win // 2).astype(int)
            for variant in ('raw', 'trimmed', 'normalized'):
                tops = []
                for h in (0, 1):
                    m = clean & (half[:, None] == h)
                    if variant == 'trimmed':
                        m &= nrm < cut
                    X = G[m]
                    if variant == 'normalized':
                        X = X / np.linalg.norm(X, axis=1, keepdims=True)
                    e, V = top_vecs(X)
                    tops.append((e, V))
                share10 = float(tops[0][0][:10].sum() / tops[0][0].sum())
                ov = {n: float(np.sum((tops[0][1][:, :n].T @ tops[1][1][:, :n]) ** 2) / n) for n in (1, 10, 50)}
                res[kind][f'{split} / {variant}'] = dict(overlap=ov, share10=share10)
                print(f'  {split:13s} {variant:10s}  top-10 share {share10:.3f}   overlap top 1 / 10 / 50: '
                      f'{ov[1]:.3f} / {ov[10]:.3f} / {ov[50]:.3f}   (chance {1 / D:.4f} / {10 / D:.4f} / {50 / D:.4f})', flush=True)
        del G
    if a.json:
        json.dump(res, open(a.json, 'w'), indent=1)


if __name__ == '__main__':
    main()
