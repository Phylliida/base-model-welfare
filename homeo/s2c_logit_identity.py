#!/usr/bin/env python3
"""S2c: is a token's raw logit (pre-softmax) a property of the token or of the context?

For absolute logit bands [z-1, z+1]: how many tokens / how much probability sit in the band,
how sticky band membership is across contexts, and how well token identity alone (band
frequency on half the positions) predicts membership on the other half (AUC, precision/recall
of the set of tokens in-band >= 50% of the time, prob-mass recall).

usage: s2c_logit_identity.py /mnt/models/homeo/logits/raw.f16
"""
import torch  # before numpy (lib resolution on this box)
import json
import sys

import numpy as np

path = sys.argv[1]
m = json.load(open(path + '.json'))
P, V = m['n_positions'], m['n_vocab']
Z = torch.from_numpy(np.fromfile(path, dtype=np.float16).reshape(P, V)).cuda().float()
lse = torch.logsumexp(Z, 1, keepdim=True)
prob = (Z - lse).exp()
top = Z.max(1).values
q = lambda x, qs: [round(float(v), 2) for v in torch.quantile(x.flatten()[torch.randint(0, x.numel(), (2_000_000,), device=x.device)], torch.tensor(qs, device=x.device))]
print(f'positions {P}, vocab {V}')
print('top logit quantiles 5/25/50/75/95%:', [round(float(v), 2) for v in torch.quantile(top, torch.tensor([.05, .25, .5, .75, .95], device='cuda'))])
print('logsumexp quantiles 5/50/95%:     ', [round(float(v), 2) for v in torch.quantile(lse[:, 0], torch.tensor([.05, .5, .95], device='cuda'))])
print('all-logit quantiles 1/50/99/99.9%: ', q(Z, [.01, .5, .99, .999]))

mx = Z.mean(0)
var_tot = Z.var(unbiased=False)
print(f'\nvariance of raw logits explained by token identity (all tokens): {float(mx.var(unbiased=False) / var_tot):.3f}')
for lo, hi in ((0, 5), (5, 10), (10, 100)):
    sel = (Z > lo) & (Z <= hi)
    zz, mm = Z[sel], mx.expand(P, V)[sel]
    r2 = 1 - ((zz - mm) ** 2).mean() / zz.var(unbiased=False)
    print(f'  logits in ({lo},{hi}]: R2 of z from the token\'s mean logit = {float(r2):.3f}  (n={int(sel.sum())})')

g = torch.Generator(device='cpu').manual_seed(0)
perm = torch.randperm(P, generator=g)
A, B = perm[: P // 2].cuda(), perm[P // 2:].cuda()
print('\nband [z-1, z+1] | tokens/pos  mass/pos | stickiness | identity AUC | set>=50%: prec  recall  mass-recall | median rank')
for zc in range(int(float(torch.quantile(top, 0.95))) + 1, -3, -2):
    inb = (Z >= zc - 1) & (Z <= zc + 1)
    ntok = inb.sum(1).float()
    mass = torch.where(inb, prob, 0).sum(1)
    fA = inb[A].float().mean(0)                   # per-token band frequency on half A
    inB = inb[B]
    pos_cnt = inB.sum(0).float()                  # per token: # B-positions in band
    neg_cnt = len(B) - pos_cnt
    # AUC of f_A as a score for membership over all (t in B, x) pairs
    order = torch.argsort(fA)
    f_sorted, pc, nc = fA[order], pos_cnt[order], neg_cnt[order]
    uniq, inv = torch.unique_consecutive(f_sorted, return_inverse=True)
    pc_g = torch.zeros(len(uniq), device='cuda').index_add_(0, inv, pc)
    nc_g = torch.zeros(len(uniq), device='cuda').index_add_(0, inv, nc)
    neg_below = torch.cumsum(nc_g, 0) - nc_g
    auc = float((pc_g * (neg_below + 0.5 * nc_g)).sum() / (pc_g.sum() * nc_g.sum()).clamp_min(1))
    S = fA >= 0.5
    prec = float(inB[:, S].float().mean()) if S.any() else float('nan')
    rec = float(inB[:, S].sum() / inB.sum().clamp_min(1))
    pB = torch.where(inB, prob[B], 0)
    mrec = float(pB[:, S].sum() / pB.sum().clamp_min(1e-12))
    del pB
    # stickiness: P(in band at a random other position | in band at t)
    stick = float((pos_cnt * (pos_cnt - 1)).sum() / (pos_cnt * (len(B) - 1)).sum().clamp_min(1))
    rk = (Z[B] > (zc + 1)).sum(1).float()        # tokens above the band = rank of the band's top edge
    print(f'  z={zc:+3d}          | {float(ntok.mean()):9.1f} {float(mass.mean()):8.4f} | {stick:9.3f}  | {auc:11.3f}  | {prec:13.3f} {rec:7.3f} {mrec:9.3f}  | {float(rk.median()):6.0f}')
