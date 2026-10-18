"""Describe the most pushed-back and most amplified directions of a plan B run (homeo-ident output).

For a lag window: fit M (response ~ M z, as ident_fit.py) on all probe pairs, take the eigenvectors of its
symmetric part with the most positive kappa = -eigenvalue (pushed back) and the most negative (amplified), and
for each report:
  - kappa, the permutation-null edge, and split-half replication (directions from one half of the prefixes,
    kappa on the other half, over several random splits)
  - kappa per lag window (how the push-back builds up)
  - loadings on the PCA basis, cosines with known layer-40 vectors (temperature and p0.25 steering vectors, the
    VL2 readout directions)
  - J-lens readability |J u| relative to random directions in the same subspace, and the tokens J u promotes and
    suppresses through the unembedding (linearized: final norm weight, no rms rescale)
  - example generations: the + and - arms of the probe most aligned with the direction, next to the unsteered text
Each direction is saved as raw f32 [n_embd] (unit norm) for follow-up steering: OUTDIR/dir_{pushback,amplify}_i.f32

usage: ident_describe.py PREFIX [--window 13-31] [--n-dir 4] [--dose 0.25] [--outdir DIR] [--no-jlens]
"""
import argparse
import json
import os
import sys

import torch  # noqa: F401  (import before numpy on this box)
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('prefix')
ap.add_argument('--window', default='13-31')
ap.add_argument('--n-dir', type=int, default=4)
ap.add_argument('--dose', type=float, default=None)
ap.add_argument('--outdir', default=None)
ap.add_argument('--n-perm', type=int, default=200)
ap.add_argument('--n-split', type=int, default=20)
ap.add_argument('--no-jlens', action='store_true')
ap.add_argument('--jlens', default='/mnt/models/jlens/jlens_glm4_q4k.jlns')
ap.add_argument('--model', default='/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf')
a = ap.parse_args()
outdir = a.outdir or a.prefix + '_dirs'
os.makedirs(outdir, exist_ok=True)

meta = json.load(open(a.prefix + '.meta.json'))
NP, G, K, P, L = meta['n_prefix'], meta['n_gen'], meta['k'], meta['n_probe'], meta['layer']
doses, hn = meta['doses'], meta['resid_norm']
di = 0 if a.dose is None else min(range(len(doses)), key=lambda i: abs(doses[i] - a.dose))
dose = doses[di]
D = 6144
Q = np.fromfile(meta['basis'], dtype=np.float32, count=K * D).reshape(K, D)
Z = np.fromfile(a.prefix + '.z.f32', dtype=np.float32).reshape(P, K)
REC = np.dtype([('dproj', np.float16, (NP, G, K)), ('dnorm', np.float32, (NP, G)), ('ent', np.float32, (NP, G)),
                ('tok', np.int32, (NP, G)), ('first_div', np.int32, (NP,)), ('endpoint', np.int32, (NP,))])
recs = np.memmap(a.prefix + '.bin', dtype=REC, mode='r')
lo = 1 + di * P * 2
n_pairs = max(0, min(P, (len(recs) - lo) // 2))
assert n_pairs > K, f'need more probe pairs than K ({n_pairs} <= {K})'
w0, w1 = (int(x) for x in a.window.split('-'))
rng = np.random.default_rng(0)
lines = []


def say(s=''):
    print(s)
    lines.append(s)


def odd_window(w0, w1, prefixes=None):
    """[n_pairs, K] response per unit push, averaged over lags w0..w1 and the given prefixes"""
    out = np.zeros((n_pairs, K), np.float64)
    for c0 in range(0, n_pairs, 256):
        c1 = min(n_pairs, c0 + 256)
        dp = recs['dproj'][lo + 2 * c0:lo + 2 * c1:2].astype(np.float32)
        dm = recs['dproj'][lo + 2 * c0 + 1:lo + 2 * c1:2].astype(np.float32)
        o = (dp - dm)[:, :, w0:w1 + 1] / (2 * dose * hn)
        if prefixes is not None:
            o = o[:, prefixes]
        out[c0:c1] = np.nanmean(np.nanmean(o, axis=2), axis=1)
    return out


def fit_M(R, Zp):
    Mt, *_ = np.linalg.lstsq(Zp, R, rcond=None)
    return Mt.T


def sym(M):
    return (M + M.T) / 2


Zp = Z[:n_pairs].astype(np.float64)
R = odd_window(w0, w1)
M = fit_M(R, Zp)
w, V = np.linalg.eigh(sym(M))      # ascending: most pushed back (kappa = -w largest) first
kap = -w
nul_hi, nul_lo = [], []
for _ in range(a.n_perm):
    wn = np.linalg.eigvalsh(sym(fit_M(R, Zp[rng.permutation(n_pairs)])))
    nul_hi.append(-wn[0]); nul_lo.append(-wn[-1])
edge_hi, edge_lo = np.percentile(nul_hi, 95), np.percentile(nul_lo, 5)
say(f'{a.prefix}: layer {L}, K {K}, dose {dose} ({dose * hn:.1f}), {n_pairs} probe pairs, {NP} prefixes; window lags {w0}-{w1}')
say(f'trace/K (mean kappa of a random direction) {-np.trace(M) / K:+.4f}')
say(f'kappa spectrum (pushed back first): {" ".join(f"{x:+.3f}" for x in kap[:8])} ... {" ".join(f"{x:+.3f}" for x in kap[-4:])}')
say(f'permutation null: top kappa 95% {edge_hi:+.3f}, bottom kappa 5% {edge_lo:+.3f}')

# split-half replication over several random splits
def split_rep(idx_from_top, sign):
    vals = []
    for _ in range(a.n_split):
        perm = rng.permutation(NP)
        A, B = perm[:NP // 2], perm[NP // 2:]
        MA, MB = fit_M(odd_window(w0, w1, A), Zp), fit_M(odd_window(w0, w1, B), Zp)
        wA, VA = np.linalg.eigh(sym(MA))
        v = VA[:, idx_from_top] if sign > 0 else VA[:, -1 - idx_from_top]
        vals.append(-(v @ MB @ v))
    return np.array(vals)

# known vectors at this layer
known = {}
def add_known(name, path, row=None, n=None):
    try:
        x = np.fromfile(path, dtype=np.float32)
        if row is not None:
            x = x[row * D:(row + 1) * D]
        if x.size != D:
            return
        known[name] = x / np.linalg.norm(x)
    except OSError:
        pass
add_known('temperature (s2opt temp1.3 L40)', '/mnt/models/homeo/s2opt/vec_temp1.3_opt2_L40.f32')
add_known('p0.25 band (s2opt L40)', '/mnt/models/homeo/s2opt/vec_p0.25_opt2_L40.f32')
for i, nm in enumerate(['stakes', 'now', 'next8', 'next32']):
    add_known(f'VL2 readout {nm}', '/mnt/models/homeo/value_probe/readout_L40.f32', row=i)
try:
    mh = np.load('/mnt/models/homeo/value_probe/mean_h_L40.npy').astype(np.float32).ravel()
    if mh.size == D:
        known['mean state'] = mh / np.linalg.norm(mh)
except OSError:
    pass

# J-lens matrix at this layer and the unembedding, for readability and decoding
J = Wu = gout = None
sys.path.insert(0, '/home/bepis/prog/llm-tests/llama.cpp/gguf-py')
import gguf  # noqa: E402
rd = gguf.GGUFReader(a.model)
fld = rd.fields['tokenizer.ggml.tokens']
vocab = [bytes(fld.parts[i]).decode('utf-8', 'replace') for i in fld.data]
if not a.no_jlens:
    with open(a.jlens, 'rb') as f:
        hdr = np.frombuffer(f.read(16), dtype=np.uint32)
        n_probes, n_pos = np.frombuffer(f.read(16), dtype=np.uint64)
        n_embd = int(hdr[2])
        f.seek(32 + L * n_embd * n_embd * 4)
        # stored with J[i, j] at i + j * n_embd: reading row-major gives A[j, i] = J[i, j]
        J = np.frombuffer(f.read(n_embd * n_embd * 4), dtype=np.float32).reshape(n_embd, n_embd).T / float(n_pos)
    tens = {t.name: t for t in rd.tensors}
    t = tens['output.weight']
    Wu = gguf.quants.dequantize(t.data, t.tensor_type).reshape(-1, D).astype(np.float32)
    t = tens['output_norm.weight']
    gout = np.asarray(gguf.quants.dequantize(t.data, t.tensor_type), np.float32).ravel()
    rnd = Q.T @ rng.standard_normal((K, 256))
    rnd /= np.linalg.norm(rnd, axis=0)
    jr = np.linalg.norm(J @ rnd, axis=0).mean()
    say(f'J-lens readability of random directions in the subspace: mean |J u| {jr:.3f}')

def _byte_decoder():
    # inverse of the GPT-2 byte -> unicode map used by byte-level BPE vocabularies
    bs = list(range(ord('!'), ord('~') + 1)) + list(range(0xA1, 0xAD)) + list(range(0xAE, 0x100))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return {chr(c): b for b, c in zip(bs, cs)}


BYTE_DEC = _byte_decoder()


def tok_bytes(i):
    s = vocab[i] if vocab else str(i)
    return bytes(BYTE_DEC.get(ch, ord('?')) for ch in s)


def piece(i):
    return tok_bytes(i).decode('utf-8', 'replace')


def text_of(toks):
    return b''.join(tok_bytes(t) for t in toks if t >= 0).decode('utf-8', 'replace')

# kappa per lag window for a direction v (basis coords)
lag_wins = [(1, 2), (3, 4), (5, 8), (9, 12), (13, 20), (21, 31)]
lag_M = {lw: fit_M(odd_window(*lw), Zp) for lw in lag_wins if lw[0] < G}

base = recs[0]
summary = {'n_pairs': int(n_pairs), 'window': a.window, 'kappa': kap.tolist(), 'null_top95': float(edge_hi),
           'null_bottom5': float(edge_lo), 'trace_over_k': float(-np.trace(M) / K), 'directions': []}
for sign, label in ((1, 'pushback'), (-1, 'amplify')):
    say()
    say(f'===== most {"pushed back" if sign > 0 else "amplified"} directions')
    for i in range(a.n_dir):
        v = V[:, i] if sign > 0 else V[:, -1 - i]
        k_i = -(v @ M @ v)
        rep = split_rep(i, sign)
        u = (Q.T @ v).astype(np.float32)
        u /= np.linalg.norm(u)
        u.tofile(f'{outdir}/dir_{label}_{i}.f32')
        say()
        say(f'--- {label} {i}: kappa {k_i:+.3f}; split-half kappa on held-out half {rep.mean():+.3f} '
            f'(median {np.median(rep):+.3f}, {int((np.sign(rep) == np.sign(k_i)).sum())}/{len(rep)} same sign)')
        say('    kappa by lag: ' + ', '.join(f'{lw[0]}-{lw[1]}: {-(v @ Mw @ v):+.3f}' for lw, Mw in lag_M.items()))
        top = np.argsort(-np.abs(v))[:5]
        say('    PCA loadings: ' + ', '.join(f'PC{j + 1} {v[j]:+.2f}' for j in top))
        if known:
            say('    cosines: ' + ', '.join(f'{nm} {float(u @ x):+.3f}' for nm, x in known.items()))
        d = {'label': label, 'index': i, 'kappa': float(k_i), 'split_half_mean': float(rep.mean()),
             'split_half_same_sign': int((np.sign(rep) == np.sign(k_i)).sum()), 'pca_loadings': v.tolist()}
        if J is not None:
            y = J @ u
            say(f'    J-lens readability |J u| {np.linalg.norm(y):.3f} ({np.linalg.norm(y) / jr:.2f} x random)')
            lg = Wu @ (gout * y)
            up, dn = np.argsort(-lg)[:12], np.argsort(lg)[:12]
            say('    promotes:  ' + ' | '.join(repr(piece(j)) for j in up))
            say('    suppresses: ' + ' | '.join(repr(piece(j)) for j in dn))
            d['readability_x_random'] = float(np.linalg.norm(y) / jr)
        # example: the probe most aligned with v, its + and - arms next to the unsteered text
        p = int(np.argmax(np.abs(Zp @ v)))
        sgn = '+' if (Zp[p] @ v) > 0 else '-'
        rp, rm = recs[lo + 2 * p], recs[lo + 2 * p + 1]
        # the prefix where the two arms' states differ most along v over the window
        dv = (rp['dproj'].astype(np.float32) - rm['dproj'].astype(np.float32))[:, w0:w1 + 1] @ v
        pre = int(np.nanargmax(np.abs(np.nanmean(dv, axis=1))))
        say(f'    example (probe {p}, cos {abs(Zp[p] @ v):.2f}, "+" arm pushes {sgn}v, prefix {pre}):')
        say(f'      unsteered: {text_of(base["tok"][pre])!r}')
        say(f'      + arm:     {text_of(rp["tok"][pre])!r}')
        say(f'      - arm:     {text_of(rm["tok"][pre])!r}')
        summary['directions'].append(d)

open(f'{outdir}/describe_{a.window}.txt', 'w').write('\n'.join(lines) + '\n')
json.dump(summary, open(f'{outdir}/describe_{a.window}.json', 'w'), indent=1)
print(f'-> {outdir}/describe_{a.window}.txt')
