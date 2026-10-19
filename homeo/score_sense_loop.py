"""Sensor x effector test of the loop sign, per text feature (plan B2).

For each direction u that clears the noise (score_sensor.py output) and each running text feature f (sentence ends,
first/second-person pronouns and !, markup / structure tokens, function words, capitalised words inside a sentence):
  sensor   = corr(u.h / |h|, density of f in the context) on natural text (sense capture);
  effector = d E[count of f in the 32 written tokens] / dc along +u, from the sweep's unpushed samples by the score
             identity (count - per-prompt mean) x u.G, for a push of 0.25 x |h| at layer 40, SE clustered by prompt.
If +u is high where f is dense and a push along +u makes the model write more f, the loop amplifies; if it writes less
f, it pushes back (for sentence ends the reading is reversed: writing an end resets tokens-since-end). Where both the
sensor and the effector are clear, the prediction is compared with the measured side of kappa.
Writes SENSE/loop_test.json and prints a summary.
"""
import json
import os
import sys

import torch
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score_io import ScoreRun  # noqa: E402

O = '/mnt/models/homeo/score'
sens = json.load(open(f'{O}/sense/sensor.json'))
run = ScoreRun(f'{O}/sweep')
keep = np.flatnonzero(np.isin(run.prompt, run.whole_prompts()))
prompt = run.prompt[keep]
groups = [np.flatnonzero(prompt == q) for q in np.unique(prompt)]
tok = np.array(run.recs['tok'][keep])
D, K = run.D, 64

sys.path.insert(0, '/home/bepis/prog/llm-tests/llama.cpp/gguf-py')
import gguf  # noqa: E402
rd = gguf.GGUFReader('/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf')
fld = rd.fields['tokenizer.ggml.tokens']
vocab = [bytes(fld.parts[i]).decode('utf-8', 'replace') for i in fld.data]
bs = list(range(33, 127)) + list(range(0xA1, 0xAD)) + list(range(0xAE, 0x100))
cs, k_ = bs[:], 0
for b_ in range(256):
    if b_ not in bs:
        bs.append(b_); cs.append(256 + k_); k_ += 1
BYTE_DEC = {chr(c): b_ for b_, c in zip(bs, cs)}
pieces = [bytes(BYTE_DEC.get(ch, 63) for ch in v).decode('utf-8', 'replace') for v in vocab]
V = len(pieces)
PRON = {'i', 'you', 'we', 'me', 'my', 'your', 'our', 'us', "i'm", "'m", "'t", "'ve", "'ll", "n't", '!', 'yours', 'myself'}
FUNC = {'the', 'a', 'an', 'of', 'to', 'and', 'that', 'is', 'are', 'in', 'it', 'for', 'as', 'with', 'on', 'be', 'by',
        'this', 'was', 'or', 'which', 'from', 'at', 'have', 'has', 'not', 'but'}
cls = {k: np.zeros(V, bool) for k in ('end', 'markup', 'pron', 'func', 'cap')}
for i, p in enumerate(pieces):
    s = p.strip(); sl = s.lower().replace('’', "'")
    cls['end'][i] = s.endswith(('.', '!', '?', '。', '！', '？')) or '\n' in p
    cls['markup'][i] = '\n' in p or any(ch.isdigit() for ch in s) or (s != '' and all(not ch.isalnum() for ch in s) and s not in {',', '.', "'", '"', '’'})
    cls['pron'][i] = sl in PRON
    cls['func'][i] = sl in FUNC and p.startswith(' ')
    cls['cap'][i] = p.startswith(' ') and s[:1].isupper() and s[1:2].islower()
tc = np.clip(tok, 0, V - 1)
counts = {'end': cls['end'][tc].sum(1), 'markup': cls['markup'][tc].sum(1), 'pron': cls['pron'][tc].sum(1),
          'func': cls['func'][tc].sum(1), 'name': (cls['cap'][tc] & ~np.concatenate([np.ones((len(tc), 1), bool), cls['end'][tc][:, :-1]], 1)).sum(1)}
SENSOR = {'end': 'since_end', 'markup': 'markup16', 'pron': 'pron32', 'func': 'func16', 'name': 'name'}
cent = {}
for f, c in counts.items():
    x = c.astype(np.float64)
    for idx in groups:
        x[idx] -= x[idx].mean()
    cent[f] = x
push = 0.25 * 257.1

res, by_layer = [], {}
for r in sens['directions']:
    by_layer.setdefault(r['layer'], []).append(r)
for L, rows in sorted(by_layer.items()):
    G = run.G(L, keep).astype(np.float64)
    B = np.fromfile(f'{O}/sweep.L{L}.capbasis.f32', dtype=np.float32, count=K * D).reshape(K, D).astype(np.float64)
    for r in rows:
        u = np.fromfile(f'{O}/sweep.describe_cap64_dirs/L{L}_{r["side"]}_{r["rank"]}.f32', dtype=np.float32).astype(np.float64)
        s = G @ u
        rec = {'layer': L, 'side': r['side'], 'rank': r['rank'], 'heldout': r['heldout'], 'tests': {}}
        for f in counts:
            x = cent[f] * s
            pm = np.array([x[idx].mean() for idx in groups])
            eff, se = x.mean() * push, pm.std(ddof=1) / np.sqrt(len(groups)) * push
            sen = r['corr_cos'][SENSOR[f]]
            pred = None
            if abs(sen) >= 0.2 and abs(eff) >= 3 * se:
                same = (sen > 0) == (eff > 0)
                pred = ('pushback' if same else 'amplify') if f == 'end' else ('amplify' if same else 'pushback')
            rec['tests'][f] = {'sensor': sen, 'effector': float(eff), 'se': float(se), 'pred': pred}
        res.append(rec)
    print(f'layer {L} done', flush=True)
json.dump(res, open(f'{O}/sense/loop_test.json', 'w'))
for f in counts:
    t = [(r, r['tests'][f]) for r in res if r['tests'][f]['pred']]
    ok = sum(x['pred'] == r['side'] for r, x in t)
    print(f'{f:7s}: clear sensor and effector for {len(t):3d} directions; predicted side correct for {ok} '
          f'(push-back {sum(x["pred"] == r["side"] for r, x in t if r["side"] == "pushback")}/{sum(r["side"] == "pushback" for r, x in t)}, '
          f'amplified {sum(x["pred"] == r["side"] for r, x in t if r["side"] == "amplify")}/{sum(r["side"] == "amplify" for r, x in t)})')
