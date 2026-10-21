#!/usr/bin/env python3
"""Forecast change and TD error of the rollout probe on the test pairs (notes: "Rollout probe results").

Each site is a pair of consecutive positions (s, s+1). With f(t) the all-layer forecast of difficulty (mean surprisal of
the K tokens after the next one) at a fixed ridge strength:
  df     = f(s+1) - f(s), how much reading token s+1 moved the forecast
  TD     = -c_{s+1} - K df, with reward log p(token) and value -K f (the user's TD error)
Checks (test pairs only, predictions out of sample):
  size        sd of df against the sd of f
  surprise    corr(df, c_{s+1} - H_s): does a token more surprising than expected raise the forecast?
  direction   corr(df, y(s+1) - f(s)): does the forecast move toward what then happens (y = the realized difficulty)?
              Estimation noise of the probe alone gives a positive value (a noisy f(s) is partly undone at s+1:
              cov(df, -f(s)) contains var(noise) - cov(noise_s, noise_s+1) = var(noise in df) / 2); "corrected"
              removes that part using the measured reliability rho of df (noise share 1 - rho, from the fit's
              disjoint-half probes extrapolated to the full training set).
  examples    the tokens with the largest rises and falls of the forecast, with context (detokenized by the lens
              server on :8056, if it is up)
For the lambda-100 probe (rollprobe_l100_rows.npz) and the val-best probe (rollprobe_rows.npz) side by side.
Writes OUT/rollprobe_td.json and .txt.

usage: rollprobe_td.py [--out /mnt/models/homeo/rollprobe] [--meta /data2/homeo/rollprobe_acts/meta]
"""
import argparse
import json
import urllib.request

import torch  # noqa: F401  (before numpy on this box)
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('--out', default='/mnt/models/homeo/rollprobe')
ap.add_argument('--meta', default='/data2/homeo/rollprobe_acts/meta')
ap.add_argument('--server', default='http://127.0.0.1:8056')
ap.add_argument('--n-examples', type=int, default=12)
a = ap.parse_args()
lines = []
say = lambda s='': (print(s, flush=True), lines.append(s))


def corr(x, y):
    return float(np.corrcoef(x, y)[0, 1])


def detok(ids):
    try:
        req = urllib.request.Request(a.server + '/detokenize', data=json.dumps({'tokens': [int(t) for t in ids]}).encode(),
                                     headers={'Content-Type': 'application/json'})
        return json.load(urllib.request.urlopen(req, timeout=30))['content']
    except Exception:
        return None


probes = {'lambda 100': f'{a.out}/rollprobe_l100_rows.npz', 'val-best (lambda 10 / 31.6)': f'{a.out}/rollprobe_rows.npz'}
REL = json.load(open(f'{a.out}/rollprobe.json'))['reliability']['by_lambda']
RHO = {pn: {K: REL[lk][f'fit next {K} df']['rho_full_train'] for K in (32, 128)}
       for pn, lk in (('lambda 100', '100'), ('val-best (lambda 10 / 31.6)', '10'))}
Z = {k: np.load(v, allow_pickle=True) for k, v in probes.items()}
z0 = Z['lambda 100']
assert (z0['split'] == Z['val-best (lambda 10 / 31.6)']['split']).all()
names = list(z0['names'])
split, pair, kind, lg = z0['split'], z0['pair'], z0['kind'], z0['lang_group']
first = np.flatnonzero((split == 2) & (pair >= 0))
first = first[split[pair[first]] == 2]
sec = pair[first]
c1 = z0['next_1'][first]  # surprisal of token s+1
exc = c1 - z0['ent'][first]  # minus the entropy it was drawn against
say(f'{len(first)} test pairs ({(kind[first] == "rollout").sum()} rollout, {(kind[first] == "pretrain").sum()} natural)')
res = {}
for pn, z in Z.items():
    pred, Y = z['pred'], z['Y']
    res[pn] = {}
    for K in (32, 128):
        j = names.index(f'next {K}')
        f0, f1 = pred[first, j], pred[sec, j]
        df = f1 - f0
        td = -c1 - K * df
        y1 = Y[sec, j]
        e = y1 - f0
        mech = (1 - RHO[pn][K]) / 2 * df.var()
        r = {'rho_df': RHO[pn][K], 'corr_df_error_corrected': float((np.cov(df, e)[0, 1] - mech) / (df.std() * e.std())),'sd_f': float(pred[first, j].std()), 'sd_df': float(df.std()),
             'corr_df_excess_surprisal': corr(df, exc), 'corr_df_surprisal': corr(df, c1),
             'corr_df_error_of_previous_forecast': corr(df, y1 - f0),
             'sd_td': float(td.std()), 'td_share_from_df': float((K * df).var() / td.var())}
        for kd in ('rollout', 'pretrain'):
            m = kind[first] == kd
            r[f'{kd}: corr_df_excess_surprisal'] = corr(df[m], exc[m])
            r[f'{kd}: corr_df_error_of_previous_forecast'] = corr(df[m], (y1 - f0)[m])
        res[pn][f'next {K}'] = r
say()
say('forecast change df = f(s+1) - f(s) on the test pairs')
say(f'{"probe":28s} {"target":8s} {"sd f":>6s} {"sd df":>6s} {"rel df":>6s} {"r(df, surprise-H)":>18s} {"r(df, y - f_prev)":>18s} {"corrected":>10s} {"var share of K df in TD":>24s}')
for pn, rr in res.items():
    for t, r in rr.items():
        say(f'{pn:28s} {t:8s} {r["sd_f"]:6.3f} {r["sd_df"]:6.3f} {r["rho_df"]:6.2f} {r["corr_df_excess_surprisal"]:18.3f} '
            f'{r["corr_df_error_of_previous_forecast"]:18.3f} {r["corr_df_error_corrected"]:10.3f} {r["td_share_from_df"]:24.2f}')
say('  by kind (lambda 100, next 128): ' + ', '.join(f'{k}: {v:.3f}' for k, v in res['lambda 100']['next 128'].items() if ':' in k))

# examples: largest rises / falls of the lambda-100 next-128 forecast
j = names.index('next 128')
df = z0['pred'][sec, j] - z0['pred'][first, j]
seqs = {}
for k in np.unique(z0['chunk']):
    seqs[int(k)] = [json.loads(l) for l in open(f'{a.meta}/capture_c{int(k)}.jsonl', encoding='utf-8')]
ex = {}
for lab, order in (('rises (expects harder text)', np.argsort(-df)), ('falls (expects easier text)', np.argsort(df))):
    out = []
    for i in order[:a.n_examples]:
        r = first[i]
        sq = seqs[int(z0['chunk'][r])][int(z0['seq'][r])]
        toks = sq['prompt_ids'] + sq['tokens']
        d = int(z0['pos'][r])
        ctx, tok, after = detok(toks[max(0, d - 24):d + 1]), detok(toks[d + 1:d + 2]), detok(toks[d + 2:d + 14])
        out.append({'df': float(df[i]), 'kind': str(kind[r]), 'lang': str(z0['lang'][r]), 'pos': d + 1, 'context': ctx, 'token': tok, 'after': after})
    ex[lab] = out
    say()
    say(f'largest {lab}, lambda 100, next 128 (context | token read | what followed):')
    for e in out:
        if e['context'] is None:
            say(f'  df {e["df"]:+.3f} {e["kind"]} {e["lang"]} pos {e["pos"]} (lens server down: no text)')
        else:
            say(f'  df {e["df"]:+.3f} {e["kind"]:8s} {e["lang"]} pos {e["pos"]}: ...{e["context"][-80:]!r} | {e["token"]!r} | {e["after"]!r}')
json.dump({'n_pairs': int(len(first)), 'results': res, 'examples': ex}, open(f'{a.out}/rollprobe_td.json', 'w'), ensure_ascii=False, indent=1)
open(f'{a.out}/rollprobe_td.txt', 'w').write('\n'.join(lines) + '\n')
say(f'-> {a.out}/rollprobe_td.json')
