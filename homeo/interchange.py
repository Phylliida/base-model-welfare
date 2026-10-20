"""Interchange interventions on the headline variables (plan C of the causal-interpretation plan).

The claim "direction u is the model's variable X" predicts more than a correlation: give a token the value u takes in
contexts where X differs, and the model's next-token behavior should move the way X predicts. For each hypothesis:
  target sites: natural tokens where X is low (e.g. 1-3 tokens into a sentence), source sites: where X is high (16+);
  c_src, c_tgt: the mean of u.h / |h| over all such positions of the natural-text capture (natural values, so the
           intervened state stays in distribution along u);
  set: at a target site, set u.h / |h| to c_src at that token only (llama-server /steer set mode, an impulse); at a
       source site, set it to c_tgt (the reverse);
  behavior: log P(next token in a class X predicts), e.g. sentence-ending tokens for sentence position;
  natural gap: mean log P(class) at source sites minus at target sites, unpushed.
Reported: the mean change at target and source sites, and the fraction of the natural gap it closes (an impulse only
reaches the next-token prediction at that token; see the impulse-vs-step check). Controls at layer 42: random unit
directions in that layer's capacity basis pushed by the same amount, and each hypothesis' sites under the other two
families' directions (a direction x behavior matrix; specificity means a dominant diagonal).
Sites come from the capture's 1,200 FineWeb rollouts, one per rollout. /steer requests share the exposure log group
'interchange-C'. Writes OUT/interchange.json and OUT/interchange.txt.

usage: interchange.py [--out /mnt/models/homeo/autointerp] [--url http://127.0.0.1:8056] [--n-site 60]
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
from score_words import O, vocab_classes, context_features  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--out', default='/mnt/models/homeo/autointerp')
ap.add_argument('--url', default='http://127.0.0.1:8056')
ap.add_argument('--n-site', type=int, default=60)
ap.add_argument('--n-random', type=int, default=3)
ap.add_argument('--fan-max', type=int, default=45)
ap.add_argument('--seed', type=int, default=5)
ap.add_argument('--dry', action='store_true', help='site counts and source/target values only, no server calls')
a = ap.parse_args()
rng = np.random.default_rng(a.seed)

HYP = [
    {'key': 'sentence', 'name': 'sentence position', 'feature': 'since_end', 'target': (1, 3), 'source': (16, 40), 'cls': 'end',
     'dirs': ['L36.pushback.0', 'L40.pushback.0', 'L42.pushback.0', 'L46.pushback.0'],
     'what': 'target: 1-3 tokens into a sentence; source: 16+ tokens in; behavior: log P(next token ends a sentence or line)'},
    {'key': 'chatty', 'name': 'chatty vs institutional', 'feature': 'pron32', 'target': (0, 0), 'source': (0.125, 1), 'cls': 'pron',
     'dirs': ['L36.amplify.0', 'L40.amplify.0', 'L42.amplify.1', 'L48.amplify.1'],
     'what': 'target: no I/you/! in the last 32 tokens; source: 4+ of them; behavior: log P(next token is I/you/!/a contraction)'},
    {'key': 'struct', 'name': 'prose vs structured', 'feature': 'markup16', 'target': (0, 0.0625), 'source': (0.5, 1), 'cls': 'markup',
     'dirs': ['L40.amplify.1', 'L42.amplify.0', 'L46.amplify.0', 'L52.amplify.0'],
     'what': 'target: at most 1 of the last 16 tokens is markup; source: 8+; behavior: log P(next token is a newline, digit or symbol)'},
]
CROSS_LAYER = 42

P = json.load(open(f'{O}/probe_dirs.json'))
D = P['n_embd']
U = np.fromfile(f'{O}/probe_dirs.f32', dtype=np.float32).reshape(len(P['names']), D).astype(np.float64)
BY = {d['name']: (i, d) for i, d in enumerate(P['directions'])}
pieces, cls = vocab_classes()
CLS_IDS = {k: np.flatnonzero(cls[k]).tolist() for k in ('end', 'pron', 'markup')}

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
feat = {k: np.zeros(n) for k in ('since_end', 'pron32', 'markup16')}
for sq, t in toks.items():
    f = context_features(t, cls)
    idx = np.flatnonzero(samp['seq'] == sq)
    for k in feat:
        feat[k][idx] = f[k][samp['pos'][idx]]


def cos_of(name):
    i, d = BY[name]
    L = d['layer']
    pr = np.fromfile(f'{O}/sense/proj_L{L:02d}.f32', dtype=np.float32, count=n * (K + F + 1)).reshape(n, K + F + 1)
    B = np.fromfile(f'{O}/sweep.L{L}.capbasis.f32', dtype=np.float32, count=K * D).reshape(K, D).astype(np.float64)
    return pr[:, :K].astype(np.float64) @ (B @ U[i]) / pr[:, -1].astype(np.float64)


def fan():
    try:
        return int(subprocess.run(['nvidia-smi', '--query-gpu=fan.speed', '--format=csv,noheader,nounits'],
                                  capture_output=True, text=True, timeout=10).stdout.split()[0])
    except Exception:
        return 0


def steer(body):
    while fan() > a.fan_max:
        time.sleep(5)
    body = dict(body, mode='impulse', n_seq=1, n_gen=1, classes=CLS_IDS, log_group='interchange-C',
                note='interchange interventions (C): set u.h/|h| at one token to a natural value')
    req = urllib.request.Request(a.url + '/steer', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    try:
        return json.load(urllib.request.urlopen(req, timeout=600))
    except urllib.error.HTTPError as e:
        # e.g. a site whose |h| is so large that the set value needs a push beyond --steer-max-dose: skipped, counted
        SKIPS.append(json.load(e).get('error', {}).get('message', str(e)))
        return None


SKIPS = []


def sites(h, which):
    lo, hi = h[which]
    m = (feat[h['feature']] >= lo) & (feat[h['feature']] <= hi)
    if h['key'] == 'sentence':
        m &= ~cls['end'][np.clip(samp['token'], 0, len(pieces) - 1)]  # not at an end token
    idx = np.flatnonzero(m)
    out, seen = [], set()
    for i in rng.permutation(idx):
        if int(samp['seq'][i]) in seen:
            continue
        seen.add(int(samp['seq'][i]))
        out.append(int(i))
        if len(out) == a.n_site:
            break
    return out, m


def prefix(i):
    return [int(t) for t in toks[int(samp['seq'][i])][:int(samp['pos'][i]) + 1]]


def run_set(name, site_idx, target_cos, cls_key):
    """set u.h/|h| at each site to target_cos; returns (unpushed log P, pushed log P, push) per site"""
    out = []
    for i in site_idx:
        r = steer({'tokens': prefix(i), 'dir': name, 'set_cos': float(target_cos)})
        if r is None:
            out.append((np.nan, np.nan, np.nan))
            continue
        out.append((r['arms'][0]['class_logp'][cls_key][0], r['arms'][1]['class_logp'][cls_key][0], r['arms'][1]['push']))
    return np.array(out)


def run_vec(vec, layer, site_idx, pushes, cls_key):
    out = []
    for i, pu in zip(site_idx, pushes):
        hn = P['per_layer'][[r['layer'] for r in P['per_layer']].index(layer)]['h_norm']
        r = steer({'tokens': prefix(i), 'dir': '', 'vector': vec.tolist(), 'layer': layer, 'doses': [float(pu / hn)]}) if np.isfinite(pu) else None
        if r is None:
            out.append((np.nan, np.nan, np.nan))
            continue
        out.append((r['arms'][0]['class_logp'][cls_key][0], r['arms'][1]['class_logp'][cls_key][0], pu))
    return np.array(out)


def ms(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(x.mean()), float(x.std(ddof=1) / np.sqrt(len(x)))


res, lines = {'hypotheses': []}, []
say = lambda s='': (print(s, flush=True), lines.append(s))
t0 = time.time()
say('Interchange interventions: set a direction at one token to the natural value it has where the variable differs, '
    'and measure the next-token behavior the variable predicts. Fractions are of the natural gap in log P(class).')
if a.dry:
    for h in HYP:
        (tgt, mt), (src, msrc) = sites(h, 'target'), sites(h, 'source')
        print(f'{h["name"]}: {mt.sum()} target / {msrc.sum()} source positions, {len(tgt)} / {len(src)} sites')
        for name in h['dirs']:
            c = cos_of(name)
            sd = BY[name][1]['cos_stats']['sd']
            print(f'  {name}: c_tgt {c[mt].mean():+.3f}, c_src {c[msrc].mean():+.3f}, gap {(c[msrc].mean() - c[mt].mean()) / sd:+.2f} sd')
    sys.exit(0)
for h in HYP:
    tgt, mt = sites(h, 'target')
    src, msrc = sites(h, 'source')
    hr = {'key': h['key'], 'name': h['name'], 'what': h['what'], 'n_target': len(tgt), 'n_source': len(src), 'dirs': {}}
    say()
    say(f'== {h["name"]}: {h["what"]} ({len(tgt)} target, {len(src)} source sites)')
    gap = None
    for name in h['dirs']:
        c = cos_of(name)
        c_src, c_tgt = float(c[msrc].mean()), float(c[mt].mean())
        A = run_set(name, tgt, c_src, h['cls'])   # target -> source value
        Bk = run_set(name, src, c_tgt, h['cls'])  # source -> target value
        nat = float(np.nanmean(Bk[:, 0]) - np.nanmean(A[:, 0]))
        gap = nat if gap is None else gap
        dA, dB = ms(A[:, 1] - A[:, 0]), ms(Bk[:, 1] - Bk[:, 0])
        hr['dirs'][name] = {'c_src': c_src, 'c_tgt': c_tgt, 'c_sd': BY[name][1]['cos_stats']['sd'], 'natural_gap': nat,
                            'target_to_source': dA, 'source_to_target': dB, 'frac_t2s': dA[0] / nat, 'frac_s2t': -dB[0] / nat,
                            'mean_abs_push': float(np.nanmean(np.abs(A[:, 2]))), 'skipped': int(np.isnan(A[:, 0]).sum() + np.isnan(Bk[:, 0]).sum()),
                            'sites_target': A.tolist(), 'sites_source': Bk.tolist()}
        say(f'  {name:16s} source-target value gap {(c_src - c_tgt) / BY[name][1]["cos_stats"]["sd"]:+.2f} sd; natural gap {nat:+.2f}; '
            f'target set to source value {dA[0]:+.3f} +- {dA[1]:.3f} ({dA[0] / nat:+.0%} of the gap); '
            f'source set to target value {dB[0]:+.3f} +- {dB[1]:.3f} ({-dB[0] / nat:+.0%}); {hr["dirs"][name]["skipped"]} sites skipped ({time.time() - t0:.0f} s)')
        if BY[name][1]['layer'] == CROSS_LAYER:
            hr['cross_push'] = A[:, 2].tolist()
    res['hypotheses'].append(hr)
    hr['tgt_sites'], hr['src_sites'] = tgt, src
    json.dump(res, open(f'{a.out}/interchange.json', 'w'), indent=1)

# ---- controls at layer 42: random directions (same push sizes) and the other families' directions ----
say()
say(f'== controls at layer {CROSS_LAYER}')
Bl = np.fromfile(f'{O}/sweep.L{CROSS_LAYER}.capbasis.f32', dtype=np.float32, count=K * D).reshape(K, D).astype(np.float64)
rand_vecs = [Bl.T @ (z / np.linalg.norm(z)) for z in rng.standard_normal((a.n_random, K))]
l42 = {h['key']: [d for d in h['dirs'] if BY[d][1]['layer'] == CROSS_LAYER][0] for h in HYP}
res['cross'] = {}
for h, hr in zip(HYP, res['hypotheses']):
    tgt = hr['tgt_sites']
    m_src = sites(h, 'source')[1]
    m_tgt = sites(h, 'target')[1]
    row = {}
    for fam, name in l42.items():
        if fam == h['key']:
            row[fam] = hr['dirs'][name]['target_to_source']
            continue
        c = cos_of(name)
        A = run_set(name, tgt, float(c[m_src].mean()), h['cls'])
        row[fam] = ms(A[:, 1] - A[:, 0])
    rnd = []
    pushes = np.array(hr['cross_push'])
    for v in rand_vecs:
        A = run_vec(v, CROSS_LAYER, tgt, pushes, h['cls'])
        rnd.append(A[:, 1] - A[:, 0])
    rnd = np.concatenate(rnd)
    row['random'] = ms(rnd)
    row['random_abs'] = ms(np.abs(rnd))
    res['cross'][h['key']] = row
    say(f'  {h["name"]} sites, behavior {h["cls"]}: ' + ', '.join(f'{k} direction {v[0]:+.3f} +- {v[1]:.3f}' for k, v in row.items() if k in l42) +
        f'; random directions (same push) {row["random"][0]:+.3f} +- {row["random"][1]:.3f}, mean |change| {row["random_abs"][0]:.3f} ({time.time() - t0:.0f} s)')

# write the pending exposure row
urllib.request.urlopen(urllib.request.Request(a.url + '/steer', data=json.dumps({'content': '.', 'dir': HYP[0]['dirs'][0], 'doses': [], 'n_seq': 1,
                       'n_gen': 1, 'log_group': 'interchange-C', 'log_flush': True}).encode(), headers={'Content-Type': 'application/json'}), timeout=600)
os.makedirs(a.out, exist_ok=True)
res['skips'] = SKIPS
json.dump(res, open(f'{a.out}/interchange.json', 'w'), indent=1)
open(f'{a.out}/interchange.txt', 'w').write('\n'.join(lines) + '\n')
say(f'-> {a.out}/interchange.json ({time.time() - t0:.0f} s)')
