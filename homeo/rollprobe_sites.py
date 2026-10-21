#!/usr/bin/env python3
"""Probe sites for one chunk of the rollout probe data (notes: "Plan for the overnight run").

Chunk k = rollouts with rid in [1000k, 1000(k+1)) plus the natural windows (pretrain.jsonl) with index in
[333k, 333(k+1)) (the last chunk takes the rest), so every chunk has the user's 75% rollouts / 25% pretraining mix.
Sites: pairs of consecutive positions (d, d+1) (the pair gives the token-to-token change of a forecast), at depths d
stratified uniformly over [16, len - 133] (the window of 128 tokens after the next one must fit after d + 1); 1 pair per
56 tokens of that span, 1 to 32 pairs per sequence. Lengths are log-uniform, so depths run from 16 to ~1,900, densest
at short contexts.
Writes OUT/capture_cK.jsonl for homeo-capture (prompt_ids, tokens, positions, plus rid / lang / kind).

usage: rollprobe_sites.py K [--out /mnt/models/homeo/rollouts2]
"""
import argparse
import json
import random

ap = argparse.ArgumentParser()
ap.add_argument('chunk', type=int)
ap.add_argument('--out', default='/mnt/models/homeo/rollouts2')
ap.add_argument('--n-chunks', type=int, default=5)
a = ap.parse_args()
k = a.chunk
D_LO, TAIL, PER, MAXP = 16, 133, 56, 32

roll = [json.loads(l) for l in open(f'{a.out}/rollouts.jsonl', encoding='utf-8')]
roll = sorted((r for r in roll if 1000 * k <= r['rid'] < 1000 * (k + 1)), key=lambda r: r['rid'])
pre = [json.loads(l) for l in open(f'{a.out}/pretrain.jsonl', encoding='utf-8')]
hi = len(pre) if k == a.n_chunks - 1 else 333 * (k + 1)
pre = pre[333 * k:hi]
n_pairs = 0
with open(f'{a.out}/capture_c{k}.jsonl', 'w', encoding='utf-8') as f:
    for r in roll + pre:
        n = len(r['prompt_ids']) + len(r['tokens'])
        assert n == r['target_len'], (r['rid'], n, r['target_len'])
        top = n - TAIL
        span = top - D_LO + 1
        m = max(1, min(MAXP, 1 + round(span / PER)))
        rng = random.Random(7_000_001 + r['rid'])
        edges = [D_LO + span * i / m for i in range(m + 1)]
        ds = sorted({min(top, int(rng.uniform(edges[i], edges[i + 1]))) for i in range(m)})
        # strata are >= 2 positions wide only when span >= 2m; drop pairs that would overlap
        keep = []
        for d in ds:
            if not keep or d > keep[-1] + 1:
                keep.append(d)
        pos = sorted(p for d in keep for p in (d, d + 1))
        n_pairs += len(keep)
        f.write(json.dumps({'rid': r['rid'], 'lang': r['lang'], 'kind': r.get('kind', 'rollout'), 'n_end': r['n_end'],
                            'prompt_ids': r['prompt_ids'], 'tokens': r['tokens'], 'positions': pos}, ensure_ascii=False) + '\n')
print(f'chunk {k}: {len(roll)} rollouts + {len(pre)} natural windows, {n_pairs} site pairs ({2 * n_pairs} rows) '
      f'-> {a.out}/capture_c{k}.jsonl')
