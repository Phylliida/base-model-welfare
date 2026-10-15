#!/usr/bin/env python3
"""Compare value-lens readouts across scenarios (Antra's ordering: rich worldbuilding > boring > loops).

Groups: fineweb (main run), its easiest / hardest / highest-stakes tenth, phrase loops, single-token loops,
and model-written fiction (value_scenarios_prep.py). For loop windows, the loop region (positions >= 100)
(positions 100-158, all 32-token horizons inside the loop) is compared with the same positions of the
paired unmodified window.

Readouts per position s (layer 40 unless noted):
  level   log-likelihood of the next token
  stakes  |g_fut|: how much the next 32 tokens' log-likelihood depends on the state at s
  now     |g_now|
  price of a few library directions (per push of 0.1 x the residual norm), future part

usage: value_scenarios.py [--main /mnt/models/homeo/value] [--scen /mnt/models/homeo/value_scen]
"""
import argparse
import glob
import json
import os

import torch  # noqa: F401  (import before numpy on this box)
import numpy as np

H = '/mnt/models/homeo'
RESID = {40: 261.1, 44: 364.0, 50: 565.4, 56: 866.8}
LIB = [('tempL40', f'{H}/s2opt/vec_temp1.3_opt2_L40.f32', 40),     # temperature 1.3, optimized
       ('tempL50', f'{H}/s2sweep/temp1.3_L50.f32', 50),            # temperature 1.3, sweep
       ('tailL56', f'{H}/s2sweep/p0.03_r1_L56.f32', 56),           # plausible-tail
       ('caaL44', f'{H}/s2/vec_caa_L44.f32', 44)]                  # contrastive weird-token


def load_run(d):
    meta = json.load(open(f'{d}/meta.json'))
    layers, dim = meta['layers'], meta['n_embd']
    s_lo, s_hi = meta['positions']
    P = s_hi - s_lo + 1
    lib = [(n, np.fromfile(p, dtype=np.float32), L) for n, p, L in LIB if L in layers]
    lib = [(n, v / np.linalg.norm(v), L) for n, v, L in lib]
    rows = {}
    for f in sorted(glob.glob(f'{d}/w*.json')):
        if not os.path.exists(f[:-5] + '.bin'):
            continue
        j = json.load(open(f))
        arr = np.fromfile(f[:-5] + '.bin', dtype=np.float16).astype(np.float32).reshape(len(layers), 3, P, dim)
        li = layers.index(40)
        r = dict(level=np.array(j['ll'])[s_lo:s_hi + 1], stakes=np.linalg.norm(arr[li, 2], axis=1),
                 now=np.linalg.norm(arr[li, 0], axis=1))
        for n, v, L in lib:
            r[n] = arr[layers.index(L), 2] @ v * 0.1 * RESID[L]
        rows[j['window']] = r
    return meta, rows, [n for n, _, _ in lib]


def summarize(name, rows, keys, sel=slice(None)):
    if not rows:
        return
    vals = {k: np.concatenate([r[k][sel] for r in rows]) for k in keys}
    cells = '  '.join(f'{vals[k].mean():+8.3f}' if k not in ('stakes', 'now') else f'{vals[k].mean():8.3f}' for k in keys)
    print(f'  {name:34s} {len(rows):5d}  {cells}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--main', default=f'{H}/value')
    ap.add_argument('--scen', default=f'{H}/value_scen')
    a = ap.parse_args()
    meta, main_rows, libn = load_run(a.main)
    s_lo = meta['positions'][0]
    smeta, scen_rows, _ = load_run(f'{a.scen}/out')
    manifest = json.load(open(f'{a.scen}/manifest.json'))
    keys = ['level', 'stakes', 'now'] + libn
    hdr = '  '.join(f'{k[:8]:>8s}' for k in keys)
    print(f'value-lens scenarios: {len(main_rows)} fineweb windows, {len(scen_rows)} scenario windows')
    print('  future prices of library directions are nats per push of 0.1 x the residual norm (sign: + helps the next 32 tokens)')

    fw = list(main_rows.values())
    lev = np.array([r['level'].mean() for r in fw]); stk = np.array([r['stakes'].mean() for r in fw])
    q = max(1, len(fw) // 10)
    print(f'\n  {"group (whole window)":34s} {"n":>5s}  {hdr}')
    summarize('fineweb, all', fw, keys)
    summarize('fineweb, easiest tenth (boring)', [fw[i] for i in np.argsort(-lev)[:q]], keys)
    summarize('fineweb, hardest tenth', [fw[i] for i in np.argsort(lev)[:q]], keys)
    summarize('fineweb, highest-stakes tenth', [fw[i] for i in np.argsort(-stk)[:q]], keys)
    by = {}
    for idx, m in enumerate(manifest):
        if idx in scen_rows:
            by.setdefault(m['scenario'], []).append((m, scen_rows[idx]))
    summarize('fiction (model-written)', [r for _, r in by.get('fiction', [])], keys)

    # loops: loop region (positions >= 100) against the same positions in the paired fineweb window
    sel = slice(100 - s_lo, None)
    print(f'\n  {"loop region (positions 100-158)":34s} {"n":>5s}  {hdr}')
    pairs = sorted({m['pair'] for m, _ in by.get('phrase loop', [])})
    summarize('paired fineweb, same positions', [main_rows[p] for p in pairs if p in main_rows], keys, sel)
    summarize('phrase loop (period 12)', [r for _, r in by.get('phrase loop', [])], keys, sel)
    summarize('token loop ("the the the")', [r for _, r in by.get('token loop', [])], keys, sel)
    summarize('fiction, same positions', [r for _, r in by.get('fiction', [])], keys, sel)


if __name__ == '__main__':
    main()
