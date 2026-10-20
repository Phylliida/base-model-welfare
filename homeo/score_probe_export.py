"""Direction probes for the loom (llama-server --probe-dirs): every layer-sweep direction that clears the noise.

Takes the directions of score_describe.py (sweep.describe_cap64) at the layers the writeup calls resolved, keeps those
whose held-out kappa is beyond +-0.03 on their own side (the set score_sensor.py reads), and writes:
  PATH.f32   [n][n_embd] unit directions u, each oriented so that +u is its family's pole (deeper into the sentence,
             inside a name, chattier, more structured, at a break, less predictable) at every layer, so a family keeps
             its color across layers; "flipped" marks the ones whose sign is the opposite of the writeup's
  PATH.json  {"n_embd", "names", "layers"} for llama-server, plus for the loom: per layer the noise edge and the held-out
             kappas, per direction its strength (held-out kappa), family, reading, effectors, contexts, and the
             distribution of u.h / |h| over the natural-text capture (score/sense, 192,000 positions of FineWeb
             rollouts) as the color scale.

usage: score_probe_export.py [--out /mnt/models/homeo/score/probe_dirs]
"""
import argparse
import json
import os
import sys

import torch  # noqa: F401  (before numpy: this venv's numpy needs torch's libz)
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score_io import ScoreRun  # noqa: E402
from score_words import O, FNAME, toks, reading, poles, ctx, families, common_tokens, layer_resolved, clears  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--out', default=f'{O}/probe_dirs')
a = ap.parse_args()

D = json.load(open(f'{O}/sweep.describe_cap64.json'))
S = json.load(open(f'{O}/sense/sensor.json'))
SENS = {(r['layer'], r['side'], r['rank']): r for r in S['directions']}
FAM = families()
common = common_tokens(ScoreRun(f'{O}/sweep'))
meta = json.load(open(f'{O}/sense/meta.json'))
n_embd, K, F = meta['n_embd'], meta['proj_k'], meta['n_extra']
n = meta['n_samples']
PCT = [1, 5, 10, 25, 50, 75, 90, 95, 99]
# the feature whose high end is +u, per family
POLE = {'sentence': 'since_end', 'name': 'name', 'chatty': 'pron32', 'prose/struct': 'markup16', 'break': 'at_end', 'entropy': 'entropy'}

U, names, layers, dirs, lays = [], [], [], [], []
for r in D['layers']:
    L = r['layer']
    if not layer_resolved(r):
        continue
    hp, ha = r['heldout_pushback'], r['heldout_amplify']
    pr = np.fromfile(f'{O}/sense/proj_L{L:02d}.f32', dtype=np.float32, count=n * (K + F + 1)).reshape(n, K + F + 1)
    hb, norm = pr[:, :K].astype(np.float64), pr[:, -1].astype(np.float64)
    B = np.fromfile(f'{O}/sweep.L{L}.capbasis.f32', dtype=np.float32, count=K * n_embd).reshape(K, n_embd).astype(np.float64)
    n_kept = 0
    for d in r['directions']:
        side, rank = d['side'], d['rank']
        ho = (hp if side == 'pushback' else ha)[rank]
        if not clears(side, ho):
            continue
        u = np.fromfile(f'{O}/sweep.describe_cap64_dirs/L{L}_{side}_{rank}.f32', dtype=np.float32).astype(np.float64)
        sr = SENS[(L, side, rank)]
        fam = FAM[(L, side, rank)][0]
        flip = fam in POLE and sr['corr_cos'][POLE[fam]] < 0
        if flip:
            # -u: correlations change sign, the poles and contexts swap, the effects of a push reverse
            u = -u
            sr = dict(sr, corr_cos={f: -v for f, v in sr['corr_cos'].items()}, high=sr['low'], low=sr['high'])
            d = dict(d, more=d['less'], less=d['more'], d_sentence_ends=-d['d_sentence_ends'], d_logp=-d['d_logp'])
        cos = hb @ (B @ u) / norm
        hi, lo = poles(sr)
        name = f'L{L}.{side}.{rank}'
        U.append(u.astype(np.float32)); names.append(name); layers.append(L)
        dirs.append({
            'name': name, 'layer': L, 'side': side, 'rank': rank, 'flipped': bool(flip),
            'heldout': ho, 'kappa': d['kappa'], 'se': d['se'], 'capacity': d['capacity'],
            'family': fam, 'family_label': FNAME[fam], 'reading': reading(sr, fam), 'high': hi, 'low': lo,
            'reading_neg': reading(dict(sr, corr_cos={f: -v for f, v in sr['corr_cos'].items()}), fam),  # for the loom's sign flip
            'corr_cos': {f: round(v, 3) for f, v in sr['corr_cos'].items() if f != 'norm'},
            'more': toks(d['more'], common), 'less': toks(d['less'], common),
            'd_sentence_ends': d['d_sentence_ends'], 'd_logp': d['d_logp'],
            'ctx_high': ctx(sr['high']), 'ctx_low': ctx(sr['low']),
            'cos_stats': {'mean': float(cos.mean()), 'sd': float(cos.std()),
                          'pct': {str(p): float(v) for p, v in zip(PCT, np.percentile(cos, PCT))}},
        })
        n_kept += 1
    lays.append({'layer': L, 'edge': (r['null_top95'] - r['null_bottom5']) / 2, 'heldout_pushback': hp, 'heldout_amplify': ha,
                 'output_regime': L >= 57, 'n_dirs': n_kept})
    print(f'L{L}: {n_kept} directions', flush=True)

np.stack(U).tofile(a.out + '.f32')
json.dump({'n_embd': n_embd, 'names': names, 'layers': layers, 'per_layer': lays, 'directions': dirs,
           'color': 'u.h / |h|, as a percentile of the natural-text capture (score/sense)',
           'source': {'describe': f'{O}/sweep.describe_cap64.json', 'sensor': f'{O}/sense/sensor.json'}},
          open(a.out + '.json', 'w'), ensure_ascii=False, indent=1)
print(f'{len(names)} directions at {len(lays)} layers -> {a.out}.f32, {a.out}.json')
