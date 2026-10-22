"""Shared paths and helpers for the writeup analyses (paths from config.sh's environment variables)."""
import json
import os

import torch  # noqa: F401  (import before numpy: on the original machine numpy needs torch's libz)
import numpy as np

PROBES = os.environ.get('PROBES', '/mnt/models/homeo/rollprobe')
ACTS = os.environ.get('ACTS', '/data2/homeo/rollprobe_acts')
SEQS = os.environ.get('SEQS', '/mnt/models/homeo/rollouts2')
VALUE_SCEN = os.environ.get('VALUE_SCEN', '/mnt/models/homeo/value_scen')
RESULTS = os.environ.get('RESULTS', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'results'))
os.makedirs(RESULTS, exist_ok=True)
LABEL = np.dtype([('seq', '<i4'), ('pos', '<i4'), ('token', '<i4'), ('rank_prev', '<i4'), ('surprisal', '<f4'),
                  ('entropy_prev', '<f4'), ('entropy', '<f4'), ('pad', '<f4')])


def r2(y, p):
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def rows(tag=''):
    """the fit's per-row file: positions, targets, features, split, val / test predictions"""
    return np.load(f'{PROBES}/rollprobe{tag}_rows.npz', allow_pickle=True)


def result(tag=''):
    return json.load(open(f'{PROBES}/rollprobe{tag}.json'))


def past_all_mean(z):
    """mean surprisal of tokens 1..s (the entire past context) for every row of a rows file, from the labels"""
    out = np.empty(len(z['pos']))
    for k in np.unique(z['chunk']):
        lab = np.fromfile(f'{ACTS}/c{k}/labels.bin', dtype=LABEL)
        st = list(np.flatnonzero(lab['pos'] == 0)) + [len(lab)]
        cs = [np.concatenate([[0.0], np.cumsum(np.nan_to_num(lab['surprisal'][st[q]:st[q + 1]].astype(np.float64)))])
              for q in range(len(st) - 1)]
        for i in np.flatnonzero(z['chunk'] == k):
            d = z['pos'][i]
            out[i] = cs[z['seq'][i]][d + 1] / d  # token 0 has no surprisal
    return out


class Out:
    """collect lines, print them and write RESULTS/name"""

    def __init__(self, name):
        self.name, self.lines = name, []

    def __call__(self, s=''):
        print(s)
        self.lines.append(s)

    def save(self):
        open(os.path.join(RESULTS, self.name), 'w').write('\n'.join(self.lines) + '\n')
        print(f'-> {os.path.join(RESULTS, self.name)}')
