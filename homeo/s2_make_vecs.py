#!/usr/bin/env python3
"""S2: write steering vectors for homeo-steer from s1_probe_dirs.npz.

Each vector is unit-normalized, then scaled to the mean natural residual norm at
its layer, so homeo-steer --scales are fractions of the typical residual norm.
  probe_s  ridge readout direction for surprisal (raw activation coords)
  caa      mean(h | forced bin >= 8) - mean(h | forced bin <= 1)
  rand     Gaussian control

usage: s2_make_vecs.py DATA_DIR OUT_DIR --layers 32,44 [--seed 0]
"""
import torch  # before numpy (lib resolution on this box)
import argparse
import json
import os

import numpy as np

from s1_probe import SAMPLE, acts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('data')
    ap.add_argument('out')
    ap.add_argument('--layers', required=True)
    ap.add_argument('--seed', type=int, default=0)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    meta = json.load(open(f'{args.data}/meta.json'))
    S = np.fromfile(f'{args.data}/samples.bin', dtype=SAMPLE)
    D = np.load(f'{args.data}/s1_probe_dirs.npz')
    rng = np.random.default_rng(args.seed)
    nat = np.nonzero(S['kind'] == 0)[0]
    nat = rng.choice(nat, min(5000, len(nat)), replace=False)
    info = {}
    for il in [int(x) for x in args.layers.split(',')]:
        A = acts(args.data, meta, il)
        norm = float(np.linalg.norm(A[np.sort(nat)].astype(np.float32), axis=1).mean())
        vecs = {
            'probe_s': D[f'w_raw_L{il}'][:, 0],
            'caa': D[f'caa_hi_lo_L{il}'],
            'rand': rng.standard_normal(meta['n_embd']),
        }
        info[il] = {'resid_norm': norm, 'caa_raw_norm': float(np.linalg.norm(D[f'caa_hi_lo_L{il}']))}
        for name, v in vecs.items():
            v = (v / np.linalg.norm(v) * norm).astype(np.float32)
            v.tofile(f'{args.out}/vec_{name}_L{il}.f32')
        cos = float(vecs['probe_s'] @ vecs['caa'] / np.linalg.norm(vecs['probe_s']) / np.linalg.norm(vecs['caa']))
        info[il]['cos_probe_caa'] = cos
        print(f'L{il}: resid norm {norm:.1f}  |caa| {info[il]["caa_raw_norm"]:.1f}  cos(probe, caa) {cos:.3f}')
    json.dump(info, open(f'{args.out}/vecs_info.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
