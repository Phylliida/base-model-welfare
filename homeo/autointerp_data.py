"""Data for scored auto-interpretation of the layer-sweep directions (plan B of the causal-interpretation plan).

For each selected direction (the top two per side at a spread of layers), from three disjoint thirds of the natural-text
capture's 1,200 FineWeb rollouts (score/sense; rollout % 3):
  0  explanation windows: 40-token windows around the most extreme and random positions, every token annotated with
     the direction's value (u.h / |h| in natural sd units, sign as exported: + is the family's pole);
  1  detection items (held out): pairs of contexts, one high and one low at the marked token (6 extreme pairs from the
     top / bottom 5%, 6 moderate pairs from 65-85% / 15-35%), in random order;
  2  steering (llama-server /steer, step input from the last prefix token, dose +-0.25 x mean |h|, 2 seeds x 40
     tokens, common random numbers): 6 prefixes as explanation evidence (unpushed / toward high / toward low) and 6
     held-out prefixes as intervention items (toward high vs toward low, random order; identical pairs dropped).
Also a baseline description per direction from the current labels (family, reading, effectors), scored by the same
judges. Writes OUT/data.json (no answers) and OUT/keys.json (answers). The /steer requests share the exposure log group
'autointerp-B' (one welfare_log.csv row per 100 requests).

usage: autointerp_data.py [--out /mnt/models/homeo/autointerp] [--url http://127.0.0.1:8056] [--layers 28,32,...]
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

import torch  # noqa: F401  (before numpy: this venv's numpy needs torch's libz)
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from value_probe import SAMPLE  # noqa: E402
from score_words import O, MODEL  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--out', default='/mnt/models/homeo/autointerp')
ap.add_argument('--url', default='http://127.0.0.1:8056')
ap.add_argument('--layers', default='28,32,36,40,42,44,46,50,54,58')
ap.add_argument('--ranks', type=int, default=2, help='directions per side and layer')
ap.add_argument('--dose', type=float, default=0.25)
ap.add_argument('--n-gen', type=int, default=40)
ap.add_argument('--fan-max', type=int, default=45, help='pause while the GPU fan is above this (%%)')
ap.add_argument('--seed', type=int, default=7)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
rng = np.random.default_rng(a.seed)

P = json.load(open(f'{O}/probe_dirs.json'))
D = P['n_embd']
U = np.fromfile(f'{O}/probe_dirs.f32', dtype=np.float32).reshape(len(P['names']), D).astype(np.float64)
BY = {d['name']: (i, d) for i, d in enumerate(P['directions'])}
layers = [int(x) for x in a.layers.split(',')]
sel = [d['name'] for d in P['directions'] if d['layer'] in layers and d['rank'] < a.ranks]
print(f'{len(sel)} directions: {" ".join(sel)}', flush=True)

# ---- natural-text capture ----
meta = json.load(open(f'{O}/sense/meta.json'))
K, F, n = meta['proj_k'], meta['n_extra'], meta['n_samples']
samp = np.fromfile(f'{O}/sense/samples.bin', dtype=SAMPLE)
LAB = np.dtype([('seq', '<i4'), ('pos', '<i4'), ('token', '<i4'), ('rank_prev', '<i4'), ('surprisal', '<f4'),
                ('entropy_prev', '<f4'), ('entropy', '<f4'), ('pad', '<f4')])
lab = np.fromfile(f'{O}/sense/labels.bin', dtype=LAB)
toks = {}
for sq in np.unique(lab['seq']):
    m = lab['seq'] == sq
    toks[int(sq)] = lab['token'][m][np.argsort(lab['pos'][m])]

sys.path.insert(0, '/home/bepis/prog/llm-tests/llama.cpp/gguf-py')
import gguf  # noqa: E402
rd = gguf.GGUFReader(MODEL)
fld = rd.fields['tokenizer.ggml.tokens']
vocab = [bytes(fld.parts[i]).decode('utf-8', 'replace') for i in fld.data]
bs = list(range(33, 127)) + list(range(0xA1, 0xAD)) + list(range(0xAE, 0x100))
cs, k_ = bs[:], 0
for b_ in range(256):
    if b_ not in bs:
        bs.append(b_); cs.append(256 + k_); k_ += 1
DEC = {chr(c): b_ for b_, c in zip(bs, cs)}
tb = lambda i: bytes(DEC.get(ch, 63) for ch in vocab[i]) if 0 <= i < len(vocab) else b''
text_of = lambda ts: b''.join(tb(int(t)) for t in ts).decode('utf-8', 'replace')
show = lambda s: s.replace('\n', '⏎')

third = samp['seq'] % 3
pos_index = {(int(q), int(p)): i for i, (q, p) in enumerate(zip(samp['seq'], samp['pos']))}


def window(cosz, i, before=31, after=8):
    """40 tokens around sample i, each annotated with its value in sd (blank where |z| < 0.5), the anchor in «»"""
    sq, ps = int(samp['seq'][i]), int(samp['pos'][i])
    out = []
    for p in range(max(32, ps - before), min(191, ps + after) + 1):
        j = pos_index.get((sq, p))
        piece = show(text_of([toks[sq][p]]))
        z = cosz[j] if j is not None else None
        tag = '' if z is None or abs(z) < 0.5 else '{%+.0f}' % z if abs(z) >= 1.5 else '{%+.1f}' % z
        out.append(('«' + piece + '»' if p == ps else piece) + tag)
    return ''.join(out)


def context(i, n_left=32):
    sq, ps = int(samp['seq'][i]), int(samp['pos'][i])
    return show(text_of(toks[sq][max(0, ps - n_left):ps])) + '«' + show(text_of([toks[sq][ps]])) + '»'


def fan():
    try:
        return int(subprocess.run(['nvidia-smi', '--query-gpu=fan.speed', '--format=csv,noheader,nounits'],
                                  capture_output=True, text=True, timeout=10).stdout.split()[0])
    except Exception:
        return 0


def steer(prefix, name, seed):
    while fan() > a.fan_max:
        time.sleep(5)
    body = {'tokens': [int(t) for t in prefix], 'dir': name, 'doses': [a.dose, -a.dose], 'n_seq': 2, 'n_gen': a.n_gen,
            'seed': seed, 'note': 'autointerp (B) evidence and intervention items', 'log_group': 'autointerp-B'}
    req = urllib.request.Request(a.url + '/steer', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    r = json.load(urllib.request.urlopen(req, timeout=900))
    time.sleep(0.3)
    return r


# steering prefixes: 12 rollouts from the third third, cut at a random point
steer_seqs = rng.choice(np.unique(samp['seq'][third == 2]), 12, replace=False)
prefixes = [toks[int(q)][:int(rng.integers(80, 151))] for q in steer_seqs]

data, keys = [], {}
t0 = time.time()
for nm in sel:
    idx, d = BY[nm]
    L = d['layer']
    pr = np.fromfile(f'{O}/sense/proj_L{L:02d}.f32', dtype=np.float32, count=n * (K + F + 1)).reshape(n, K + F + 1)
    B = np.fromfile(f'{O}/sweep.L{L}.capbasis.f32', dtype=np.float32, count=K * D).reshape(K, D).astype(np.float64)
    cos = pr[:, :K].astype(np.float64) @ (B @ U[idx]) / pr[:, -1].astype(np.float64)
    cosz = (cos - d['cos_stats']['mean']) / d['cos_stats']['sd']
    q = np.quantile(cos, [0.005, 0.05, 0.15, 0.35, 0.65, 0.85, 0.95, 0.995])

    # explanation windows: 4 highest (distinct rollouts), 4 lowest, 4 random, from third 0
    e_idx = np.flatnonzero(third == 0)
    order = e_idx[np.argsort(cos[e_idx])]
    pick = lambda cand: [i for k, i in enumerate(cand) if samp['seq'][i] not in {samp['seq'][j] for j in cand[:k]}][:4]
    hi, lo = pick(list(order[::-1][:400])), pick(list(order[:400]))
    rnd = list(rng.choice(e_idx, 4, replace=False))
    windows = [('high', window(cosz, i)) for i in hi] + [('low', window(cosz, i)) for i in lo] + [('random', window(cosz, i)) for i in rnd]

    # detection pairs from third 1
    d_idx = np.flatnonzero(third == 1)
    det, det_key = [], []
    for kind, (hl, hh), (ll, lh), n_pair in (('extreme', (q[6], np.inf), (-np.inf, q[1]), 6), ('moderate', (q[4], q[5]), (q[2], q[3]), 6)):
        hs = rng.choice(d_idx[(cos[d_idx] >= hl) & (cos[d_idx] < hh)], n_pair, replace=False)
        ls = rng.choice(d_idx[(cos[d_idx] >= ll) & (cos[d_idx] < lh)], n_pair, replace=False)
        for h_, l_ in zip(hs, ls):
            flip = bool(rng.integers(2))
            A, Bc = (context(l_), context(h_)) if flip else (context(h_), context(l_))
            det.append({'kind': kind, 'A': A, 'B': Bc})
            det_key.append('B' if flip else 'A')

    # steering: 6 evidence prefixes, 6 held-out intervention prefixes
    ev, itv, itv_key = [], [], []
    for k, pf in enumerate(prefixes):
        r = steer(pf, nm, seed=1000 + k)
        arms = r['arms']  # [unpushed, +dose (toward high), -dose (toward low)]
        tail = show(text_of(pf)[-240:])
        if k < 6:
            ev.append({'prefix_tail': tail, 'seeds': [{'unpushed': show(arms[0]['seqs'][s]['text']), 'toward_high': show(arms[1]['seqs'][s]['text']),
                                                      'toward_low': show(arms[2]['seqs'][s]['text'])} for s in range(2)]})
        else:
            for s in range(2):
                th, tl = show(arms[1]['seqs'][s]['text']), show(arms[2]['seqs'][s]['text'])
                if th == tl:
                    continue
                flip = bool(rng.integers(2))
                itv.append({'prefix_tail': tail, 'A': tl if flip else th, 'B': th if flip else tl})
                itv_key.append('B' if flip else 'A')

    # baseline description from the current labels
    more, less = ' '.join(d['more']) or '(none common)', ' '.join(d['less']) or '(none common)'
    base = {'label': d['family_label'], 'reads_high': (d['high'] + '. ' if d['high'] else '') + d['reading'],
            'reads_low': d['low'] or 'the opposite of high',
            'push_toward_high': f'writes more {more}; less {less}', 'push_toward_low': f'writes more {less}; less {more}'}
    data.append({'name': nm, 'layer': L, 'side': d['side'], 'rank': d['rank'], 'heldout': d['heldout'],
                 'windows': windows, 'steer_evidence': ev, 'detect': det, 'intervene': itv, 'baseline': base})
    keys[nm] = {'detect': det_key, 'detect_kind': [x['kind'] for x in det], 'intervene': itv_key}
    print(f'{nm}: {len(det)} detection pairs, {len(itv)} intervention pairs ({time.time() - t0:.0f} s)', flush=True)
    json.dump({'directions': data, 'dose': a.dose, 'n_gen': a.n_gen}, open(f'{a.out}/data.json', 'w'), ensure_ascii=False)
    json.dump(keys, open(f'{a.out}/keys.json', 'w'))
# write the pending exposure row of the log group
urllib.request.urlopen(urllib.request.Request(a.url + '/steer', data=json.dumps({'content': '.', 'dir': sel[0], 'doses': [], 'n_seq': 1, 'n_gen': 1,
                                              'log_group': 'autointerp-B', 'log_flush': True}).encode(), headers={'Content-Type': 'application/json'}), timeout=600)
print(f'-> {a.out}/data.json, keys.json ({time.time() - t0:.0f} s)')
