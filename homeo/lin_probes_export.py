#!/usr/bin/env python3
"""Bundle the saved all-layer rollout probes into one file for llama-server --lin-probes (and the loom).

Inputs in DIR (/mnt/models/homeo/rollprobe), each f32 [n_targets][61][6144] weights then [n_targets] biases on raw
block outputs (value = sum_L w_L . h_L + b), with names in the matching json:
  rollprobe_weights.f32       difficulty forecasts, strength chosen on val (lambda 10; added: 31.6)   key prefix fc
  rollprobe_l100_weights.f32  the same at lambda 100 (forecast change ~90% reliable)                  key prefix fc100
  rollprobe_past_weights.f32  past difficulty (mean surprisal of the last 8 / 32 / 128 / all tokens)  key prefix past
  rollprobe_baseline_weights.f32  entropy, surprisal, ... decoded from the state                    key prefix base
(missing files are skipped). Writes DIR/lin_probes.f32 ([n][61][6144] then [n]) and DIR/lin_probes.json: names (keys),
and per probe a label, group, test R2, percentiles of its predictions on the test rows (the loom's color scale) and,
for forecasts, the horizon K and percentiles of the forecast change df_t = f(t) - f(t-1) and of the TD error
-c_t - K df_t on the test pairs (c_t = surprisal of token t; the loom derives both per token).

Without the rows files (e.g. from the repo copy, probes/rollout) the color scales are taken from an existing
DIR/lin_probes.json.

usage: lin_probes_export.py [--dir /mnt/models/homeo/rollprobe]
"""
import argparse
import json
import os

import torch  # noqa: F401  (before numpy on this box)
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('--dir', default='/mnt/models/homeo/rollprobe')
a = ap.parse_args()
NL, D = 61, 6144
SOURCES = [
    ('fc', 'rollprobe', 'forecast (best fit)', 'joint'),
    ('fc100', 'rollprobe_l100', 'forecast (smooth, lambda 100)', 'joint'),
    ('past', 'rollprobe_past', 'past difficulty', 'results'),
    ('base', 'rollprobe_baseline', 'decoded text statistics', 'results'),
]
LABEL = {
    'next 1': "next token's surprisal", 'next 8': 'difficulty, next 8', 'next 32': 'difficulty, next 32',
    'next 128': 'difficulty, next 128', 'added 32': 'state beyond baseline, next 32', 'added 128': 'state beyond baseline, next 128',
    'past 8': 'past difficulty, last 8', 'past 32': 'past difficulty, last 32', 'past 128': 'past difficulty, last 128',
    'past all': 'past difficulty, whole context', 'entropy': 'next-token entropy', 'surprisal': "current token's surprisal",
    'entropy prev': 'entropy before the current token', 'excess surprisal': 'surprisal minus expected',
    'log rank': "log rank of the current token", 'log context': 'log context length',
}
PCT = [1, 2.5, 5, 10, 25, 50, 75, 90, 95, 97.5, 99]
pcts = lambda v: {str(q): float(x) for q, x in zip(PCT, np.percentile(v, PCT))}
W, B, names, probes = [], [], [], []
OLD = {p['key']: p for p in json.load(open(f'{a.dir}/lin_probes.json'))['probes']} if os.path.exists(f'{a.dir}/lin_probes.json') else {}
SCALES = ('pct', 'df_pct', 'td_pct')
for prefix, stem, group, key in SOURCES:
    wf, jf = f'{a.dir}/{stem}_weights.f32', f'{a.dir}/{stem}.json'
    if not (os.path.exists(wf) and os.path.exists(jf)):
        print(f'skip {stem} (not found)')
        continue
    meta = json.load(open(jf))
    nm = meta['names']
    raw = np.fromfile(wf, dtype=np.float32)
    assert raw.size == len(nm) * NL * D + len(nm), (stem, raw.size)
    W.append(raw[:len(nm) * NL * D].reshape(len(nm), NL, D))
    B.append(raw[len(nm) * NL * D:])
    res = meta[key]
    have_rows = os.path.exists(f'{a.dir}/{stem}_rows.npz') and os.path.exists(f'{a.dir}/rollprobe_rows.npz')
    if have_rows:
        rows = np.load(f'{a.dir}/{stem}_rows.npz', allow_pickle=True)
        base = np.load(f'{a.dir}/rollprobe_rows.npz', allow_pickle=True)  # pairs and surprisal (same row order in every rows file)
        sp, pair = base['split'], base['pair']
        te = np.flatnonzero(sp == 2)
        first = te[pair[te] >= 0]
        first = first[sp[pair[first]] == 2]
        rnames = list(rows['names'])
    for t in nm:
        k = f'{prefix}:{t}'
        names.append(k)
        p = {'key': k, 'target': t, 'group': group, 'label': LABEL.get(t, t), 'test_r2': res[t]['test'],
             'source': wf}
        if t.startswith('next ') and t != 'next 1':
            p['horizon'] = int(t.split()[1])  # forecasts of mean surprisal of the K tokens after the next one
        if have_rows:
            f = rows['pred'][:, rnames.index(t)]
            p['pct'] = pcts(f[te])
            if 'horizon' in p:
                df = f[pair[first]] - f[first]
                p['df_pct'] = pcts(df)
                p['td_pct'] = pcts(-base['next_1'][first] - p['horizon'] * df)
        else:
            p.update({k_: OLD[k][k_] for k_ in SCALES if k in OLD and k_ in OLD[k]})
        if t.startswith('added'):
            p['note'] = 'predicts the residual of the baseline in rollprobe.json baseline_coef'
        probes.append(p)
    print(f'{stem}: {len(nm)} probes')
W = np.concatenate(W)
B = np.concatenate(B)
with open(f'{a.dir}/lin_probes.f32', 'wb') as fh:
    W.reshape(-1).tofile(fh)
    B.astype(np.float32).tofile(fh)
json.dump({'n_embd': D, 'n_layer': NL, 'names': names, 'probes': probes,
           'units': 'nats per token (forecasts, past difficulty, surprisal, entropy); log units for log rank / log context',
           'layout': 'f32 [n][61][6144] then [n] bias; value = sum_L w_L . h_L + b on raw block outputs'},
          open(f'{a.dir}/lin_probes.json', 'w'), indent=1)
print(f'{len(names)} probes -> {a.dir}/lin_probes.{{f32,json}}')
