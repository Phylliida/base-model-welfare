#!/usr/bin/env python3
"""Numbers of the details section: sequence counts and mix, lengths, languages, split, probe positions, document
ends in rollouts, and the on-policy check (rollouts: mean surprisal = mean entropy; natural text: surprisal > entropy).
"""
import collections
import json


from common import SEQS, ACTS, LABEL, rows, Out
import numpy as np

J = [json.loads(l) for l in open(f'{SEQS}/jobs.jsonl')]
P = [json.loads(l) for l in open(f'{SEQS}/pretrain.jsonl')]
R = [json.loads(l) for l in open(f'{SEQS}/rollouts.jsonl')]
o = Out('data_composition.txt')
for nm, X in (('rollouts', J), ('natural windows', P)):
    L = np.array([x['target_len'] for x in X])
    c = collections.Counter(x['lang'] for x in X)
    o(f'{nm}: {len(X)}; length {L.min()}-{L.max()} tokens, median {int(np.median(L))}, mean {int(L.mean())}; '
      f'English {100 * c["eng_Latn"] / len(X):.1f}%, Chinese {100 * c["cmn_Hani"] / len(X):.1f}%, '
      f'other {100 * (len(X) - c["eng_Latn"] - c["cmn_Hani"]) / len(X):.1f}% ({", ".join(sorted(k for k in c if k not in ("eng_Latn", "cmn_Hani")))})')
o(f'total {len(J) + len(P)} sequences: {100 * len(J) / (len(J) + len(P)):.1f}% rollouts, {100 * len(P) / (len(J) + len(P)):.1f}% natural')
o(f'rollouts generated: {len(R)}; with at least one document end: {100 * np.mean([r["n_end"] > 0 for r in R]):.0f}%')
z = rows()
sp = z['split']
o(f'probe positions: {len(sp)} (pairs of consecutive tokens, depth {z["pos"].min()}-{z["pos"].max()}); '
  f'train / val / test {(sp == 0).sum()} / {(sp == 1).sum()} / {(sp == 2).sum()} (split by sequence)')
# on-policy check on chunk 0
seqs = [json.loads(l) for l in open(f'{SEQS}/capture_c0.jsonl')]
lab = np.fromfile(f'{ACTS}/c0/labels.bin', dtype=LABEL)
kind = np.array([s['kind'] for s in seqs])
ok = np.isfinite(lab['surprisal'])
for k in ('rollout', 'pretrain'):
    m = ok & np.isin(lab['seq'], np.flatnonzero(kind == k))
    s, h = lab['surprisal'][m].astype(float), lab['entropy_prev'][m].astype(float)
    o(f'chunk 0, {k}: mean surprisal {s.mean():.3f}, mean entropy {h.mean():.3f} nats ({m.sum()} tokens)')
o.save()
