"""Per-layer prose for the layer-sweep writeup ("What a base model regulates, layer by layer", tab "Layer by layer").

Reads the sweep analysis (sweep.describe_cap64.json, sweep.sweep.json), the natural-text capture analysis
(sense/sensor.json, sense/families.json from score_sensor.py and score_sense_families.py) and writes, to --out:
  sections.md  one "## Layer N" section per layer: held-out kappa against the noise edge, then per direction what it
               tracks in ordinary text (its family comes from that reading), what the model writes when pushed
               along it, and the layer-40 directions read and pushed at that layer;
  table.md     the overview table (one row per layer).

usage: score_layer_sections.py [--out DIR]
"""
import argparse
import json
import os
import sys

import torch
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score_io import ScoreRun  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--out', default='.')
a = ap.parse_args()
O = '/mnt/models/homeo/score'
D = json.load(open(f'{O}/sweep.describe_cap64.json'))
SW = {r['layer']: r for r in json.load(open(f'{O}/sweep.sweep.json'))['layers']}
S = json.load(open(f'{O}/sense/sensor.json'))
SENS = {(r['layer'], r['side'], r['rank']): r for r in S['directions']}
FIX = {(r['layer'], r['name']): r for r in S['fixed']}
FAM = {tuple(k.split('_')[:1]) + (k.split('_')[1], int(k.split('_')[2])): v for k, v in json.load(open(f'{O}/sense/families.json')).items()}
FAM = {(int(k[0]), k[1], k[2]): v for k, v in FAM.items()}

# tokens written in >= 25% of the sweep prompts (rarer ones are prompt-specific topic words)
sys.path.insert(0, '/home/bepis/prog/llm-tests/llama.cpp/gguf-py')
import gguf  # noqa: E402
run = ScoreRun(f'{O}/sweep')
rd = gguf.GGUFReader('/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf')
fld = rd.fields['tokenizer.ggml.tokens']
vocab = [bytes(fld.parts[i]).decode('utf-8', 'replace') for i in fld.data]
bs = list(range(33, 127)) + list(range(0xA1, 0xAD)) + list(range(0xAE, 0x100))
cs, k_ = bs[:], 0
for b in range(256):
    if b not in bs:
        bs.append(b); cs.append(256 + k_); k_ += 1
dec = {chr(c): b for b, c in zip(bs, cs)}
piece = lambda i: bytes(dec.get(ch, 63) for ch in vocab[i]).decode('utf-8', 'replace')
tok = np.array(run.recs['tok']); pr = run.prompt
cov = {}
for q in np.unique(pr):
    for t in set(np.unique(tok[pr == q]).tolist()):
        p = piece(t); cov[p] = cov.get(p, 0) + 1
common = {p for p, c in cov.items() if c >= 0.25 * len(np.unique(pr))}

DOC = {'|', '_of', '_text', 'end', 'begin', '><', '<', '>', '<|endoftext|>'}
NSFW = ('sex', 'porn', 'escort', 'nude', 'fuck', 'viagra', 'casino', 'xxx', 'dating', 'cock', 'pussy', 'slut', 'erotic', 'naked')
FNAME = {'sentence': 'sentence position', 'name': 'proper names', 'chatty': 'chatty vs institutional',
         'prose/struct': 'prose vs structured text', 'break': 'break vs continue', 'entropy': 'predictability', 'unclear': 'unidentified'}
PHRASE = {'since_end': ('deep into sentences', 'near sentence ends'), 'at_end': ('at sentence or line ends', 'mid-clause'),
          'markup16': ('in structured text (newlines, digits, symbols)', 'in running prose'),
          'pron32': ('in chatty first- and second-person text', 'in impersonal text'),
          'func16': ('where function words are dense', 'where function words are sparse'),
          'name': ('inside names', 'away from names'), 'entropy': ('where the next token is uncertain', 'where the next token is predictable'),
          'surprisal': ('right after surprising tokens', 'right after expected tokens'), 'newline': ('at line breaks', 'within lines')}
FSHORT = {'since_end': 'tokens since sentence end', 'at_end': 'sentence end', 'markup16': 'markup', 'pron32': 'I/you/!',
          'func16': 'function words', 'name': 'names', 'entropy': 'entropy', 'surprisal': 'surprisal', 'newline': 'newline'}


def f2(v):
    return f'{v:+.2f}'.replace('-', '−')


def f3(v):
    return f'{v:+.3f}'.replace('-', '−')


def tk(t):
    if t in DOC:
        return '‹doc-end›'
    s = t.replace('\n', '⏎')
    return '␣' if s.strip() == '' else s.strip()


def toks(lst, k=5, filt=True):
    out = []
    for t in lst:
        if filt and t not in common and t not in DOC:
            continue
        s = tk(t)
        if s not in out:
            out.append(s)
        if len(out) == k:
            break
    return out


def code(lst):
    return ' '.join('`' + s.replace('`', "'") + '`' for s in lst) if lst else '(no common tokens)'


def reading(sr, fam):
    c = sr['corr_cos']
    feats = [f for f in sorted(c, key=lambda f: -abs(c[f])) if f != 'norm' and abs(c[f]) >= 0.15]
    if 'at_end' in feats and 'newline' in feats:
        feats.remove('newline')
    feats = feats[:3]
    if not feats:
        f = max((f for f in c if f != 'norm'), key=lambda f: abs(c[f]))
        return f'In ordinary text it tracks none of the features clearly (largest: {FSHORT[f]} r {f2(c[f])}).'
    hi = [PHRASE[f][0 if c[f] > 0 else 1] for f in feats]
    s = f'In ordinary text it is high {", ".join(hi[:-1]) + (" and " if len(hi) > 1 else "") + hi[-1]} (r with |h| divided out: ' + \
        ', '.join(f'{FSHORT[f]} {f2(c[f])}' for f in feats) + ')'
    if fam == 'sentence':
        s += ', rising steadily through a sentence' if c['since_end'] > 0 else ', highest just after a sentence end and falling through the sentence'
    elif fam == 'break':
        s += ', a spike at the token itself rather than a running count'
    return s + '.'


def ctx(lst):
    for x in lst:
        if not any(w in x.lower() for w in NSFW):
            return '`' + x[-52:].replace('`', "'") + '`'
    return None


def label(L, side, rank):
    k = (L, side, rank)
    return FAM[k][0] if k in FAM else None


rows_tab, out = [], []
for r in D['layers']:
    L = r['layer']; sw = SW[L]; fx = sw['fixed']
    hp, ha = r['heldout_pushback'], r['heldout_amplify']
    edge = (r['null_top95'] - r['null_bottom5']) / 2
    resolved = ((r['kappa'][0] > r['null_top95']) or (r['kappa'][-1] < r['null_bottom5'])) and max(hp[0], -ha[0]) > 0.03
    dirs = {s: [x for x in r['directions'] if x['side'] == s] for s in ('pushback', 'amplify')}
    fs, ff, fh = FIX[L, 'probe_pushback_0'], FIX[L, 'probe_amplify_0'], fx['amplify_1']
    l40 = (f'Layer-40 directions at this layer: the sentence direction is read in ordinary text at |r| {abs(fs["corr_cos"]["since_end"]):.2f} '
           f'(tokens since sentence end) and pushed back by κ {f3(fx["pushback_0"]["kappa"])} ± {fx["pushback_0"]["se"]:.3f}; the formal-vs-casual '
           f'direction is read at |r| {abs(ff["corr_cos"]["pron32"]):.2f} (I/you/! density) and amplified by κ {f3(fx["amplify_0"]["kappa"])} ± '
           f'{fx["amplify_0"]["se"]:.3f}; hedging κ {f3(fh["kappa"])}. Mean-score check χ² {sw["chi2"]:.0f} on 32 degrees of freedom.')
    lines = []
    if not resolved:
        regS, readS = fx['pushback_0']['kappa'], abs(fs['corr_cos']['since_end'])
        head = ('nothing detectable' if readS < 0.2 else 'represented, not regulated' if regS < 0.005 else
                'represented, regulated only in traces' if regS < 0.015 else 'represented, weakly regulated')
        lines += [f'## Layer {L}: {head}', '',
                  f'No searched direction clears the noise (±{edge:.2f} in sample). Held out, the strongest pushed-back direction scores {f2(hp[0])} '
                  f'and the strongest amplified one {f2(ha[0])}.' +
                  (' The noise edge is wide because a push this low passes through every later layer and moves the next-token probabilities a lot, '
                   'while the state varies a lot from token to token.' if L in (0, 9) else '')]
        if readS >= 0.2:
            lines += ['', 'The layer-40 variables are already represented here, but writing ' + ('barely touches them.' if regS < 0.015 else 'regulates them only weakly.')]
        cell_p = cell_a = 'not above noise'
    else:
        p0, a0 = label(L, 'pushback', 0), label(L, 'amplify', 0)
        p_ok, a_ok = hp[0] >= 0.03, -ha[0] >= 0.03
        if L >= 57:
            head = 'output dynamics, break vs continue on both sides'
        else:
            head = (f'{FNAME[p0]} pushed back' if p_ok and p0 != 'unclear' else 'an unidentified direction pushed back' if p_ok else 'no clear push-back') + ', ' + \
                   (f'{FNAME[a0]} amplified' if a_ok and a0 != 'unclear' else 'an unidentified direction amplified' if a_ok else 'no clear amplification')
        lines += [f'## Layer {L}: {head}', '']
        s1 = (f'writing undoes {hp[0] * 100:.0f}% of a push along the strongest pushed-back direction ({FNAME[p0]})' if p_ok
              else f'the strongest pushed-back direction scores only {f2(hp[0])}')
        s2 = (f'{"" if p_ok else "writing "}amplifies a push along the strongest amplified one ({FNAME[a0]}) by {-ha[0] * 100:.0f}%' if a_ok
              else f'the strongest amplified one only {f2(ha[0])}')
        lines += [f'Held out, {s1}, and {s2}. The noise edge is ±{edge:.2f}.', '']
        for side, word in (('pushback', 'Pushed back'), ('amplify', 'Amplified')):
            for d in dirs[side]:
                rank = d['rank']
                ho = (hp if side == 'pushback' else ha)[rank]
                clears = ho >= 0.03 if side == 'pushback' else ho <= -0.03
                fam = label(L, side, rank)
                if not clears:
                    if rank <= 1:
                        lines.append(f'- **{word} {rank + 1}:** weak (held out {f2(ho)}), not interpreted.')
                    continue
                if rank == 2 and fam == 'unclear':
                    continue
                sr = SENS[(L, side, rank)]
                cmax = max(d['cos'].items(), key=lambda kv: abs(kv[1]))
                b = (f'- **{word} {rank + 1}: {FNAME[fam]}** (held out {f2(ho)}; κ {f2(d["kappa"])} ± {d["se"]:.2f} in sample; capacity {d["capacity"]:.2f}'
                     + (f'; cosine {abs(cmax[1]):.2f} with a layer-40 direction' if abs(cmax[1]) >= 0.5 else '') + '). ' + reading(sr, fam))
                b += f' Pushed toward +u, the model writes more {code(toks(d["more"]))} and less {code(toks(d["less"]))}'
                if abs(d['d_sentence_ends']) >= 0.2:
                    b += f'; sentence ends change by {f2(d["d_sentence_ends"])} per 32 tokens'
                if abs(d['d_logp']) >= 4:
                    b += f'; the text becomes {abs(d["d_logp"]):.0f} nats {"more" if d["d_logp"] > 0 else "less"} predictable'
                b += '.'
                jp = toks([t for t in d.get('jlens_promotes', []) if t in common], 4, filt=False)
                js = toks([t for t in d.get('jlens_suppresses', []) if t in common], 4, filt=False)
                if jp or js:
                    b += ' The J-lens reads it as ' + (f'promoting {code(jp)}' if jp else '') + (' and ' if jp and js else '') + (f'suppressing {code(js)}' if js else '') + '.'
                ch, cl = ctx(sr['high']), ctx(sr['low'])
                if ch and cl:
                    b += f' Highest at {ch}; lowest at {cl}.'
                lines.append(b)
        cell_p = (f'{FNAME[p0]} (r {max(abs(v) for k, v in SENS[(L, "pushback", 0)]["corr_cos"].items() if k != "norm"):.2f})' if p_ok else 'weak')
        cell_a = (f'{FNAME[a0]} (r {max(abs(v) for k, v in SENS[(L, "amplify", 0)]["corr_cos"].items() if k != "norm"):.2f})' if a_ok else 'weak')
    lines += ['', l40]
    if L == 40:
        lines += ['', 'This is the layer the earlier runs studied. With 51,200 continuations, its strongest directions reach +0.27 (sentence position) '
                      'and −0.30 (prose vs structured text) held out.']
    if L >= 57 and resolved:
        lines += ['', 'As at the other output layers, both sides read whether the current token ends a sentence or line. These are dynamics of the '
                      'next-token distribution (avoiding a word just written, prose and markup each continuing) rather than an internal variable.']
    out.append('\n'.join(lines))
    rows_tab.append(f'| {L} | {f2(hp[0])} | {f2(ha[0])} | ±{edge:.2f} | {cell_p} | {cell_a} |')

open(os.path.join(a.out, 'sections.md'), 'w').write('\n\n'.join(out) + '\n')
open(os.path.join(a.out, 'table.md'), 'w').write(
    '| Layer | Pushed back κ | Amplified κ | Noise edge | Top pushed-back direction (reading r) | Top amplified direction (reading r) |\n'
    '| --- | --- | --- | --- | --- | --- |\n' + '\n'.join(rows_tab) + '\n')
print(sum(len(x) for x in out), 'chars')
