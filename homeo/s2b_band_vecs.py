#!/usr/bin/env python3
"""S2b: steering vectors for "promote only tokens with probability p" from homeo-band output.

Per level p (arms: 0 normal, 1..L band:p, L+1..2L temp:p) and layer, mean-difference vectors:
  normal     mean(band:p) - mean(normal)
  temp       mean(band:p) - mean(temp:p)            (same per-step expected surprisal)
  bracket    mean(band:p) - [w mean(band:p_hi) + (1-w) mean(band:p_lo)]
             w set so the neighbors' realized mean surprisal equals band:p's; anything linear
             in surprisal cancels, a component peaked at p survives (second difference in log p)
Split-half cosine (by prefix parity) checks that a vector is signal, not noise.
Vectors are written unit-norm x mean residual norm (homeo-steer --scales = fraction of norm).

usage: s2b_band_vecs.py DATA_DIR OUT_DIR [--s1 /mnt/models/homeo/s1]
"""
import torch  # before numpy (lib resolution on this box)
import argparse
import json
import os

import numpy as np

STEP = np.dtype([('prefix', 'i4'), ('arm', 'i4'), ('step', 'i4'), ('token', 'i4'), ('p', 'f4'),
                 ('H', 'f4'), ('T', 'f4'), ('hit', 'i4'), ('bm', '8f4')])
SAMP = np.dtype([('prefix', 'i4'), ('arm', 'i4'), ('step', 'i4'), ('token', 'i4'), ('seq', 'i4'),
                 ('pos', 'i4'), ('p', 'f4'), ('H', 'f4')])


def cos(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('data')
    ap.add_argument('out')
    ap.add_argument('--s1', default='/mnt/models/homeo/s1')
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    meta = json.load(open(f'{args.data}/meta.json'))
    levels, L = meta['levels'], len(meta['levels'])
    steps = np.fromfile(f'{args.data}/steps.bin', dtype=STEP)
    S = np.fromfile(f'{args.data}/samples.bin', dtype=SAMP)
    K = meta['n_arms']
    has_temp = K == 1 + 2 * L
    surp = {k: float(-np.log(steps['p'][steps['arm'] == k]).mean()) for k in range(K)}
    hit = {k: float(steps['hit'][steps['arm'] == k].mean()) for k in range(1, 1 + L)}
    print('realized mean surprisal (nats): normal %.2f | ' % surp[0] +
          ' '.join(f'band:{levels[i]:g} {surp[1 + i]:.2f} (hit {hit[1 + i]:.2f})' for i in range(L)) +
          (' | ' + ' '.join(f'temp:{levels[i]:g} {surp[1 + L + i]:.2f}' for i in range(L)) if has_temp else ''))

    s1caa = {}
    if os.path.exists(f'{args.s1}/s1_probe_dirs.npz'):
        D = np.load(f'{args.s1}/s1_probe_dirs.npz')
        s1caa = {int(k.split('_L')[1]): D[k] for k in D.files if k.startswith('caa_hi_lo_L')}

    order = np.argsort(np.array(levels))[::-1]  # descending p
    info = {'surprisal': surp, 'hit': hit, 'vectors': {}}
    for il in meta['layers']:
        A = np.memmap(f'{args.data}/acts_L{il:02d}.f16', dtype=np.float16, mode='r').reshape(-1, meta['n_embd'])
        A = np.asarray(A, dtype=np.float32)
        resid = float(np.linalg.norm(A[S['arm'] == 0], axis=1).mean())
        half = S['prefix'] % 2

        def arm_mean(k, h=None):
            m = S['arm'] == k
            if h is not None:
                m &= half == h
            return A[m].mean(0)

        for i in range(L):
            band = 1 + i
            contrasts = {'normal': {0: 1.0}}
            if has_temp:
                contrasts['temp'] = {1 + L + i: 1.0}
            pos = int(np.nonzero(order == i)[0][0])
            if 0 < pos < L - 1:
                hi, lo = 1 + order[pos - 1], 1 + order[pos + 1]  # higher-p and lower-p neighbors
                w = (surp[lo] - surp[band]) / (surp[lo] - surp[hi])
                w = float(np.clip(w, 0.0, 1.0))
                contrasts['bracket'] = {hi: w, lo: 1.0 - w}
            for name, neg in contrasts.items():
                def vec(h=None):
                    return arm_mean(band, h) - sum(wt * arm_mean(k, h) for k, wt in neg.items())
                v, v0, v1 = vec(), vec(0), vec(1)
                key = f'p{levels[i]:g}_{name}_L{il}'
                rec = {'norm_frac': float(np.linalg.norm(v) / resid), 'split_half_cos': cos(v0, v1),
                       'neg_weights': {str(k): wt for k, wt in neg.items()}}
                if il in s1caa:
                    rec['cos_s1_surprise_caa'] = cos(v, s1caa[il])
                info['vectors'][key] = rec
                (v / np.linalg.norm(v) * resid).astype(np.float32).tofile(f'{args.out}/vec_{key}.f32')
                print(f'L{il:02d} p={levels[i]:<5g} {name:>7}: |v|/resid {rec["norm_frac"]:.3f}  split-half cos {rec["split_half_cos"]:+.3f}'
                      + (f'  cos(S1 surprise vec) {rec["cos_s1_surprise_caa"]:+.3f}' if 'cos_s1_surprise_caa' in rec else ''))
    json.dump(info, open(f'{args.out}/band_vecs_info.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
