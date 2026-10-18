#!/usr/bin/env python3
"""Scenario set 2 (VL4): model-written fiction, boring prose and structured text on the value lens.

Per window (positions 32-158, layer 40): level (mean log-likelihood), stakes (mean |g_fut|), now (mean
|g_now|), progress (mean log-likelihood of positions 96-158 minus 32-95) and the temperature vector's future
price. Group means with standard errors clustered by prompt (the two continuations of a prompt share it), and
pairwise differences with a permutation test over prompts. The fineweb main run is shown for reference.

usage: value_scenarios2.py [--scen /mnt/models/homeo/value_scen2] [--json out.json]
"""
import argparse
import json
import os
import sys

import torch  # noqa: F401  (import before numpy on this box)
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from value_scenarios import load_run  # noqa: E402

H = '/mnt/models/homeo'
KEYS = ['level', 'stakes', 'now', 'progress', 'drift', 'tempL40']


def window_stats(r, s_lo):
    lev = r['level']
    mid = 96 - s_lo
    return dict(level=lev.mean(), stakes=r['stakes'].mean(), now=r['now'].mean(),
                progress=lev[mid:].mean() - lev[:mid].mean(), drift=r['stakes'][mid:].mean() - r['stakes'][:mid].mean(),
                tempL40=r['tempL40'].mean())


def rep4(w, lo=32):
    seen, hit = set(), 0
    for t in range(3, len(w)):
        g = tuple(w[t - 3:t + 1])
        hit += t >= lo and g in seen
        seen.add(g)
    return hit / (len(w) - lo)


def byte_decoder():
    """Decode GLM-4 byte-level BPE ids with the vocab dump from the value lens."""
    voc = json.load(open(f'{H}/value/vocab.json'))
    bs = list(range(ord('!'), ord('~') + 1)) + list(range(ord('¡'), ord('¬') + 1)) + list(range(ord('®'), ord('ÿ') + 1))
    cs, n = bs[:], 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    m = {chr(c): b for b, c in zip(bs, cs)}
    return lambda t: bytes(m.get(ch, 32) for ch in ''.join(voc[x] for x in t)).decode('utf8', 'replace')


def cluster_mean(vals, clusters):
    """Mean and SE with clusters (prompts) as the unit."""
    cm = {}
    for v, c in zip(vals, clusters):
        cm.setdefault(c, []).append(v)
    m = np.array([np.mean(x) for x in cm.values()])
    return m.mean(), m.std(ddof=1) / np.sqrt(len(m)), m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scen', default=f'{H}/value_scen2')
    ap.add_argument('--main', default=f'{H}/value')
    ap.add_argument('--json', default=None)
    a = ap.parse_args()
    meta, rows, _ = load_run(f'{a.scen}/out')
    s_lo = meta['positions'][0]
    manifest = json.load(open(f'{a.scen}/manifest.json'))
    print(f'scenario set 2: {len(rows)} of {len(manifest)} windows done')
    groups = {}
    for i, m in enumerate(manifest):
        if i in rows:
            groups.setdefault(m['scenario'], []).append((m['prompt'], window_stats(rows[i], s_lo)))
    _, main_rows, _ = load_run(a.main)
    fw = [window_stats(r, s_lo) for r in main_rows.values()]

    res = {'n_windows': len(rows), 'groups': {}}
    print(f'\n  {"group":22s} {"windows":>7s} {"prompts":>7s}  ' + '  '.join(f'{k:>16s}' for k in KEYS))
    per = {}
    for g in ['fiction', 'boring', 'structured']:
        if g not in groups:
            continue
        cl = [p for p, _ in groups[g]]
        cells, res['groups'][g] = [], {'windows': len(cl), 'prompts': len(set(cl))}
        per[g] = {}
        for k in KEYS:
            m, se, pm = cluster_mean([s[k] for _, s in groups[g]], cl)
            per[g][k] = pm
            res['groups'][g][k] = dict(mean=float(m), se=float(se))
            cells.append(f'{m:+8.4f} ({se:.4f})')
        print(f'  {g:22s} {len(cl):7d} {len(set(cl)):7d}  ' + '  '.join(cells))
    cells = [f'{np.mean([s[k] for s in fw]):+8.4f} ({np.std([s[k] for s in fw]) / np.sqrt(len(fw)):.4f})' for k in KEYS]
    print(f'  {"fineweb (human)":22s} {len(fw):7d} {"":>7s}  ' + '  '.join(cells))
    res['groups']['fineweb'] = {k: dict(mean=float(np.mean([s[k] for s in fw]))) for k in KEYS}

    rng = np.random.default_rng(0)
    print('\n  differences (prompt-level permutation test, 10000 permutations):')
    res['diffs'] = {}
    for g1, g2 in [('fiction', 'boring'), ('structured', 'boring'), ('fiction', 'structured')]:
        if g1 not in per or g2 not in per:
            continue
        out = []
        for k in KEYS:
            x, y = per[g1][k], per[g2][k]
            d = x.mean() - y.mean()
            pool = np.concatenate([x, y])
            perm = np.array([(lambda q: q[:len(x)].mean() - q[len(x):].mean())(rng.permutation(pool)) for _ in range(10000)])
            p = float((np.abs(perm) >= abs(d)).mean())
            res['diffs'][f'{g1} - {g2}'] = res['diffs'].get(f'{g1} - {g2}', {})
            res['diffs'][f'{g1} - {g2}'][k] = dict(diff=float(d), p=p)
            out.append(f'{k} {d:+.4f} (p {p:.3f})')
        print(f'  {g1} - {g2}: ' + '  '.join(out))
    # difficulty-matched: stakes relative to fineweb's stakes-vs-level curve (quadratic OLS on the 1200 windows)
    lv = np.array([s['level'] for s in fw])
    st = np.array([s['stakes'] for s in fw])
    A = lambda x: np.stack([np.ones_like(x), x, x ** 2], 1)
    coef = np.linalg.lstsq(A(lv), st, rcond=None)[0]
    r2 = 1 - ((st - A(lv) @ coef) ** 2).mean() / st.var()
    print(f'\n  difficulty-matched stakes: fineweb stakes ~ level + level^2 (R2 {r2:.3f}, corr(level, stakes) '
          f'{np.corrcoef(lv, st)[0, 1]:+.3f}); residual = stakes minus the fineweb curve at the window\'s level')
    res['matched'] = dict(coef=coef.tolist(), r2=float(r2), corr_fineweb=float(np.corrcoef(lv, st)[0, 1]), groups={}, diffs={})
    resid = {}
    for g in per:
        cl = [p for p, _ in groups[g]]
        x = np.array([s['level'] for _, s in groups[g]])
        v = np.array([s['stakes'] for _, s in groups[g]]) - A(x) @ coef
        m, se, pm = cluster_mean(v, cl)
        resid[g] = pm
        c = np.corrcoef(x, [s['stakes'] for _, s in groups[g]])[0, 1]
        res['matched']['groups'][g] = dict(mean=float(m), se=float(se), corr_within=float(c),
                                           level_range=[float(x.min()), float(x.max())])
        print(f'  {g:12s} residual {m:+.4f} ({se:.4f})  within-group corr(level, stakes) {c:+.2f}  level {x.min():.2f} to {x.max():.2f}')
    # the same without repetitive windows (4-gram repeat share above 5%)
    man_ids = np.fromfile(f'{a.scen}/scenario_ids.bin', dtype=np.int32).reshape(len(manifest), -1)
    res['matched']['low_repeat'] = {}
    for g in per:
        idx = [i for i in rows if manifest[i]['scenario'] == g and rep4(man_ids[i]) <= 0.05]
        x = np.array([rows[i]['level'].mean() for i in idx])
        v = np.array([rows[i]['stakes'].mean() for i in idx]) - A(x) @ coef
        m, se, _ = cluster_mean(v, [manifest[i]['prompt'] for i in idx])
        res['matched']['low_repeat'][g] = dict(n=len(idx), mean=float(m), se=float(se))
        print(f'  {g:12s} without windows above 5% repeated 4-grams: n {len(idx)}, residual {m:+.4f} ({se:.4f})')
    for g1, g2 in [('fiction', 'boring'), ('structured', 'boring'), ('fiction', 'structured')]:
        if g1 not in resid or g2 not in resid:
            continue
        x, y = resid[g1], resid[g2]
        d = x.mean() - y.mean()
        pool = np.concatenate([x, y])
        perm = np.array([(lambda q: q[:len(x)].mean() - q[len(x):].mean())(rng.permutation(pool)) for _ in range(10000)])
        p = float((np.abs(perm) >= abs(d)).mean())
        res['matched']['diffs'][f'{g1} - {g2}'] = dict(diff=float(d), p=p)
        print(f'  {g1} - {g2}: {d:+.4f} (p {p:.3f})')
    # repetition (share of positions 32-191 whose 4-gram occurred earlier in the window) and extreme windows
    dec = byte_decoder()
    print('\n  repetition and extreme windows (decoded from the window ids):')
    res['repetition'] = {}
    for g in per:
        idx = [i for i in rows if manifest[i]['scenario'] == g]
        rep = np.array([rep4(man_ids[i]) for i in idx])
        stk = np.array([rows[i]['stakes'].mean() for i in idx])
        lev = np.array([rows[i]['level'].mean() for i in idx])
        c = float(np.corrcoef(rep, stk)[0, 1])
        res['repetition'][g] = dict(mean=float(rep.mean()), max=float(rep.max()), corr_stakes=c)
        print(f'  {g}: 4-gram repeat share mean {rep.mean():.3f}, max {rep.max():.2f}; corr(repeat, stakes) {c:+.2f}')
        o = np.argsort(stk)
        res['repetition'][g]['extremes'] = []
        for j in list(o[:3]) + list(o[-3:]):
            i = idx[j]
            t = dec(man_ids[i][:manifest[i]['n_prompt'] + 24])
            res['repetition'][g]['extremes'].append(dict(window=int(i), stakes=float(stk[j]), level=float(lev[j]), text=t))
            print(f'    stakes {stk[j]:.3f} level {lev[j]:+.2f}  {t[:110]!r}')
    if a.json:
        json.dump(res, open(a.json, 'w'), indent=1)


if __name__ == '__main__':
    main()
