#!/usr/bin/env python3
"""Value lens analysis (the Value Lens proposal; homeo-value output).

1. Prices of existing steering vectors at their layers: now (k = 0), short (k = 1..8) and fut (k = 1..32)
   log-likelihood change per unit push, against random unit directions at the same layer.
2. Price structure (H1): how much of the price variance the leading directions carry, whether they replicate
   across halves of the windows, and whether future prices are just rescaled now prices.
3. Contexts (protocol A5, candidate good states first): per window, level (mean log-likelihood), stakes
   (mean size of the future price vector) and progress (how fast log-likelihood improves along the window),
   with decoded text for the top and bottom windows.

With --clean, only positions whose 32-token horizon contains no blank-line token are used. fineweb_ids.bin
joins documents with blank lines, so this drops horizons that cross into the next document (and some
paragraph breaks inside documents, which is conservative).

usage: value_lens.py /mnt/models/homeo/value [--max-windows N] [--json out.json] [--examples 4] [--clean]
"""
import argparse
import glob
import json
import os
import sys

import torch  # noqa: F401  (import before numpy on this box)
import numpy as np

H = '/mnt/models/homeo'
MODEL = '/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf'
RESID = {40: 261.1, 44: 364.0, 50: 565.4, 56: 866.8}  # mean residual norm (S2(c) sweep)
LIBRARY = [  # name, file, layer
    ('contrastive "weird token" (S2)', f'{H}/s2/vec_caa_L44.f32', 44),
    ('surprise probe direction (S2)', f'{H}/s2/vec_probe_s_L44.f32', 44),
    ('temperature 1.3, optimized (S2(c))', f'{H}/s2opt/vec_temp1.3_opt2_L40.f32', 40),
    ('band p~0.5, optimized', f'{H}/s2opt/vec_p0.5_opt2_L40.f32', 40),
    ('band p~0.25, optimized', f'{H}/s2opt/vec_p0.25_opt2_L40.f32', 40),
    ('band p~0.1, optimized', f'{H}/s2opt/vec_p0.1_opt2_L40.f32', 40),
    ('band p~0.03, optimized', f'{H}/s2opt/vec_p0.03_opt2_L40.f32', 40),
    ('temperature 1.3, sweep (L50)', f'{H}/s2sweep/temp1.3_L50.f32', 50),
    ('plausible-tail (p~0.03 sweep, L56)', f'{H}/s2sweep/p0.03_r1_L56.f32', 56),
]
KINDS = ['now', 'short', 'fut']
N_RANDOM = 32


def unit(v):
    return v / np.linalg.norm(v)


def vocab_decoder():
    """GLM-4 vocab from the GGUF (cached), decoded as byte-level BPE."""
    cache = f'{H}/value/vocab.json'
    if os.path.exists(cache):
        toks = json.load(open(cache))
    else:
        sys.path.insert(0, '/home/bepis/prog/llm-tests/llama.cpp/gguf-py')
        from gguf import GGUFReader
        r = GGUFReader(MODEL)
        f = r.fields['tokenizer.ggml.tokens']
        toks = [bytes(f.parts[i]).decode('utf-8', errors='replace') for i in f.data]
        json.dump(toks, open(cache, 'w'))
    bs = list(range(ord('!'), ord('~') + 1)) + list(range(ord('\xa1'), ord('\xac') + 1)) + list(range(ord('\xae'), ord('\xff') + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b); cs.append(256 + n); n += 1
    u2b = {chr(c): b for b, c in zip(bs, cs)}

    def decode(ids):
        out = bytearray()
        for i in ids:
            t = toks[i] if 0 <= i < len(toks) else ''
            for ch in t:
                if ch in u2b:
                    out.append(u2b[ch])
                else:
                    out.extend(ch.encode('utf-8'))
        return out.decode('utf-8', errors='replace')
    return decode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dir')
    ap.add_argument('--max-windows', type=int, default=0)
    ap.add_argument('--json', default='')
    ap.add_argument('--examples', type=int, default=4)
    ap.add_argument('--clean', action='store_true', help='drop positions whose horizon contains a blank-line token')
    a = ap.parse_args()

    meta = json.load(open(f'{a.dir}/meta.json'))
    layers, d = meta['layers'], meta['n_embd']
    s_lo, s_hi = meta['positions']
    P = s_hi - s_lo + 1
    files = sorted(glob.glob(f'{a.dir}/w*.json'))
    files = [f for f in files if os.path.exists(f[:-5] + '.bin')]
    if a.max_windows:
        files = files[:a.max_windows]
    W = len(files)
    print(f'{a.dir}: {W} windows x {P} positions, layers {layers}, horizon {meta["horizon"]}, short {meta["short"]}')

    boundary = set()
    if a.clean:
        vocab_decoder()  # make sure the vocab cache exists
        toks = json.load(open(f'{H}/value/vocab.json'))
        boundary = {i for i, t in enumerate(toks) if '\u010a\u010a' in t}  # byte-level BPE spelling of "\n\n"
        print(f'  --clean: {len(boundary)} blank-line tokens; positions whose horizon contains one are dropped')
    K = meta['horizon']

    lib = [(name, unit(np.fromfile(p, dtype=np.float32)), L) for name, p, L in LIBRARY if L in layers and os.path.exists(p)]
    rng = np.random.default_rng(0)
    rand = {L: np.stack([unit(rng.standard_normal(d).astype(np.float32)) for _ in range(N_RANDOM)]) for L in layers}

    price = {name: {k: [] for k in KINDS} for name, _, _ in lib}
    rprice = {L: {k: [] for k in KINDS} for L in layers}
    norms = {L: {k: [] for k in KINDS} for L in layers}
    cos_now_fut = []
    li40 = layers.index(40) if 40 in layers else 0
    C = {(half, k): np.zeros((d, d)) for half in (0, 1) for k in (0, 2)}
    ctx = []
    masks = []
    for wi, f in enumerate(files):
        j = json.load(open(f))
        arr = np.fromfile(f[:-5] + '.bin', dtype=np.float16).astype(np.float32).reshape(len(layers), 3, P, d)
        tk = j['tokens']
        m = np.array([not any(t in boundary for t in tk[s + 1:s + K + 2]) for s in range(s_lo, s_hi + 1)])
        masks.append(m)
        for name, v, L in lib:
            for ki, k in enumerate(KINDS):
                price[name][k].append(arr[layers.index(L), ki] @ v)
        for li, L in enumerate(layers):
            for ki, k in enumerate(KINDS):
                rprice[L][k].append(arr[li, ki] @ rand[L].T)
                norms[L][k].append(np.linalg.norm(arr[li, ki], axis=1))
        gn, gf = arr[li40, 0], arr[li40, 2]
        cos_now_fut.append(((gn * gf).sum(1) / (np.linalg.norm(gn, axis=1) * np.linalg.norm(gf, axis=1) + 1e-12))[m])
        for ki in (0, 2):
            G = arr[li40, ki][m].astype(np.float64)
            C[(wi % 2, ki)] += G.T @ G
        ll = np.array(j['ll'])[s_lo:s_hi + 1]
        ent = np.array(j['entropy'])[s_lo:s_hi + 1]
        surpr = -np.array(j['ll'])[s_lo - 1:s_hi]  # surprisal of the token at each position
        x = np.arange(len(ll))
        if m.sum() >= 20:
            ctx.append(dict(window=j['window'], tokens=j['tokens'], ll=ll, ent=ent, surpr=surpr,
                            level=float(ll[m].mean()), progress=float(np.polyfit(x[m], ll[m], 1)[0] * len(ll)),
                            stakes=float(norms[layers[li40]]['fut'][-1][m].mean())))
    for name in price:
        for k in KINDS:
            price[name][k] = np.stack(price[name][k])  # [W, P]
    for L in layers:
        for k in KINDS:
            rprice[L][k] = np.stack(rprice[L][k])  # [W, P, R]
            norms[L][k] = np.stack(norms[L][k])
    M = np.stack(masks)  # [W, P] positions used
    ent_all = np.stack([np.array(json.load(open(f))['entropy'])[s_lo:s_hi + 1] for f in files])
    surpr_all = np.stack([-np.array(json.load(open(f))['ll'])[s_lo - 1:s_hi] for f in files])
    good_w = M.sum(1) >= 10
    out = {'windows': W, 'positions': int(M.sum()), 'clean': bool(a.clean)}
    print(f'  positions used: {int(M.sum())} of {W * P}')

    # ---- 1. library prices ----
    print('\n== 1. Prices of existing vectors (per unit push; "x0.1" = per push of 0.1 x the residual norm)')
    print('   kind  mean x0.1 (nats)  t (windows)  sd ratio vs random  frac > 0  corr(price, entropy)  corr(price, surprisal)')
    out['library'] = {}
    for name, v, L in lib:
        print(f'  {name} [L{L}]')
        out['library'][name] = {'layer': L}
        for k in KINDS:
            xw = price[name][k]
            x = xw[M]
            wmean = np.array([xw[i][M[i]].mean() for i in range(W) if good_w[i]])
            t = wmean.mean() / (wmean.std(ddof=1) / np.sqrt(len(wmean))) if len(wmean) > 1 else float('nan')
            rsd = rprice[L][k][M].std(axis=0).mean()
            sd_ratio = x.std() / rsd
            c_ent = np.corrcoef(x, ent_all[M])[0, 1]
            c_sur = np.corrcoef(x, surpr_all[M])[0, 1]
            m01 = x.mean() * 0.1 * RESID[L]
            print(f'   {k:5s}  {m01:+.4f}          {t:+6.2f}       {sd_ratio:6.2f}            {(x > 0).mean():.2f}      {c_ent:+.3f}                {c_sur:+.3f}')
            out['library'][name][k] = dict(mean_per_0p1=float(m01), t=float(t), sd_ratio_vs_random=float(sd_ratio),
                                           frac_pos=float((x > 0).mean()), corr_entropy=float(c_ent), corr_surprisal=float(c_sur))
        cnf = np.corrcoef(price[name]['now'][M], price[name]['fut'][M])[0, 1]
        print(f'   corr(now, fut) {cnf:+.3f}')
        out['library'][name]['corr_now_fut'] = float(cnf)
    print('  random directions (same layers): |mean| x0.1, typical:')
    for L in layers:
        rm = np.abs(rprice[L]['fut'][M].mean(axis=0)) * 0.1 * RESID[L]
        print(f'   L{L}: fut |mean| median {np.median(rm):.4f}, max {rm.max():.4f}')

    # ---- 2. structure ----
    print('\n== 2. Price structure at L%d' % layers[li40])
    cnf = np.concatenate(cos_now_fut)
    print(f'  per-position cosine(g_now, g_fut): median {np.median(cnf):+.3f}, IQR {np.percentile(cnf, 25):+.3f} to {np.percentile(cnf, 75):+.3f}')
    out['structure'] = {'cos_now_fut_median': float(np.median(cnf))}
    tops = {}
    for ki, k in ((0, 'now'), (2, 'fut')):
        evs = []
        for half in (0, 1):
            w_, V_ = np.linalg.eigh(C[(half, ki)])
            evs.append((w_[::-1], V_[:, ::-1]))
        share = [float(evs[0][0][:n].sum() / evs[0][0].sum()) for n in (1, 10, 100)]
        ov = {n: float(np.sum((evs[0][1][:, :n].T @ evs[1][1][:, :n]) ** 2) / n) for n in (1, 10, 50)}
        print(f'  {k}: variance share of top 1 / 10 / 100 directions {share[0]:.3f} / {share[1]:.3f} / {share[2]:.3f};'
              f' split-half subspace overlap top 1 / 10 / 50: {ov[1]:.3f} / {ov[10]:.3f} / {ov[50]:.3f} (random ~ n/{d})')
        tops[k] = evs[0][1][:, :10]
        out['structure'][k] = dict(share_top=share, split_half_overlap=ov)
    o = float(np.sum((tops['now'].T @ tops['fut']) ** 2) / 10)
    print(f'  overlap of the top-10 now and top-10 fut subspaces: {o:.3f}')
    out['structure']['now_fut_top10_overlap'] = o
    for name, v, L in lib:
        if L == layers[li40]:
            print(f'  {name}: share of its unit norm in the top-10 fut directions {float(np.sum((tops["fut"].T @ v) ** 2)):.3f}')

    # ---- 3. contexts ----
    lev = np.array([c['level'] for c in ctx]); stk = np.array([c['stakes'] for c in ctx]); prg = np.array([c['progress'] for c in ctx])
    print('\n== 3. Contexts (per window: level = mean log-likelihood, stakes = mean |g_fut| at L%d, progress = log-likelihood gain along the window)' % layers[li40])
    print(f'  corr(level, stakes) {np.corrcoef(lev, stk)[0, 1]:+.3f}   corr(level, progress) {np.corrcoef(lev, prg)[0, 1]:+.3f}   corr(stakes, progress) {np.corrcoef(stk, prg)[0, 1]:+.3f}')
    out['contexts'] = dict(corr_level_stakes=float(np.corrcoef(lev, stk)[0, 1]), corr_level_progress=float(np.corrcoef(lev, prg)[0, 1]),
                           corr_stakes_progress=float(np.corrcoef(stk, prg)[0, 1]))
    if a.examples:
        decode = vocab_decoder()
        for label, key, order in (('highest stakes', stk, -1), ('lowest stakes', stk, 1), ('highest progress', prg, -1), ('lowest level (hardest)', lev, 1), ('highest level (easiest)', lev, -1)):
            idx = np.argsort(order * key)[:a.examples]
            print(f'\n  -- {label}')
            for i in idx:
                c = ctx[i]
                txt = decode(c['tokens'][s_lo:s_hi + 1]).replace('\n', ' / ')
                print(f'   [w{c["window"]} level {c["level"]:.2f} stakes {c["stakes"]:.3f} progress {c["progress"]:+.2f}] {txt[:220]!r}')
    if a.json:
        json.dump(out, open(a.json, 'w'), indent=1)


if __name__ == '__main__':
    main()
