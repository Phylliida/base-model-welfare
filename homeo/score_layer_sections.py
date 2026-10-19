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

import torch  # noqa: F401  (before numpy: this venv's numpy needs torch's libz)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score_io import ScoreRun  # noqa: E402
from score_words import (O, FNAME, f2, f3, toks, reading, ctx, families, common_tokens, layer_resolved,  # noqa: E402
                         clears as clears_side)

ap = argparse.ArgumentParser()
ap.add_argument('--out', default='.')
a = ap.parse_args()
D = json.load(open(f'{O}/sweep.describe_cap64.json'))
SW = {r['layer']: r for r in json.load(open(f'{O}/sweep.sweep.json'))['layers']}
S = json.load(open(f'{O}/sense/sensor.json'))
SENS = {(r['layer'], r['side'], r['rank']): r for r in S['directions']}
FIX = {(r['layer'], r['name']): r for r in S['fixed']}
FAM = families()
common = common_tokens(ScoreRun(f'{O}/sweep'))


def code(lst):
    return ' '.join('`' + s.replace('`', "'") + '`' for s in lst) if lst else '(no common tokens)'


def quote(x):
    return '`' + x.replace('`', "'") + '`' if x else None


def label(L, side, rank):
    k = (L, side, rank)
    return FAM[k][0] if k in FAM else None


rows_tab, out = [], []
for r in D['layers']:
    L = r['layer']; sw = SW[L]; fx = sw['fixed']
    hp, ha = r['heldout_pushback'], r['heldout_amplify']
    edge = (r['null_top95'] - r['null_bottom5']) / 2
    resolved = layer_resolved(r)
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
                clears = clears_side(side, ho)
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
                b += f' Pushed toward +u, the model writes more {code(toks(d["more"], common))} and less {code(toks(d["less"], common))}'
                if abs(d['d_sentence_ends']) >= 0.2:
                    b += f'; sentence ends change by {f2(d["d_sentence_ends"])} per 32 tokens'
                if abs(d['d_logp']) >= 4:
                    b += f'; the text becomes {abs(d["d_logp"]):.0f} nats {"more" if d["d_logp"] > 0 else "less"} predictable'
                b += '.'
                jp = toks([t for t in d.get('jlens_promotes', []) if t in common], common, 4, filt=False)
                js = toks([t for t in d.get('jlens_suppresses', []) if t in common], common, 4, filt=False)
                if jp or js:
                    b += ' The J-lens reads it as ' + (f'promoting {code(jp)}' if jp else '') + (' and ' if jp and js else '') + (f'suppressing {code(js)}' if js else '') + '.'
                ch, cl = quote(ctx(sr['high'])), quote(ctx(sr['low']))
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
