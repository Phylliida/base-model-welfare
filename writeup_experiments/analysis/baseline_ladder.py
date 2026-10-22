#!/usr/bin/env python3
"""Tables 2-3 (baseline ladder) and the "probe alone / baselines / combined" numbers of the future-difficulty section.

Targets: difficulty of the next 32 / 128 tokens = mean surprisal of the 32 / 128 tokens after the next one. Baselines
are OLS on the training rows, adding one feature group per rung; "+ probe" stacks the all-layer probe's prediction with
the same features (weights fit on the validation rows); everything is scored on the test rows. Also the stricter
"added" of the fit (probe fit to the baseline's residual) from rollprobe.json.
"""

from common import r2, rows, result, past_all_mean, Out
import numpy as np

z = rows()
J = result()
names = list(z['names'])
sp = z['split']
tr, va, te = (np.flatnonzero(sp == i) for i in range(3))
one = np.ones(len(sp))
F = {'past': [past_all_mean(z)], 'ent': [z['ent']], 'cur': [z['cur']], 'win': [z['m8'], z['m32'], z['m128']], 'logd': [z['logd']]}
LADDER = [('Mean surprisal of all prior tokens', ['past']), ('\\quad + current entropy', ['past', 'ent']),
          ('\\quad + current surprisal', ['past', 'ent', 'cur']), ('\\quad + mean surprisal of last 8/32/128', ['past', 'ent', 'cur', 'win']),
          ('\\quad + log context length', ['past', 'ent', 'cur', 'win', 'logd'])]
o = Out('baseline_ladder.tex')
summary = Out('baseline_ladder.txt')
for K in (32, 128):
    j = names.index(f'next {K}')
    y, pred = z['Y'][:, j], z['pred'][:, j]
    o(f'% Difficulty of the next {K} tokens: test R2 (baseline OLS on train; + probe stacked on val)')
    o('\\begin{tabular}{lccc}')
    o('  \\toprule')
    o('  Baseline features & Baseline & + Probe & Probe Added \\\\')
    o('  \\midrule')
    last = None
    for lab, fs in LADDER:
        X = np.stack(sum([F[f] for f in fs], []) + [one], 1)
        w = np.linalg.lstsq(X[tr], y[tr], rcond=None)[0]
        rb = r2(y[te], X[te] @ w)
        Xs = np.hstack([pred[:, None], X])
        ws = np.linalg.lstsq(Xs[va], y[va], rcond=None)[0]
        rs = r2(y[te], Xs[te] @ ws)
        o(f'  {lab:44s} & {rb:.3f} & {rs:.3f} & ${rs - rb:+.3f}$ \\\\')
        last = (rb, rs)
    ra = r2(y[te], pred[te])
    o('  \\midrule')
    o(f'  {"Probe alone":44s} & \\multicolumn{{3}}{{c}}{{{ra:.3f}}} \\\\')
    o('  \\bottomrule')
    o('\\end{tabular}')
    o()
    strict = J['joint'][f'added {K}']['test']
    summary(f'next {K}: probe alone {100 * ra:.1f}%, full baseline {100 * last[0]:.1f}%, combined {100 * last[1]:.1f}%, '
            f'added {100 * (last[1] - last[0]):.1f} points (stacked) / {100 * strict:.1f} points (strict: probe fit to the baseline residual)')
o.save()
summary.save()
