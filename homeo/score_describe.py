"""Describe the most pushed-back and most amplified directions of a homeo-score run (plan B2), at one or many layers.

Per layer L: fits M = mean[(B R - b)(B G)^T] in a basis B (rows orthonormal; --basis may contain {L} for a per-layer
file), with b the leave-one-out mean over the continuations of the same prompt; reports the kappa spectrum against a
within-prompt permutation null and split-half replication (directions from half the prompts, kappa on the other
half), and takes the top --n-dir eigenvectors of the symmetric part on each side. For each direction u (unit, raw):
  - kappa(u) with SE clustered by prompt, capacity sigma_u sqrt(I_F,u), cosines with reference directions (by
    default the screen's layer-40 directions) and known vectors;
  - effector: what the model writes more of when pushed along +u. By the score identity d E[f] / dc = E[(f - b) u.G]
    for any statistic f of the written tokens: per token, the change in its expected count per 32 tokens for a push
    of 0.25 x |h| (linear), with a z-score; sentence ends; the log-probability of the written text;
  - J-lens decode of u at layer L (tokens promoted / suppressed through the unembedding);
  - sensor (layer 40 only): u.h on natural text (VL2 states) against tokens since the last sentence end, entropy,
    surprisal, |h|, and the contexts where it is most extreme.
Writes PREFIX.describe_<tag>.txt / .json and the directions under PREFIX.describe_<tag>_dirs/.

usage: score_describe.py PREFIX --basis BASIS.f32 --k 128 [--layers 40 | 0-60] [--n-dir 3] [--tag cap128] [--no-jlens]
"""
import argparse
import json
import os
import sys
import time

import torch
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score_io import ScoreRun  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('prefix')
ap.add_argument('--basis', required=True, help='f32 [>=K][n_embd]; may contain {L}')
ap.add_argument('--k', type=int, required=True)
ap.add_argument('--layers', default=None, help='e.g. 40, 0-60, 20,40; default: 40 if captured, else the first layer')
ap.add_argument('--window', default='13-31')
ap.add_argument('--n-dir', type=int, default=3)
ap.add_argument('--n-perm', type=int, default=50)
ap.add_argument('--n-split', type=int, default=10)
ap.add_argument('--tag', default=None)
ap.add_argument('--ref-dirs', default='/mnt/models/homeo/score/screen.describe_cap128_dirs',
                help='directory of reference directions (*.f32) to compare with')
ap.add_argument('--no-jlens', action='store_true')
ap.add_argument('--hn', type=float, default=257.1, help='mean |h| at layer 40, for the reference push size')
ap.add_argument('--jlens', default='/mnt/models/jlens/jlens_glm4_q4k.jlns')
ap.add_argument('--model', default='/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf')
a = ap.parse_args()
torch.set_grad_enabled(False)
rng = np.random.default_rng(0)

run = ScoreRun(a.prefix)
if a.layers:
    want = []
    for t in a.layers.split(','):
        l0, _, l1 = t.partition('-')
        want += list(range(int(l0), int(l1 or l0) + 1))
    layers = [L for L in run.layers if L in want]
else:
    layers = [40 if 40 in run.layers else run.layers[0]]
tag = a.tag or os.path.basename(a.basis).replace('.f32', '').replace('{L}', 'L')
out_base = a.prefix + f'.describe_{tag}'
os.makedirs(out_base + '_dirs', exist_ok=True)
keep = np.flatnonzero(np.isin(run.prompt, run.whole_prompts()))
prompt = run.prompt[keep]
prompts = np.unique(prompt)
groups = [np.flatnonzero(prompt == q) for q in prompts]
n, D, K = len(keep), run.D, a.k
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


def sym(M):
    return (M + M.T) / 2


# reference and known vectors
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
refs = {}
if a.ref_dirs and os.path.isdir(a.ref_dirs) and os.path.realpath(a.ref_dirs) != os.path.realpath(out_base + '_dirs'):
    for f in sorted(os.listdir(a.ref_dirs)):
        if f.endswith('.f32'):
            refs['L40 ' + f[:-4]] = np.fromfile(os.path.join(a.ref_dirs, f), dtype=np.float32).astype(np.float64)
known = {k: v / np.linalg.norm(v) for k, v in known.items()}
refs = {k: v / np.linalg.norm(v) for k, v in refs.items()}

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

Wu = gout = n_pos = None
if not a.no_jlens:
    with open(a.jlens, 'rb') as f:
        hdr = np.frombuffer(f.read(16), dtype=np.uint32)
        n_probes, n_pos = np.frombuffer(f.read(16), dtype=np.uint64)
    tens = {t.name: t for t in rd.tensors}
    Wu = gguf.quants.dequantize(tens['output.weight'].data, tens['output.weight'].tensor_type).reshape(-1, D).astype(np.float32)
    gout = np.asarray(gguf.quants.dequantize(tens['output_norm.weight'].data, tens['output_norm.weight'].tensor_type), np.float32).ravel()


def jlens_at(L):
    with open(a.jlens, 'rb') as f:
        f.seek(32 + L * D * D * 4)
        return np.frombuffer(f.read(D * D * 4), dtype=np.float32).reshape(D, D).T / float(n_pos)


# written tokens and their statistics
tok = np.array(run.recs['tok'][keep])
logp = run.logp[keep].sum(1)
n_end = ends[np.clip(tok, 0, V_n - 1)].sum(1).astype(np.float64)
push = 0.25 * a.hn
# effector lists only for tokens written in at least 10% of the prompts (rarer ones are prompt-specific topic words)
prompt_cov = np.zeros(V_n)
for idx in groups:
    prompt_cov[np.unique(np.clip(tok[idx], 0, V_n - 1))] += 1
common = prompt_cov >= max(5, 0.1 * len(groups))

# natural-text states at layer 40
nat = None
if 40 in layers:
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

say(f'{a.prefix}: {n} continuations / {len(prompts)} prompts; lags {a.window}; basis {a.basis} (K {K}); layers {layers[0]}..{layers[-1]}')
summary = []
t0 = time.time()
for L in layers:
    bpath = a.basis.replace('{L}', str(L))
    B = np.fromfile(bpath, dtype=np.float32, count=K * D).reshape(K, D).astype(np.float64)
    G = run.G(L, keep).astype(np.float64)
    R = loo(run.R(L, a.window, keep).astype(np.float64))
    g, r = G @ B.T, R @ B.T
    M = r.T @ g / n
    ev, V = np.linalg.eigh(sym(M))
    hi, lo = [], []
    for _ in range(a.n_perm):
        gp = g.copy()
        for idx in groups:
            gp[idx] = g[rng.permutation(idx)]
        e = np.linalg.eigvalsh(sym(r.T @ gp / n))
        hi.append(-e[0]); lo.append(-e[-1])
    rep = {'pushback': [], 'amplify': []}
    for _ in range(a.n_split):
        perm = rng.permutation(len(prompts))
        A = np.isin(prompt, prompts[perm[:len(prompts) // 2]]); Bm = ~A
        eA, VA = np.linalg.eigh(sym(r[A].T @ g[A] / A.sum()))
        MB = r[Bm].T @ g[Bm] / Bm.sum()
        rep['pushback'].append([-(VA[:, i] @ MB @ VA[:, i]) for i in range(a.n_dir)])
        rep['amplify'].append([-(VA[:, -1 - i] @ MB @ VA[:, -1 - i]) for i in range(a.n_dir)])
    J = jlens_at(L) if Wu is not None else None
    say()
    say(f'################ layer {L}: kappa {" ".join(f"{-x:+.3f}" for x in ev[:4])} ... {" ".join(f"{-x:+.3f}" for x in ev[-4:])}; '
        f'null {np.percentile(hi, 95):+.3f} / {np.percentile(lo, 5):+.3f}; held-out (split halves) pushed back '
        + ' '.join(f'{np.mean([x[i] for x in rep["pushback"]]):+.3f}' for i in range(a.n_dir)) + ', amplified '
        + ' '.join(f'{np.mean([x[i] for x in rep["amplify"]]):+.3f}' for i in range(a.n_dir)) + f'  ({time.time() - t0:.0f} s)')
    lrow = {'layer': L, 'kappa': (-ev).tolist(), 'null_top95': float(np.percentile(hi, 95)), 'null_bottom5': float(np.percentile(lo, 5)),
            'heldout_pushback': [float(np.mean([x[i] for x in rep['pushback']])) for i in range(a.n_dir)],
            'heldout_amplify': [float(np.mean([x[i] for x in rep['amplify']])) for i in range(a.n_dir)], 'directions': []}
    for side, idxs in (('pushback', range(a.n_dir)), ('amplify', [len(ev) - 1 - i for i in range(a.n_dir)])):
        for rank, j in enumerate(idxs):
            u = B.T @ V[:, j]
            u /= np.linalg.norm(u)
            u.astype(np.float32).tofile(f'{out_base}_dirs/L{L}_{side}_{rank}.f32')
            ru, su = R @ u, G @ u
            x = -ru * su
            pm = np.array([x[idx].mean() for idx in groups])
            cap = float(np.sqrt(np.mean(ru ** 2) * np.mean(su ** 2)))
            sc = su.copy()
            for idx in groups:
                sc[idx] -= sc[idx].mean()
            d_end = float(np.mean((n_end - n_end.mean()) * sc)) * push
            d_lp = float(np.mean((logp - logp.mean()) * sc)) * push
            cnt = np.zeros(V_n); cnt2 = np.zeros(V_n)
            w = np.repeat(sc, tok.shape[1]); t = np.clip(tok.ravel(), 0, V_n - 1)
            np.add.at(cnt, t, w)
            np.add.at(cnt2, t, w ** 2)
            dE = cnt / n * push
            z = cnt / np.sqrt(np.maximum(cnt2, 1e-30))
            ok = (cnt2 > 0) & common
            up = [i for i in np.argsort(-z) if ok[i]][:10]
            dn = [i for i in np.argsort(z) if ok[i]][:10]
            rc = sorted(((abs(float(v_ @ u)), nm, float(v_ @ u)) for nm, v_ in {**refs, **known}.items()), reverse=True)[:3]
            say(f'--- L{L} {side} {rank}: kappa {x.mean():+.3f} +- {pm.std(ddof=1) / np.sqrt(len(groups)):.3f}, capacity {cap:.2f}; '
                f'push +u: sentence ends {d_end:+.2f} / 32 (mean {n_end.mean():.2f}), log p {d_lp:+.1f} nats; '
                f'|cos|: ' + ', '.join(f'{nm} {c:+.2f}' for _, nm, c in rc))
            say('    writes more: ' + ' | '.join(f'{piece(i)!r} {dE[i]:+.3f}' for i in up))
            say('    writes less: ' + ' | '.join(f'{piece(i)!r} {dE[i]:+.3f}' for i in dn))
            d = {'side': side, 'rank': rank, 'kappa': float(x.mean()), 'se': float(pm.std(ddof=1) / np.sqrt(len(groups))), 'capacity': cap,
                 'd_sentence_ends': d_end, 'd_logp': d_lp, 'more': [piece(i) for i in up], 'less': [piece(i) for i in dn],
                 'cos': {nm: c for _, nm, c in rc}}
            if J is not None:
                lg = Wu @ (gout * (J @ u))
                pr, sp = np.argsort(-lg)[:10], np.argsort(lg)[:10]
                say('    J-lens promotes: ' + ' | '.join(repr(piece(i)) for i in pr) + '   suppresses: ' + ' | '.join(repr(piece(i)) for i in sp))
                d['jlens_promotes'] = [piece(i) for i in pr]
                d['jlens_suppresses'] = [piece(i) for i in sp]
            if nat is not None and L == 40:
                pj = nat['X'] @ u
                sd = pj.std()
                bins = [0, 1, 2, 4, 8, 16, 41]
                prof = [(pj[(nat['since'] >= bins[i]) & (nat['since'] < bins[i + 1])].mean() - pj.mean()) / sd for i in range(len(bins) - 1)]
                say(f'    natural text: corr since-end {np.corrcoef(pj, np.minimum(nat["since"], 40))[0, 1]:+.2f}, entropy '
                    f'{np.corrcoef(pj, nat["rr"]["entropy"])[0, 1]:+.2f}, |h| {np.corrcoef(pj, nat["norm"])[0, 1]:+.2f}; by tokens since end '
                    f'0/1/2-3/4-7/8-15/16+ (sd): ' + ' '.join(f'{p_:+.2f}' for p_ in prof))
                rr_ = nat['rr']
                for lab, order in (('highest', np.argsort(-pj)), ('lowest', np.argsort(pj))):
                    ex = []
                    for i in order[:400]:
                        s0 = i
                        while s0 > 0 and rr_['seq'][s0 - 1] == rr_['seq'][i] and i - s0 < 14:
                            s0 -= 1
                        ctx = text_of(rr_['token'][s0:i]) + '[[' + text_of([rr_['token'][i]]) + ']]'
                        if all(ctx[-30:] != e_[-30:] for e_ in ex):
                            ex.append(ctx)
                        if len(ex) == 3:
                            break
                    say(f'    {lab} u.h: ' + '  ||  '.join(repr(e_[-60:]) for e_ in ex))
            lrow['directions'].append(d)
    summary.append(lrow)
    open(out_base + '.txt', 'w').write('\n'.join(lines) + '\n')
    json.dump({'prefix': a.prefix, 'basis': a.basis, 'k': K, 'window': a.window, 'layers': summary}, open(out_base + '.json', 'w'), indent=1)
print(f'-> {out_base}.txt')
