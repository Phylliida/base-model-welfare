"""Score-function identification (plan B2): the closed-loop response matrix from homeo-score output.

For a push c*u after block 40 (held over lags 0-31), the response of the readout r = q.R satisfies
    d E[q.R] / dc = E[(q.R - b)(u.G)]
with G the summed gradient of the written tokens' log-likelihood (homeo-score) and b the leave-one-out mean of
q.R over the other continuations of the same prompt (independent of the sample's tokens, so unbiased). So
    M_jk = mean over samples of (q_j.R - b_j)(q_k.G),    kappa(u) = -u' M u
in the same units as homeo-ident's probing matrix (response per unit push, both in state units).

Reports per lag window: the mean-score check (E[q.G] must be 0), the kappa spectrum against a within-prompt
permutation null (G shuffled among continuations of the same prompt), split-half replication over prompts, and
with --probe: the probing matrix refit from homeo-ident output (same basis, same window), kappa along the probing
run's saved directions (PREFIX_dirs/dir_*.f32) with standard errors, spectra side by side, the cosine of the top
eigenvectors, and the loop-capacity bound |kappa(u)| <= sigma_u sqrt(I_F,u) from the model's own samples.

usage: score_fit.py PREFIX [--probe /mnt/models/homeo/ident/main] [--k 32] [--n-perm 200] [--n-split 20]
"""
import argparse
import json
import os

import torch  # noqa: F401  (import before numpy on this box)
import numpy as np

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score_io import ScoreRun  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('prefix')
ap.add_argument('--layer', type=int, default=None, help='default: 40 if captured, else the run\'s first layer')
ap.add_argument('--probe', default='/mnt/models/homeo/ident/main', help='probing run to compare with (layer 40 only)')
ap.add_argument('--basis', default=None, help='f32 [>=K][n_embd], or "self" (within-prompt PCA of this run\'s readout at the '
                'layer); default: the probing run\'s basis at layer 40, else "self"')
ap.add_argument('--k', type=int, default=32)
ap.add_argument('--n-perm', type=int, default=200)
ap.add_argument('--n-split', type=int, default=20)
a = ap.parse_args()

run = ScoreRun(a.prefix)
meta_score = run.meta
layer = a.layer if a.layer is not None else (40 if 40 in run.layers else run.layers[0])
D, G, NW, wins = run.D, run.n_gen, len(run.windows), run.windows
keep = np.flatnonzero(np.isin(run.prompt, run.whole_prompts()))
n = len(keep)
prompt = run.prompt[keep]
prompts = np.unique(prompt)
K = a.k
pmeta = json.load(open(a.probe + '.meta.json')) if (a.probe and layer == 40) else None
basis = a.basis or (pmeta['basis'] if pmeta else 'self')
if pmeta and (basis == 'self' or os.path.realpath(basis) != os.path.realpath(pmeta['basis']) or K != pmeta['k']):
    pmeta = None  # the probing matrix lives in the probing run's own basis (and K): no comparison in any other basis
rng = np.random.default_rng(0)
lines = []


def say(s=''):
    print(s)
    lines.append(s)


def chunks(step=512):
    for c0 in range(0, n, step):
        yield c0, min(n, c0 + step)


if basis == 'self':
    # top-K directions of the within-prompt covariance of the readout (window 13-31 if present, else the last)
    wsel = '13-31' if (13, 31) in wins else '-'.join(map(str, wins[-1]))
    C = np.zeros((D, D))
    for q in prompts:
        idx = keep[prompt == q]
        Rq = run.R(layer, wsel, idx).astype(np.float64)
        Rq -= Rq.mean(0)
        C += Rq.T @ Rq
    ev, V = np.linalg.eigh(C)
    Q = V[:, ::-1][:, :K].T.copy()
    basis_desc = f'self (within-prompt PCA of R at layer {layer}, lags {wsel}; top {K} hold {ev[::-1][:K].sum() / ev.sum():.0%})'
else:
    Q = np.fromfile(basis, dtype=np.float32, count=K * D).reshape(K, D).astype(np.float64)
    basis_desc = basis

# projections on the basis
g = np.zeros((n, K))
r = np.zeros((NW, n, K))
for c0, c1 in chunks():
    g[c0:c1] = run.G(layer, keep[c0:c1]).astype(np.float64) @ Q.T
    for w in range(NW):
        r[w, c0:c1] = run.R(layer, wins[w], keep[c0:c1]).astype(np.float64) @ Q.T
say(f'{a.prefix}: layer {layer}, {n} continuations of {G} tokens over {len(prompts)} prompts; basis {basis_desc} (K {K})')
lp = run.logp[keep].sum(1)
say(f'log p(written) per continuation: mean {lp.mean():.2f}, entropy per token {run.ent[keep].mean():.2f} nats')

# mean-score check: E[q.G] = 0 under the model's own sampling
z = g.mean(0) / (g.std(0) / np.sqrt(n))
say(f'mean score check: |z| max {np.abs(z).max():.2f}, chi2 {np.sum(z ** 2):.1f} on {K} dof (expect ~{K} +- {np.sqrt(2 * K):.0f})')


def loo(x, p):
    """leave-one-out mean of x over the other samples with the same prompt"""
    b = np.empty_like(x)
    for q in np.unique(p):
        m = p == q
        s = x[m].sum(0)
        b[m] = (s[None] - x[m]) / (m.sum() - 1)
    return b


def fit(rw, gg):
    return rw.T @ gg / len(gg)


def sym(M):
    return (M + M.T) / 2


# probing matrix (homeo-ident), same basis and windows
probe_M = {}
if pmeta:
    NP, PG, PK, NPR = pmeta['n_prefix'], pmeta['n_gen'], pmeta['k'], pmeta['n_probe']
    alpha, hn = pmeta['doses'][0], pmeta['resid_norm']
    PREC = np.dtype([('dproj', np.float16, (NP, PG, PK)), ('dnorm', np.float32, (NP, PG)), ('ent', np.float32, (NP, PG)),
                     ('tok', np.int32, (NP, PG)), ('first_div', np.int32, (NP,)), ('endpoint', np.int32, (NP,))])
    precs = np.memmap(a.probe + '.bin', dtype=PREC, mode='r')
    n_pairs = (len(precs) - 1) // 2
    Zp = np.fromfile(a.probe + '.z.f32', dtype=np.float32).reshape(NPR, PK)[:n_pairs].astype(np.float64)
    assert PK == K, 'the probing run must use the same K'
    for (w0, w1) in wins:
        odd = np.zeros((n_pairs, K))
        for c0 in range(0, n_pairs, 256):
            c1 = min(n_pairs, c0 + 256)
            dp = precs['dproj'][1 + 2 * c0:1 + 2 * c1:2].astype(np.float32)
            dm = precs['dproj'][2 + 2 * c0:2 + 2 * c1:2].astype(np.float32)
            o = (dp - dm)[:, :, w0:w1 + 1] / (2 * alpha * hn)
            odd[c0:c1] = np.nanmean(np.nanmean(o, axis=2), axis=1)
        Mt, *_ = np.linalg.lstsq(Zp, odd, rcond=None)
        probe_M[(w0, w1)] = Mt.T
    pdirs = {}
    for name in [f'pushback_{i}' for i in range(4)] + [f'amplify_{i}' for i in range(4)]:
        f = f'{a.probe}_dirs/dir_{name}.f32'
        if os.path.exists(f):
            pdirs[name] = Q @ np.fromfile(f, dtype=np.float32).astype(np.float64)

out = {'n': int(n), 'windows': []}
for w, (w0, w1) in enumerate(wins):
    rw = r[w] - loo(r[w], prompt)
    M = fit(rw, g)
    ev, V = np.linalg.eigh(sym(M))
    kap = -ev                                   # ascending ev -> most pushed back first
    say()
    say(f'=== lags {w0}-{w1}')
    say(f'trace/K (mean kappa of a random direction) {-np.trace(M) / K:+.4f}')
    say(f'kappa spectrum: {" ".join(f"{x:+.3f}" for x in kap[:6])} ... {" ".join(f"{x:+.3f}" for x in kap[-6:])}')
    # permutation null: G shuffled within prompts
    hi, lo = [], []
    for _ in range(a.n_perm):
        gp = g.copy()
        for q in prompts:
            m = np.flatnonzero(prompt == q)
            gp[m] = g[rng.permutation(m)]
        e = np.linalg.eigvalsh(sym(fit(rw, gp)))
        hi.append(-e[0]); lo.append(-e[-1])
    eh, el = np.percentile(hi, 95), np.percentile(lo, 5)
    say(f'permutation null (G shuffled within prompts): top kappa 95% {eh:+.3f}, bottom kappa 5% {el:+.3f}')
    # split halves over prompts
    reps = {'pushback': [], 'amplify': []}
    for _ in range(a.n_split):
        perm = rng.permutation(prompts)
        A = np.isin(prompt, perm[:len(perm) // 2]); B = ~A
        MA = fit(r[w][A] - loo(r[w][A], prompt[A]), g[A]); MB = fit(r[w][B] - loo(r[w][B], prompt[B]), g[B])
        eA, VA = np.linalg.eigh(sym(MA))
        reps['pushback'].append([-(VA[:, i] @ MB @ VA[:, i]) for i in range(3)])
        reps['amplify'].append([-(VA[:, -1 - i] @ MB @ VA[:, -1 - i]) for i in range(3)])
    for side in ('pushback', 'amplify'):
        x = np.array(reps[side])
        say(f'split halves, top-3 {side} directions of half A, kappa on half B: ' +
            ', '.join(f'{x[:, i].mean():+.3f} ({int((np.sign(x[:, i]) == (1 if side == "pushback" else -1)).sum())}/{len(x)})' for i in range(3)))
    wout = {'window': [w0, w1], 'kappa': kap.tolist(), 'null_top95': float(eh), 'null_bottom5': float(el), 'trace_over_k': float(-np.trace(M) / K)}

    if (w0, w1) in probe_M:
        Mp = probe_M[(w0, w1)]
        evp, Vp = np.linalg.eigh(sym(Mp))
        say(f'probing spectrum: {" ".join(f"{x:+.3f}" for x in -evp[:6])} ... {" ".join(f"{x:+.3f}" for x in -evp[-6:])}; trace/K {-np.trace(Mp) / K:+.4f}')
        Sa, Sb = sym(M), sym(Mp)
        say(f'symmetric parts: entry correlation {np.corrcoef(Sa.ravel(), Sb.ravel())[0, 1]:+.3f}; '
            f'top pushed-back eigenvectors cos {abs(V[:, 0] @ Vp[:, 0]):.2f}, top amplified cos {abs(V[:, -1] @ Vp[:, -1]):.2f}')
        if pdirs:
            src = f'offsets file {meta_score["offsets"]}' if meta_score.get('offsets') else f'stream offset {meta_score.get("ids_offset")} + i x {meta_score.get("ids_stride")}'
            say(f'  (score prompts: {src}; the probing main run used stream offset 500000 + i x 100003; SE clustered by prompt)')
            say(f'  {"direction":12s} {"probing":>8s} {"score":>8s} {"+-SE":>6s} {"sigma":>7s} {"sqrtI":>6s} {"bound":>6s}')
            wout['dirs'] = []
            for name, v in pdirs.items():
                v = v / np.linalg.norm(v)
                kp = -(v @ Mp @ v)
                x = -(rw @ v) * (g @ v)                    # per-sample contributions to kappa_score(v)
                pm = np.array([x[prompt == q].mean() for q in prompts])
                ks, se = x.mean(), pm.std(ddof=1) / np.sqrt(len(prompts))  # clustered by prompt
                sg = np.sqrt(np.mean((rw @ v) ** 2)); sI = np.sqrt(np.mean((g @ v) ** 2))
                say(f'  {name:12s} {kp:+8.3f} {ks:+8.3f} {se:6.3f} {sg / hn:7.4f} {sI * hn:6.2f} {sg * sI:6.3f}')
                wout['dirs'].append(dict(name=name, kappa_probe=float(kp), kappa_score=float(ks), se=float(se), bound=float(sg * sI)))
        wout['probe_kappa'] = (-evp).tolist()
    out['windows'].append(wout)

tag = '' if len(run.layers) == 1 else f'.L{layer}'
json.dump(out, open(a.prefix + tag + '.fit.json', 'w'), indent=1)
open(a.prefix + tag + '.fit.txt', 'w').write('\n'.join(lines) + '\n')
print(f'-> {a.prefix}{tag}.fit.txt / .json')
