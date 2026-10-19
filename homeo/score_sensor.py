"""Sensor side at every layer (plan B2): what each layer's regulated directions track in ordinary text.

Reads the homeo-capture --proj run (runs/score/sense.sh): 192,000 positions of 1,200 FineWeb rollouts, with every
layer's block output projected on that layer's top-64 capacity basis and 14 fixed directions. Every direction found
by score_describe.py (sweep.describe_cap64) lies in that basis, so u.h = (B u).(B h).

For each direction that clears the noise (held-out kappa beyond +-0.03 on its own side, at a layer whose extreme
beats the shuffled null), with its sign as saved (the effector lists in sweep.describe_cap64.json are for +u):
  - correlations of u.h with text features of the context: tokens since the last sentence end, sentence end, newline,
    markup / structure density (last 16 tokens), first- and second-person pronoun density (last 32), function-word
    density (last 16), capitalised token inside a sentence (name-like), next-token entropy, surprisal, |h|;
  - mean u.h (in sd) by tokens since the last sentence end;
  - the contexts where u.h / |h| is highest and lowest.
Also, at every layer, the same correlations for the fixed directions (the screen's layer-40 directions and the probing
directions), to see whether they read the same features below the layers where the search resolves anything.
Writes DIR/sensor.txt and DIR/sensor.json.

usage: score_sensor.py [--dir /mnt/models/homeo/score/sense] [--sweep /mnt/models/homeo/score/sweep]
"""
import argparse
import json
import os
import sys

import torch
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from value_probe import SAMPLE  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--dir', default='/mnt/models/homeo/score/sense')
ap.add_argument('--sweep', default='/mnt/models/homeo/score/sweep')
ap.add_argument('--model', default='/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf')
ap.add_argument('--n-ctx', type=int, default=3, help='contexts shown per pole')
ap.add_argument('--limit', type=int, default=0, help='testing: use only the first N samples (whole rollouts)')
a = ap.parse_args()
torch.set_grad_enabled(False)

meta = json.load(open(f'{a.dir}/meta.json'))
D, K, F = meta['n_embd'], meta['proj_k'], meta['n_extra']
P = K + F
extra_names = json.load(open(f'{a.dir}/extra_names.json'))
samp = np.fromfile(f'{a.dir}/samples.bin', dtype=SAMPLE)
LAB = np.dtype([('seq', '<i4'), ('pos', '<i4'), ('token', '<i4'), ('rank_prev', '<i4'), ('surprisal', '<f4'),
                ('entropy_prev', '<f4'), ('entropy', '<f4'), ('pad', '<f4')])
lab = np.fromfile(f'{a.dir}/labels.bin', dtype=LAB)
if a.limit:
    samp = samp[:a.limit]
    lab = lab[lab['seq'] <= samp['seq'].max()]
n = len(samp)

# ---- vocabulary classes ----
sys.path.insert(0, '/home/bepis/prog/llm-tests/llama.cpp/gguf-py')
import gguf  # noqa: E402
rd = gguf.GGUFReader(a.model)
fld = rd.fields['tokenizer.ggml.tokens']
vocab = [bytes(fld.parts[i]).decode('utf-8', 'replace') for i in fld.data]
bs = list(range(33, 127)) + list(range(0xA1, 0xAD)) + list(range(0xAE, 0x100))
cs, k_ = bs[:], 0
for b_ in range(256):
    if b_ not in bs:
        bs.append(b_); cs.append(256 + k_); k_ += 1
BYTE_DEC = {chr(c): b_ for b_, c in zip(bs, cs)}
tok_bytes = lambda i: bytes(BYTE_DEC.get(ch, 63) for ch in vocab[i])
pieces = [tok_bytes(i).decode('utf-8', 'replace') for i in range(len(vocab))]
V = len(vocab)
PRON = {'i', 'you', 'we', 'me', 'my', 'your', 'our', 'us', "i'm", "'m", "'t", "'ve", "'ll", "n't", '!', 'yours', 'myself'}
FUNC = {'the', 'a', 'an', 'of', 'to', 'and', 'that', 'is', 'are', 'in', 'it', 'for', 'as', 'with', 'on', 'be', 'by',
        'this', 'was', 'or', 'which', 'from', 'at', 'have', 'has', 'not', 'but'}
cls = {k: np.zeros(V, bool) for k in ('end', 'nl', 'markup', 'pron', 'func', 'cap')}
for i, p in enumerate(pieces):
    s = p.strip()
    sl = s.lower().replace('’', "'")
    cls['end'][i] = s.endswith(('.', '!', '?', '。', '！', '？')) or '\n' in p
    cls['nl'][i] = '\n' in p
    cls['markup'][i] = '\n' in p or any(ch.isdigit() for ch in s) or (s != '' and all(not ch.isalnum() for ch in s) and s not in {',', '.', "'", '"', '’'})
    cls['pron'][i] = sl in PRON
    cls['func'][i] = sl in FUNC and p.startswith(' ')
    cls['cap'][i] = p.startswith(' ') and s[:1].isupper() and s[1:2].islower()

# ---- features per captured position (from each rollout's full token stream) ----
rollout_tok = {}
for sq in np.unique(lab['seq']):
    m = lab['seq'] == sq
    rollout_tok[int(sq)] = lab['token'][m][np.argsort(lab['pos'][m])]
feat = {k: np.zeros(n, np.float64) for k in ('since_end', 'at_end', 'newline', 'markup16', 'pron32', 'func16', 'name')}
order = np.lexsort((samp['pos'], samp['seq']))
for sq, t in rollout_tok.items():
    tc = np.clip(t, 0, V - 1)
    e, nl, mk, pr, fu, cp = (cls[k][tc].astype(np.float64) for k in ('end', 'nl', 'markup', 'pron', 'func', 'cap'))
    since = np.zeros(len(t))
    c = 0
    for i in range(len(t)):
        c = 0 if e[i] else c + 1
        since[i] = c
    cum = lambda x: np.concatenate([[0.0], np.cumsum(x)])
    cmk, cpr, cfu = cum(mk), cum(pr), cum(fu)
    idx = np.flatnonzero(samp['seq'] == sq)
    pos = samp['pos'][idx]
    feat['since_end'][idx] = np.minimum(since[pos], 40)
    feat['at_end'][idx] = e[pos]
    feat['newline'][idx] = nl[pos]
    feat['markup16'][idx] = (cmk[pos + 1] - cmk[np.maximum(pos - 15, 0)]) / 16
    feat['pron32'][idx] = (cpr[pos + 1] - cpr[np.maximum(pos - 31, 0)]) / 32
    feat['func16'][idx] = (cfu[pos + 1] - cfu[np.maximum(pos - 15, 0)]) / 16
    prev_end = np.concatenate([[1.0], e[:-1]])
    feat['name'][idx] = cp[pos] * (1 - prev_end[pos])
feat['entropy'] = samp['entropy'].astype(np.float64)
feat['surprisal'] = np.nan_to_num(samp['surprisal'].astype(np.float64))
FEATS = ['since_end', 'at_end', 'newline', 'markup16', 'pron32', 'func16', 'name', 'entropy', 'surprisal', 'norm']
FSHORT = {'since_end': 'since-end', 'at_end': 'at-end', 'newline': 'newline', 'markup16': 'markup', 'pron32': 'I/you/!',
          'func16': 'func-words', 'name': 'name', 'entropy': 'entropy', 'surprisal': 'surprisal', 'norm': '|h|'}
BINS = [0, 1, 2, 4, 8, 16, 41]


def zs(x):
    return (x - x.mean()) / (x.std() + 1e-30)


def text_of(t):
    return b''.join(tok_bytes(int(i)) for i in t if 0 <= i < V).decode('utf-8', 'replace')


def contexts(pj, top):
    out, seen = [], set()
    for i in (np.argsort(-pj) if top else np.argsort(pj))[:600]:
        sq, ps = int(samp['seq'][i]), int(samp['pos'][i])
        t = rollout_tok[sq]
        ctx = (text_of(t[max(0, ps - 14):ps]) + '[[' + text_of(t[ps:ps + 1]) + ']]').replace('\n', '⏎')
        key = ctx[-28:]
        if key in seen:
            continue
        seen.add(key)
        out.append(ctx[-64:])
        if len(out) == a.n_ctx:
            break
    return out


def describe(pj, Z, norm):
    zp = zs(pj)
    corr = {f: float(np.mean(zp * Z[f])) for f in FEATS[:-1]}
    corr['norm'] = float(np.mean(zp * zs(norm)))
    prof = [float(zp[(feat['since_end'] >= BINS[i]) & (feat['since_end'] < BINS[i + 1])].mean()) for i in range(len(BINS) - 1)]
    # the same with the scale of h removed (u.h / |h|), so a correlation is not just |h| varying
    zc = zs(pj / norm)
    corr_cos = {f: float(np.mean(zc * Z[f])) for f in FEATS[:-1]}
    return corr, prof, corr_cos


Z = {f: zs(feat[f]) for f in FEATS[:-1]}
dsc = json.load(open(f'{a.sweep}.describe_cap64.json'))
lines = []


def say(s=''):
    print(s, flush=True)
    lines.append(s)


say(f'sensor: {n} positions of {len(rollout_tok)} FineWeb rollouts; correlations of u.h with context features (u as saved: '
    f'the effector lists are for a push along +u)')
say('features: since-end = tokens since the last sentence end (capped 40); at-end / newline = current token; markup = '
    'share of the last 16 tokens with a newline, digit or symbol; I/you/! = share of the last 32 that are first/second-person '
    'pronouns, contractions or !; func-words = share of the last 16 that are function words; name = capitalised word inside a sentence')
out = {'directions': [], 'fixed': []}
for row in dsc['layers']:
    L = row['layer']
    pr = np.fromfile(f'{a.dir}/proj_L{L:02d}.f32', dtype=np.float32, count=n * (P + 1)).reshape(n, P + 1)
    norm = pr[:, -1].astype(np.float64)
    hb = pr[:, :K].astype(np.float64)
    for fi, nm in enumerate(extra_names):
        corr, prof, corr_cos = describe(pr[:, K + fi].astype(np.float64), Z, norm)
        out['fixed'].append({'layer': L, 'name': nm, 'corr': corr, 'profile': prof, 'corr_cos': corr_cos})
    zn = zs(norm)
    out.setdefault('norm', []).append({'layer': L, 'corr': {f: float(np.mean(zn * Z[f])) for f in FEATS[:-1]}})
    resolved = (row['kappa'][0] > row['null_top95']) or (row['kappa'][-1] < row['null_bottom5'])
    if not resolved:
        continue
    B = np.fromfile(f'{a.sweep}.L{L}.capbasis.f32', dtype=np.float32, count=K * D).reshape(K, D).astype(np.float64)
    for d in row['directions']:
        ho = (row['heldout_pushback'] if d['side'] == 'pushback' else row['heldout_amplify'])[d['rank']]
        if (d['side'] == 'pushback' and ho < 0.03) or (d['side'] == 'amplify' and ho > -0.03):
            continue
        u = np.fromfile(f'{a.sweep}.describe_cap64_dirs/L{L}_{d["side"]}_{d["rank"]}.f32', dtype=np.float32).astype(np.float64)
        v = B @ u
        pj = hb @ v
        corr, prof, corr_cos = describe(pj, Z, norm)
        top = sorted(corr.items(), key=lambda kv: -abs(kv[1]))
        rec = {'layer': L, 'side': d['side'], 'rank': d['rank'], 'kappa': d['kappa'], 'heldout': ho, 'in_basis': float(np.linalg.norm(v)),
               'corr': corr, 'corr_cos': corr_cos, 'profile': prof, 'high': contexts(pj / norm, True), 'low': contexts(pj / norm, False),
               'effector_more': d['more'][:6], 'effector_less': d['less'][:6], 'd_sentence_ends': d['d_sentence_ends']}
        out['directions'].append(rec)
        say()
        say(f'--- L{L} {d["side"]} {d["rank"]}: held-out kappa {ho:+.3f}; push +u writes more {" ".join(repr(t) for t in d["more"][:5])}, '
            f'less {" ".join(repr(t) for t in d["less"][:5])} (sentence ends {d["d_sentence_ends"]:+.2f})')
        say('    corr: ' + ', '.join(f'{FSHORT[f]} {c:+.2f}' for f, c in top[:6]))
        say('    with |h| divided out: ' + ', '.join(f'{FSHORT[f]} {corr_cos[f]:+.2f}' for f, _ in top[:6] if f != 'norm'))
        say('    by tokens since end 0/1/2-3/4-7/8-15/16+ (sd): ' + ' '.join(f'{p_:+.2f}' for p_ in prof))
        say('    highest: ' + '  ||  '.join(repr(c) for c in rec['high']))
        say('    lowest:  ' + '  ||  '.join(repr(c) for c in rec['low']))
    json.dump(out, open(f'{a.dir}/sensor.json', 'w'))

say()
say('fixed layer-40 directions read at every layer: corr with since-end / I-you-! / markup / func-words')
for nm in ('probe_pushback_0', 'screenL40_pushback_0', 'probe_amplify_0', 'screenL40_amplify_0', 'screenL40_amplify_1'):
    rows = [r for r in out['fixed'] if r['name'] == nm]
    say(f'  {nm}:')
    for r in rows:
        if r['layer'] % 4 == 0 or r['layer'] in (14, 18, 22, 26, 27, 42, 46, 58, 59, 60):
            c = r['corr']
            say(f'    L{r["layer"]:2d}: since-end {c["since_end"]:+.2f}  at-end {c["at_end"]:+.2f}  I/you/! {c["pron32"]:+.2f}  markup {c["markup16"]:+.2f}  '
                f'func {c["func16"]:+.2f}  |h| {c["norm"]:+.2f}')
open(f'{a.dir}/sensor.txt', 'w').write('\n'.join(lines) + '\n')
json.dump(out, open(f'{a.dir}/sensor.json', 'w'))
print(f'-> {a.dir}/sensor.txt')
