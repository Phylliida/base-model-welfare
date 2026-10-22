#!/usr/bin/env python3
"""Figures: test R2 of single-layer probes at every layer, with the all-layer probe (dashed) and, for the future
targets, the text-statistics baseline (dotted). Future: next 32 / 128 (rollprobe.json per_layer). Past: last 32 / 128
and the entire past context (rollprobe_layers_more.json from homeo/rollprobe_layers.py; skipped if missing).
Decoded text statistics (rollprobe_layers_more.json; all-layer values from rollprobe_baseline.json): two figures of three.
Writes pgfplots figures (needs \\usepackage{pgfplots}, \\pgfplotsset{compat=1.18}, and float for [H]).
"""
import json
import os

from common import PROBES, result, Out


def coords(vals):
    pts = [f'({L},{100 * v:.1f})' for L, v in enumerate(vals)]
    return '\n'.join('        ' + ' '.join(pts[i:i + 10]) for i in range(0, len(pts), 10))


def figure(name, curves, hlines, caption, label, ymax=60, legend='south east'):
    o = Out(name)
    o('\\begin{figure}[H]')
    o('  \\centering')
    o('  \\begin{tikzpicture}')
    o('    \\begin{axis}[')
    o('        width=\\linewidth, height=6.5cm,')
    o('        xlabel={Layer}, ylabel={Test $R^2$ (\\%)},')
    o(f'        xmin=0, xmax=60, ymin=0, ymax={ymax},')
    o('        xtick={0,10,20,30,40,50,60},')
    o('        grid=major, grid style={gray!25},')
    if legend == 'below':  # outside the axes, under the x label, two columns
        o('        legend style={at={(0.5,-0.25)}, anchor=north, legend columns=2}, legend cell align=left,')
    else:
        o(f'        legend pos={legend}, legend cell align=left,')
    o('        legend style={font=\\small},')
    o('      ]')
    for color, vals, leg in curves:
        o(f'      \\addplot[thick, {color}, mark=none] coordinates {{')
        o(coords(vals))
        o('      };')
        o(f'      \\addlegendentry{{{leg}}}')
    for color, style, v, leg in hlines:
        o(f'      \\addplot[{color}, {style}] coordinates {{(0,{100 * v:.1f}) (60,{100 * v:.1f})}};')
        o(f'      \\addlegendentry{{{leg}}}')
    o('    \\end{axis}')
    o('  \\end{tikzpicture}')
    o(f'  \\caption{{{caption}}}')
    o(f'  \\label{{{label}}}')
    o('\\end{figure}')
    o.save()


J = result()
pl = J['per_layer']
fut = {K: [pl[str(L)][f'next {K}']['test'] for L in range(61)] for K in (32, 128)}
peak = {K: max(range(61), key=lambda L: fut[K][L]) for K in (32, 128)}
figure('fig_future_layers.tex',
       [('blue', fut[32], 'Next 32 tokens (single layer)'), ('red', fut[128], 'Next 128 tokens (single layer)')],
       [('blue', 'dashed', J['joint']['next 32']['test'], 'Next 32, all layers'),
        ('red', 'dashed', J['joint']['next 128']['test'], 'Next 128, all layers'),
        ('blue', 'dotted, thick', J['baseline_r2']['next 32'], 'Next 32, baseline'),
        ('red', 'dotted, thick', J['baseline_r2']['next 128'], 'Next 128, baseline')],
       'Test $R^2$ for predicting difficulty (mean surprisal of the next 32 or 128 tokens after the next one) from a '
       'linear probe on one layer\'s activations at the current token. Dashed: one probe on all 61 layers. Dotted: '
       f'text-statistics baseline. Single layers peak at layer {peak[32]} (32) and {peak[128]} (128).', 'fig:layer-r2')

more = f'{PROBES}/rollprobe_layers_more.json'
if os.path.exists(more):
    M = json.load(open(more))['per_layer']
    P = json.load(open(f'{PROBES}/rollprobe_past.json'))['results']
    past = {t: [M[str(L)][t]['test'] for L in range(61)] for t in ('past 32', 'past 128', 'past all')}
    pk = {t: max(range(61), key=lambda L: past[t][L]) for t in past}
    figure('fig_past_layers.tex',
           [('blue', past['past 32'], 'Last 32 tokens (single layer)'), ('red', past['past 128'], 'Last 128 tokens (single layer)'),
            ('black!60!green', past['past all'], 'Entire context (single layer)')],
           [('blue', 'dashed', P['past 32']['test'], 'Last 32, all layers'), ('red', 'dashed', P['past 128']['test'], 'Last 128, all layers'),
            ('black!60!green', 'dashed', P['past all']['test'], 'Entire context, all layers')],
           'Test $R^2$ for decoding past difficulty (mean surprisal of the last 32 or 128 tokens, or of the entire '
           'context so far) from a linear probe on one layer\'s activations at the current token. Dashed: one probe on '
           f'all 61 layers. Single layers peak at layer {pk["past 32"]} (32), {pk["past 128"]} (128) and {pk["past all"]} (entire context).',
           'fig:layer-r2-past', ymax=90)
    Bj = json.load(open(f'{PROBES}/rollprobe_baseline.json'))['results']
    for name, label, targets in (
            ('fig_decoded_layers_a.tex', 'fig:layer-r2-decoded-a',
             [('entropy', 'next-token entropy'), ('entropy prev', 'entropy before the token'), ('log context', 'log context length')]),
            ('fig_decoded_layers_b.tex', 'fig:layer-r2-decoded-b',
             [('surprisal', 'surprisal'), ('log rank', 'log rank'), ('excess surprisal', 'excess surprisal')])):
        cols = ['blue', 'red', 'black!60!green']
        vals = {t: [M[str(L)][t]['test'] for L in range(61)] for t, _ in targets}
        pkd = {t: max(range(61), key=lambda L: vals[t][L]) for t, _ in targets}
        figure(name,
               [(c, vals[t], f'{lab[0].upper() + lab[1:]} (one layer)') for c, (t, lab) in zip(cols, targets)],
               [(c, 'dashed', Bj[t]['test'], f'{lab[0].upper() + lab[1:]}, all layers') for c, (t, lab) in zip(cols, targets)],
               'Test $R^2$ for decoding text statistics from a linear probe on one layer\'s activations at the current '
               'token' + (' (surprisal, log rank and excess surprisal $=$ surprisal $-$ expected are of the current token)' if name.endswith('_b.tex') else '') +
               '. Dashed: one probe on all 61 layers. Single-layer peaks: ' +
               ', '.join(f'{lab} layer {pkd[t]}' for t, lab in targets) + '.', label, ymax=100,
               legend='below' if name.endswith('_b.tex') else 'south east')
else:
    print(f'{more} not found: run homeo/rollprobe_layers.py for the past-difficulty and decoded-statistics figures')
