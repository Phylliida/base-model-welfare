#!/usr/bin/env python3
"""Similarity of the all-layer probes to each other, two ways:

  weights      cosine of the probe directions in standardized coordinates (raw weight x the feature's sd over the
               training rows, all 61 layers concatenated): the space the ridge fit worked in. Raw-unit weights would
               mostly measure layer scale (they are small wherever activations are large).
  predictions  correlation of the probes' predictions over the test rows: whether two probes read the same signal
               in the data (cosine under the activations' covariance).

Probes: future difficulty (next 1 / 8 / 32 / 128, val-best strength), past difficulty (last 8 / 32 / 128, entire
context), decoded text statistics (entropy, surprisal, entropy before the current token, excess surprisal, log rank,
log context length). Standardization from $PROBES/rollprobe_standardization.npz (written from the saved kernels'
rows.npz the first time). Writes results/probe_similarity.{tex,txt} (colored LaTeX tables with the values; needs
\\usepackage[table]{xcolor} and graphicx) and results/probe_similarity.png.
"""
import json
import os

from common import PROBES, RESULTS, rows, Out
import numpy as np

KERNELS = os.environ.get('KERNELS', '/dev/shm/rollprobe_kernels')
D, NL = 6144, 61
SRC = [('rollprobe', ['next 1', 'next 8', 'next 32', 'next 128']), ('rollprobe_past', ['past 8', 'past 32', 'past 128', 'past all']),
       ('rollprobe_baseline', ['entropy', 'surprisal', 'entropy prev', 'excess surprisal', 'log rank', 'log context'])]
SHORT = {'next 1': 'next token', 'next 8': 'next 8', 'next 32': 'next 32', 'next 128': 'next 128', 'past 8': 'past 8',
         'past 32': 'past 32', 'past 128': 'past 128', 'past all': 'past, all', 'entropy': 'entropy', 'surprisal': 'surprisal',
         'entropy prev': 'entropy before', 'excess surprisal': 'excess surpr.', 'log rank': 'log rank', 'log context': 'log context'}
GROUP = {'next': 'future difficulty', 'past': 'past difficulty'}

st = f'{PROBES}/rollprobe_standardization.npz'
if not os.path.exists(st):
    kr = np.load(f'{KERNELS}/rows.npz', allow_pickle=True)
    np.savez(st, mu=kr['mu'].astype(np.float32), sd=kr['sd'].astype(np.float32),
             note='per layer and feature: mean and sd of the raw block output over the training rows of the rollout probes')
sd = np.load(st)['sd'].astype(np.float64)  # [61][6144]

names, W, P = [], [], []
for stem, targets in SRC:
    meta = json.load(open(f'{PROBES}/{stem}.json'))
    nm = meta['names']
    raw = np.fromfile(f'{PROBES}/{stem}_weights.f32', dtype=np.float32)[:len(nm) * NL * D].reshape(len(nm), NL, D)
    z = rows('' if stem == 'rollprobe' else stem[len('rollprobe'):])
    for t in targets:
        names.append(t)
        W.append((raw[nm.index(t)].astype(np.float64) * sd).reshape(-1))
        P.append(z['pred'][:, list(z['names']).index(t)])
W = np.stack(W)
W /= np.linalg.norm(W, axis=1, keepdims=True)
COS = W @ W.T
te = np.flatnonzero(rows()['split'] == 2)
COR = np.corrcoef(np.stack([p[te] for p in P]))

o = Out('probe_similarity.txt')
for title, M in (('cosine of the standardized probe weights', COS), ('correlation of the probes\' test-set predictions', COR)):
    o(title)
    o(' ' * 16 + ' '.join(f'{SHORT[n][:7]:>7s}' for n in names))
    for i, n in enumerate(names):
        o(f'{SHORT[n]:16s}' + ' '.join(f'{M[i, j]:+7.2f}' for j in range(len(names))))
    o()
o.save()

t = Out('probe_similarity.tex')
for title, M, lab in (('Cosine similarity of the all-layer probes\' weights (standardized coordinates).', COS, 'tab:probe-cosine'),
                      ('Correlation of the all-layer probes\' predictions on the test set.', COR, 'tab:probe-corr')):
    t('\\begin{table}[H]')
    t('  \\centering')
    t('  \\scriptsize')
    t('  \\setlength{\\tabcolsep}{2pt}')
    t('  \\begin{tabular}{l' + 'c' * len(names) + '}')
    t('    & ' + ' & '.join(f'\\rotatebox{{90}}{{{SHORT[n]}}}' for n in names) + ' \\\\')
    for i, n in enumerate(names):
        cells = []
        for j in range(len(names)):
            v = M[i, j]
            col = f'red!{round(60 * min(1, v))}' if v >= 0 else f'blue!{round(60 * min(1, -v))}'
            txt = f'{abs(v):.2f}' if round(v, 2) >= 0 else f'$-${abs(v):.2f}'
            cells.append(f'\\cellcolor{{{col}}}{txt}')
        t(f'    {SHORT[n]} & ' + ' & '.join(cells) + ' \\\\')
    t('  \\end{tabular}')
    t(f'  \\caption{{{title} Rows and columns: future difficulty (next token, next 8 / 32 / 128), past difficulty '
      '(last 8 / 32 / 128, entire context), decoded text statistics. Red positive, blue negative.}')
    t(f'  \\label{{{lab}}}')
    t('\\end{table}')
    t()
t.save()

import matplotlib  # noqa: E402
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
fig, axs = plt.subplots(1, 2, figsize=(17, 7.6))
for ax, M, title in ((axs[0], COS, 'cosine of standardized probe weights'), (axs[1], COR, 'correlation of test-set predictions')):
    im = ax.imshow(M, cmap='RdBu_r', vmin=-1, vmax=1)
    ax.set_xticks(range(len(names)), [SHORT[n] for n in names], rotation=60, ha='right', fontsize=9)
    ax.set_yticks(range(len(names)), [SHORT[n] for n in names], fontsize=9)
    for i in range(len(names)):
        for j in range(len(names)):
            ax.text(j, i, f'{M[i, j]:.2f}', ha='center', va='center', fontsize=7, color='white' if abs(M[i, j]) > 0.6 else 'black')
    for b in (3.5, 7.5):
        ax.axhline(b, color='k', lw=0.8)
        ax.axvline(b, color='k', lw=0.8)
    ax.set_title(title)
fig.colorbar(im, ax=axs, shrink=0.8)
fig.savefig(os.path.join(RESULTS, 'probe_similarity.png'), dpi=130, bbox_inches='tight')
print(f'-> {os.path.join(RESULTS, "probe_similarity.png")}')
