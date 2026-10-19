"""Reading homeo-score output: single-layer f32 records, or multi-layer f16 records (meta "layers", "dtype": "f16").

    run = ScoreRun(prefix)            # tolerates a run still being written (whole records only)
    run.layers, run.windows, run.n, run.prompt, run.logp, run.ent
    run.G(40)                         # [n, n_embd] float32, summed gradient for a push after block 40
    run.R(40, '13-31', idx)           # [len(idx), n_embd] float32, mean block-40 output over lags 13-31
"""
import json
import os

import numpy as np


class ScoreRun:
    def __init__(self, prefix):
        self.prefix = prefix
        m = self.meta = json.load(open(prefix + '.meta.json'))
        self.D, self.n_gen = m['n_embd'], m['n_gen']
        self.windows = [tuple(w) for w in m['windows']]
        self.layers = list(m['layers']) if 'layers' in m else [m['layer']]
        self.f16 = m.get('dtype') == 'f16'
        NW = len(self.windows)
        head = [('prompt', '<i4'), ('cont', '<i4'), ('tok', '<i4', (self.n_gen,)), ('logp', '<f4', (self.n_gen,)),
                ('ent', '<f4', (self.n_gen,))]
        if self.f16:
            dt = np.dtype(head + [('v', '<f2', (len(self.layers), 1 + NW, self.D))])
        else:
            dt = np.dtype(head + [('G', '<f4', (self.D,)), ('R', '<f4', (NW, self.D))])
        assert dt.itemsize == m['record_bytes'], (dt.itemsize, m['record_bytes'])
        self.n = os.path.getsize(prefix + '.bin') // dt.itemsize
        self.recs = np.memmap(prefix + '.bin', dtype=dt, mode='r', shape=(self.n,))
        self.prompt = np.array(self.recs['prompt'])
        self.logp = np.array(self.recs['logp'])
        self.ent = np.array(self.recs['ent'])

    def li(self, layer):
        if layer not in self.layers:
            raise ValueError(f'layer {layer} not in this run (layers {self.layers[0]}..{self.layers[-1]})')
        return self.layers.index(layer)

    def wi(self, window):
        w = tuple(int(x) for x in window.split('-')) if isinstance(window, str) else tuple(window)
        return self.windows.index(w)

    def G(self, layer, idx=slice(None)):
        if self.f16:
            return np.array(self.recs['v'][idx, self.li(layer), 0], dtype=np.float32)
        self.li(layer)
        return np.array(self.recs['G'][idx], dtype=np.float32)

    def R(self, layer, window, idx=slice(None)):
        if self.f16:
            return np.array(self.recs['v'][idx, self.li(layer), 1 + self.wi(window)], dtype=np.float32)
        self.li(layer)
        return np.array(self.recs['R'][idx, self.wi(window)], dtype=np.float32)

    def whole_prompts(self):
        """prompts with the full number of continuations (the last one may still be in progress)"""
        q, c = np.unique(self.prompt, return_counts=True)
        return q[c == c.max()]
