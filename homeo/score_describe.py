"""Describe the most pushed-back and most amplified directions of a homeo-score run (plan B2).

Fits M = mean[(B R - b)(B G)^T] in a basis B (rows orthonormal: a capacity basis, PCA basis, ...) at one layer, takes
the top --n-dir eigenvectors of its symmetric part on each side, and for each direction u (unit, raw coordinates):
  - kappa(u) with SE clustered by prompt, capacity sigma_u sqrt(I_F,u), share of u in the top-32 / top-256 PCA
    subspace of layer 40, cosines with the probing run's layer-40 directions and known vectors;
  - effector: what the model writes more of when pushed along +u. By the score identity, for any statistic f of the
    written tokens, d E[f] / dc = E[(f - b) (u.G)]; with f = count of token t in the 32 written tokens this gives,
    per token, the change in its expected count per unit push (reported for a push of 0.25 x |h|, linearly) with a
    z-score; also sentence ends and the mean log-probability (entropy-like);
  - sensor (layer 40 only): correlations of u.h on natural text (VL2 states: tokens since the last sentence end,
    sentence end, entropy, surprisal, |h|) and the contexts where u.h is most extreme;
  - J-lens decode of u at the layer (tokens promoted / suppressed through the unembedding).
Writes PREFIX[.L<layer>].describe_<tag>.txt and .json, and the directions as f32 files.

usage: score_describe.py PREFIX --basis BASIS.f32 --k 128 [--layer 40] [--n-dir 4] [--tag cap128] [--no-jlens]
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
ap.add_argument('prefix')
ap.add_argument('--basis', required=True)
ap.add_argument('--k', type=int, required=True)
ap.add_argument('--layer', type=int, default=None)
ap.add_argument('--window', default='13-31')
ap.add_argument('--n-dir', type=int, default=4)
ap.add_argument('--tag', default=None)
ap.add_argument('--no-jlens', action='store_true')
ap.add_argument('--hn', type=float, default=257.1, help='mean |h| at layer 40, for the reference push size')
ap.add_argument('--jlens', default='/mnt/models/jlens/jlens_glm4_q4k.jlns')
ap.add_argument('--model', default='/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf')
a = ap.parse_args()
torch.set_grad_enabled(False)

run = ScoreRun(a.prefix)
layer = a.layer if a.layer is not None else (40 if 40 in run.layers else run.layers[0])
tag = a.tag or os.path.basename(a.basis).replace('.f32', '')
out_base = a.prefix + ('' if len(run.layers) == 1 else f'.L{layer}') + f'.describe_{tag}'
os.makedirs(out_base + '_dirs', exist_ok=True)
keep = np.flatnonzero(np.isin(run.prompt, run.whole_prompts()))
prompt = run.prompt[keep]
prompts = np.unique(prompt)
groups = [np.flatnonzero(prompt == q) for q in prompts]
n, D = len(keep), run.D
lines = []


def say(s=''):
    print(s, flush=True)
    lines.append(s)


def loo(x):
    out = np.empty_like(x)
    for idx in groups:
        s = x[idx].sum(0)
        out[idx] = x[idx] - (s[None] - x[idx]) / (len(idx) - 1)
    return out


B = np.fromfile(a.basis, dtype=np.float32, count=a.k * D).reshape(a.k, D).astype(np.float64)
G = run.G(layer, keep).astype(np.float64)
R = loo(run.R(layer, a.window, keep).astype(np.float64))
g, r = G @ B.T, R @ B.T
M = r.T @ g / n
ev, V = np.linalg.eigh((M + M.T) / 2)
say(f'{a.prefix}: layer {layer}, lags {a.window}, basis {a.basis} (K {a.k}), {n} continuations / {len(prompts)} prompts')
say(f'kappa spectrum: {" ".join(f"{-x:+.3f}" for x in ev[:6])} ... {" ".join(f"{-x:+.3f}" for x in ev[-6:])}')

# reference vectors
Qp = np.fromfile('/mnt/models/homeo/ident/basis_pca256_L40.f32', dtype=np.float32).reshape(-1, D).astype(np.float64)
known = {}
for nm in [f'pushback_{i}' for i in range(4)] + [f'amplify_{i}' for i in range(4)]:
    f = f'/mnt/models/homeo/ident/main_dirs/dir_{nm}.f32'
    if os.path.exists(f):
        known['probe ' + nm] = np.fromfile(f, dtype=np.float32).astype(np.float64)
for nm, f, row in [('temperature', '/mnt/models/homeo/s2opt/vec_temp1.3_opt2_L40.f32', None)] + \
        [(f'VL2 {x}', '/mnt/models/homeo/value_probe/readout_L40.f32', i) for i, x in enumerate(['stakes', 'now', 'next8', 'next32'])]:
    if os.path.exists(f):
        x = np.fromfile(f, dtype=np.float32).astype(np.float64)
        x = x[row * D:(row + 1) * D] if row is not None else x
        if x.size == D:
            known[nm] = x
known = {k: v / np.linalg.norm(v) for k, v in known.items()}

# token decoding
sys.path.insert(0, '/home/bepis/prog/llm-tests/llama.cpp/gguf-py')
import gguf  # noqa: E402
rd = gguf.GGUFReader(a.model)
fld = rd.fields['tokenizer.ggml.tokens']
vocab = [bytes(fld.parts[i]).decode('utf-8', 'replace') for i in fld.data]
bs = list(range(33, 127)) + list(range(0xA1, 0xAD)) + list(range(0xAE, 0x100))
cs, k_ = bs[:], 0
for b_ in range(256):
    if b_ not in bs:
        bs.append(b_); cs.append(256 + k_); k_ += 1
BYTE_DEC = {chr(c): b_ for b_, c in zip(bs, cs)}
tok_bytes = lambda i: bytes(BYTE_DEC.get(ch, 63) for ch in vocab[i])
piece = lambda i: tok_bytes(i).decode('utf-8', 'replace')
text_of = lambda t: b''.join(tok_bytes(i) for i in t if i >= 0).decode('utf-8', 'replace')
V_n = len(vocab)
ends = np.array([(v.rstrip('Ġ').endswith(('.', '!', '?', '。', '！', '？')) or 'Ċ' in v) for v in vocab])

J = Wu = gout = None
if not a.no_jlens:
    with open(a.jlens, 'rb') as f:
        hdr = np.frombuffer(f.read(16), dtype=np.uint32)
        n_probes, n_pos = np.frombuffer(f.read(16), dtype=np.uint64)
        f.seek(32 + layer * D * D * 4)
        J = np.frombuffer(f.read(D * D * 4), dtype=np.float32).reshape(D, D).T / float(n_pos)
    tens = {t.name: t for t in rd.tensors}
    Wu = gguf.quants.dequantize(tens['output.weight'].data, tens['output.weight'].tensor_type).reshape(-1, D).astype(np.float32)
    gout = np.asarray(gguf.quants.dequantize(tens['output_norm.weight'].data, tens['output_norm.weight'].tensor_type), np.float32).ravel()

# written tokens and per-prompt centered scores (the baseline for text statistics)
tok = np.array(run.recs['tok'][keep])                       # [n, 32]
logp = run.logp[keep].sum(1)
n_end = ends[np.clip(tok, 0, V_n - 1)].sum(1).astype(np.float64)
push = 0.25 * a.hn

# natural-text states (layer 40 only)
nat = None
if layer == 40:
    from value_probe import SAMPLE  # noqa: E402
    vd = '/mnt/models/homeo/value_probe/main'
    srec = np.fromfile(f'{vd}/samples.bin', dtype=SAMPLE)
    acts = np.memmap(f'{vd}/acts_L40.f16', dtype=np.float16, mode='r', shape=(len(srec), D))
    kk = np.flatnonzero(srec['kind'] == 0)
    rr = srec[kk]
    o = np.lexsort((rr['pos'], rr['seq']))
    kk, rr = kk[o][:60000], rr[o][:60000]
    X = np.asarray(acts[kk], dtype=np.float32)
    since = np.zeros(len(rr), np.int32)
    cur, prev = 0, -1
    for i in range(len(rr)):
        if rr['seq'][i] != prev:
            cur, prev = 0, rr['seq'][i]
        cur = 0 if ends[rr['token'][i]] else cur + 1
        since[i] = cur
    nat = dict(X=X, rr=rr, since=since, norm=np.linalg.norm(X, axis=1))

out = {'layer': layer, 'basis': a.basis, 'k': a.k, 'kappa': (-ev).tolist(), 'directions': []}
for side, idxs in (('pushback', range(a.n_dir)), ('amplify', [len(ev) - 1 - i for i in range(a.n_dir)])):
    say()
    say(f'===== most {"pushed back" if side == "pushback" else "amplified"} directions')
    for rank, j in enumerate(idxs):
        u = B.T @ V[:, j]
        u /= np.linalg.norm(u)
        u.astype(np.float32).tofile(f'{out_base}_dirs/{side}_{rank}.f32')
        ru, su = R @ u, G @ u
        x = -ru * su
        pm = np.array([x[idx].mean() for idx in groups])
        cap = float(np.sqrt(np.mean(ru ** 2) * np.mean(su ** 2)))
        say()
        say(f'--- {side} {rank}: kappa {x.mean():+.3f} +- {pm.std(ddof=1) / np.sqrt(len(groups)):.3f} (clustered), capacity {cap:.2f}; '
            f'share in top-32 / top-256 PCA of layer 40: {np.sum((Qp[:32] @ u) ** 2):.2f} / {np.sum((Qp @ u) ** 2):.2f}')
        cos = sorted(((abs(float(v_ @ u)), nm, float(v_ @ u)) for nm, v_ in known.items()), reverse=True)[:4]
        say('    largest |cos| with known vectors: ' + ', '.join(f'{nm} {c:+.2f}' for _, nm, c in cos))
        # effector: d E[f] / dc for written-token statistics, f centered within prompt
        sc = su.copy()
        for idx in groups:
            sc[idx] -= sc[idx].mean()
        d_end = float(np.mean((n_end - n_end.mean()) * sc)) * push
        d_lp = float(np.mean((logp - logp.mean()) * sc)) * push
        cnt = np.zeros(V_n); cnt2 = np.zeros(V_n)
        w = np.repeat(sc, tok.shape[1]); t = np.clip(tok.ravel(), 0, V_n - 1)
        np.add.at(cnt, t, w)
        np.add.at(cnt2, t, w ** 2)
        dE = cnt / n * push                                    # change in expected count per 32 tokens
        z = cnt / np.sqrt(np.maximum(cnt2, 1e-30))
        ok = cnt2 > 0
        up = [i for i in np.argsort(-z) if ok[i]][:14]
        dn = [i for i in np.argsort(z) if ok[i]][:14]
        say(f'    effector (push +u by 0.25 x |h|, linear): sentence ends per 32 tokens {d_end:+.3f} (mean {n_end.mean():.2f}), '
            f'log p of the written text {d_lp:+.2f} nats (mean {logp.mean():.1f})')
        say('      writes more: ' + ' | '.join(f'{piece(i)!r} {dE[i]:+.3f}' for i in up))
        say('      writes less: ' + ' | '.join(f'{piece(i)!r} {dE[i]:+.3f}' for i in dn))
        d = {'side': side, 'rank': rank, 'kappa': float(x.mean()), 'capacity': cap, 'd_sentence_ends': d_end, 'd_logp': d_lp,
             'more': [piece(i) for i in up], 'less': [piece(i) for i in dn]}
        if J is not None:
            lg = Wu @ (gout * (J @ u))
            say('    J-lens promotes:   ' + ' | '.join(repr(piece(i)) for i in np.argsort(-lg)[:12]))
            say('    J-lens suppresses: ' + ' | '.join(repr(piece(i)) for i in np.argsort(lg)[:12]))
        if nat is not None:
            pj = nat['X'] @ u
            sd = pj.std()
            bins = [0, 1, 2, 4, 8, 16, 41]
            prof = [(pj[(nat['since'] >= bins[i]) & (nat['since'] < bins[i + 1])].mean() - pj.mean()) / sd for i in range(len(bins) - 1)]
            say(f'    natural text: corr since-end {np.corrcoef(pj, np.minimum(nat["since"], 40))[0, 1]:+.2f}, at-end '
                f'{np.corrcoef(pj, nat["since"] == 0)[0, 1]:+.2f}, entropy {np.corrcoef(pj, nat["rr"]["entropy"])[0, 1]:+.2f}, '
                f'surprisal {np.corrcoef(pj, nat["rr"]["surprisal"])[0, 1]:+.2f}, |h| {np.corrcoef(pj, nat["norm"])[0, 1]:+.2f}; '
                f'by tokens since end 0/1/2-3/4-7/8-15/16+ (sd): ' + ' '.join(f'{p_:+.2f}' for p_ in prof))
            rr_ = nat['rr']
            for lab, order in (('highest', np.argsort(-pj)), ('lowest', np.argsort(pj))):
                ex = []
                for i in order[:400]:
                    s0 = i
                    while s0 > 0 and rr_['seq'][s0 - 1] == rr_['seq'][i] and i - s0 < 14:
                        s0 -= 1
                    ctx = text_of(rr_['token'][s0:i]) + '[[' + text_of([rr_['token'][i]]) + ']]'
                    if all(ctx[-30:] != e[-30:] for e in ex):
                        ex.append(ctx)
                    if len(ex) == 4:
                        break
                say(f'      {lab} u.h: ' + '  ||  '.join(repr(e[-70:]) for e in ex))
        out['directions'].append(d)

open(out_base + '.txt', 'w').write('\n'.join(lines) + '\n')
json.dump(out, open(out_base + '.json', 'w'), indent=1)
print(f'-> {out_base}.txt')
