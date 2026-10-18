"""PCA basis of layer-40 states for plan B (homeo-ident): top-K principal directions as orthonormal rows.

The states are the VL2 activations (fineweb windows, /mnt/models/homeo/value_probe/main, positions 16..). At a
fixed layer every change of the state between positions is driven by tokens, so the high-variance directions
are the ones the token stream moves: the actuator side of a token-mediated regulator.

usage: ident_basis.py [--k 256] [--rows 80000] [--out /mnt/models/homeo/ident/basis_pca256_L40]
writes OUT.f32 (f32 [K][6144]) and OUT.json (variance fractions, outlier concentration per component)
"""
import argparse
import json
import sys

import torch  # noqa: F401  (import before numpy on this box)
import numpy as np

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from value_probe import SAMPLE, D  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--k', type=int, default=256)
ap.add_argument('--rows', type=int, default=80000)
ap.add_argument('--out', default='/mnt/models/homeo/ident/basis_pca256_L40')
a = ap.parse_args()

d = '/mnt/models/homeo/value_probe/main'
rec = np.fromfile(f'{d}/samples.bin', dtype=SAMPLE)
acts = np.memmap(f'{d}/acts_L40.f16', dtype=np.float16, mode='r', shape=(len(rec), D))
idx = np.flatnonzero(rec['pos'] >= 16)
rng = np.random.default_rng(0)
idx = np.sort(rng.choice(idx, size=min(a.rows, len(idx)), replace=False))
torch.set_num_threads(32)
mu = torch.zeros(D, dtype=torch.float64)
C = torch.zeros(D, D, dtype=torch.float64)
n = 0
for c0 in range(0, len(idx), 8192):
    X = torch.from_numpy(np.asarray(acts[idx[c0:c0 + 8192]], dtype=np.float32))
    mu += X.double().sum(0)
    C += (X.T @ X).double()
    n += len(X)
mu /= n
C = C / n - torch.outer(mu, mu)
ev, V = torch.linalg.eigh(C)
ev, V = ev.flip(0), V.flip(1)
tot = float(ev.sum())
B = V[:, :a.k].T.float().contiguous().numpy()
B.tofile(a.out + '.f32')
cum = np.cumsum(ev.numpy()) / tot
info = {
    'rows': n, 'k': a.k, 'total_variance': tot, 'mean_norm': float(mu.norm()),
    'var_frac': [float(x) / tot for x in ev[:a.k]],
    'cum_var_at': {str(k): float(cum[k - 1]) for k in (1, 8, 16, 32, 64, 128, 256, 512, 1024)},
    # how concentrated each component is on single coordinates (massive-activation dims)
    'max_abs_coord': [float(np.abs(B[i]).max()) for i in range(a.k)],
    'argmax_coord': [int(np.abs(B[i]).argmax()) for i in range(a.k)],
}
json.dump(info, open(a.out + '.json', 'w'), indent=1)
print('rows', n, 'mean |mu|', round(info['mean_norm'], 1), 'total var', round(tot, 1))
print('cumulative variance:', {k: round(v, 3) for k, v in info['cum_var_at'].items()})
print('first 16 components, max |coord|:', [round(x, 2) for x in info['max_abs_coord'][:16]])
print('argmax coords:', info['argmax_coord'][:16])
