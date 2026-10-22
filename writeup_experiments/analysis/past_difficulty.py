#!/usr/bin/env python3
"""Numbers of the past-difficulty section: test R2 of the all-layer probes for the mean surprisal of the last 8 / 32 /
128 tokens and of the entire context, the entire-context probe by depth, and whether the state carries the difficulty
of text before the last 128 tokens beyond what the exact recent means give (depths 256-1024 and 1024+; OLS on train,
probe stacked on val, scored on test).
"""
import json


from common import PROBES, r2, rows, Out
import numpy as np

P = json.load(open(f'{PROBES}/rollprobe_past.json'))
zp = rows('_past')
z = rows()
o = Out('past_difficulty.txt')
o('all-layer probes, test R2 (within-sequence):')
for t, r in P['results'].items():
    o(f'  {t:9s} {100 * r["test"]:.1f}% ({100 * r["within"]:.1f}%)')
o('entire context by depth: ' + ', '.join(f'{g} {100 * v["test"]:.1f}%' for g, v in P['groups']['past all'].items() if g.startswith('depth')))
o('by kind and language (entire context): ' + ', '.join(f'{g} {100 * v["test"]:.1f}%' for g, v in P['groups']['past all'].items() if not g.startswith('depth')))
names = list(zp['names'])
Y, Pr, sp, pos = zp['Y'], zp['pred'], zp['split'], z['pos']
ja, j128 = names.index('past all'), names.index('past 128')
older = (Y[:, ja] * pos - Y[:, j128] * 128) / np.maximum(pos - 128, 1)  # mean surprisal of tokens before the last 128
X = np.stack([z['m128'], z['m32'], z['m8'], np.ones(len(pos))], 1)
o('text before the last 128 tokens, test R2:')
for lo, hi in ((256, 1024), (1024, 2048)):
    tr, va, te = (np.flatnonzero((sp == i) & (pos >= lo) & (pos < hi)) for i in range(3))
    w = np.linalg.lstsq(X[tr], older[tr], rcond=None)[0]
    Xp = np.hstack([Pr[:, [ja]], X])
    wp = np.linalg.lstsq(Xp[va], older[va], rcond=None)[0]
    o(f'  depth {lo}-{hi}: exact last-8/32/128 means {100 * r2(older[te], X[te] @ w):.1f}%, '
      f'+ the probe\'s entire-context read-out {100 * r2(older[te], Xp[te] @ wp):.1f}% (n test {len(te)})')
o.save()
