"""Layer sweep (plan B2): the score-function response matrix at every captured layer of a homeo-score --layers run.

Per layer L (push after block L over lags 0-31, readout = block-L output averaged over --window):
  - basis: the top-K directions of the within-prompt covariance of the readout at L (what writing moves most there);
  - M = mean[(Q R - b)(Q G)^T] with b the leave-one-out mean over the continuations of the same prompt;
    kappa spectrum (most pushed back / most amplified), mean kappa of a random direction in the basis (-tr M / K)
    and in the whole space (-mean(r~ . G) / n_embd);
  - within-prompt permutation null of the extreme eigenvalues; split halves over prompts (top directions of half A
    measured on half B);
  - mean-score check (E[Q G] = 0);
  - fixed directions: kappa_L of the probing run's layer-40 directions (PREFIX_dirs/dir_*.f32), pushed and read at L
    (the residual stream shares one coordinate system across layers), with SE clustered by prompt, and their
    capacity sigma_u sqrt(I_F,u) at L.
Writes PREFIX.sweep.json and PREFIX.sweep.txt.

usage: score_sweep.py PREFIX [--window 13-31] [--k 32] [--n-perm 100] [--n-split 10] [--layers 0-60]
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
ap.add_argument('--window', default='13-31')
ap.add_argument('--k', type=int, default=32)
ap.add_argument('--n-perm', type=int, default=100)
ap.add_argument('--n-split', type=int, default=10)
ap.add_argument('--layers', default=None, help='e.g. 0-60 or 20,40; default: all captured')
ap.add_argument('--dirs', default='/mnt/models/homeo/ident/main_dirs')
a = ap.parse_args()
torch.set_grad_enabled(False)
torch.manual_seed(0)
rng = np.random.default_rng(0)

run = ScoreRun(a.prefix)
keep = np.flatnonzero(np.isin(run.prompt, run.whole_prompts()))
prompt = run.prompt[keep]
prompts = np.unique(prompt)
n, D, K = len(keep), run.D, a.k
if a.layers:
    want = []
    for t in a.layers.split(','):
        l0, _, l1 = t.partition('-')
        want += list(range(int(l0), int(l1 or l0) + 1))
    layers = [L for L in run.layers if L in want]
else:
    layers = run.layers
dir_names = [f'pushback_{i}' for i in range(4)] + [f'amplify_{i}' for i in range(4)]
U = {nm: np.fromfile(f'{a.dirs}/dir_{nm}.f32', dtype=np.float32).astype(np.float64) for nm in dir_names
     if os.path.exists(f'{a.dirs}/dir_{nm}.f32')}
groups = [np.flatnonzero(prompt == q) for q in prompts]


def loo(x):
    out = np.empty_like(x)
    for idx in groups:
        s = x[idx].sum(0)
        out[idx] = x[idx] - (s[None] - x[idx]) / (len(idx) - 1)
    return out


def fit(rr, gg):
    return rr.T @ gg / len(gg)


def sym(M):
    return (M + M.T) / 2


lines = []


def say(s=''):
    print(s, flush=True)
    lines.append(s)


say(f'{a.prefix}: {n} continuations, {len(prompts)} prompts, layers {layers[0]}..{layers[-1]}; window {a.window}; '
    f'basis = top-{K} within-prompt PCA of the readout at each layer')
say(f'{"L":>3s} {"kap1":>6s} {"kap2":>6s} {"kapK":>7s} {"kapK-1":>7s} {"null+":>6s} {"null-":>6s} {"rep+":>6s} {"rep-":>6s} '
    f'{"rnd(K)":>7s} {"rnd(D)":>8s} {"chi2":>5s}   ' + ' '.join(f'{nm[:2]}{nm[-1]:>1s}' + ' ' * 4 for nm in U))
out = []
t0 = time.time()
for L in layers:
    G = run.G(L, keep).astype(np.float64)
    R = loo(run.R(L, a.window, keep).astype(np.float64))      # readout minus the leave-one-out prompt mean
    # basis: top-K right singular vectors of the within-prompt-centered readout
    Rc = R.copy()
    for idx in groups:
        Rc[idx] -= Rc[idx].mean(0)
    _, sv, Vt = torch.linalg.svd(torch.from_numpy(Rc).float(), full_matrices=False)
    Q = Vt[:K].double().numpy()
    var_share = float((sv[:K] ** 2).sum() / (sv ** 2).sum())
    g, r = G @ Q.T, R @ Q.T
    M = fit(r, g)
    ev, V = np.linalg.eigh(sym(M))
    kap = -ev
    hi, lo = [], []
    for _ in range(a.n_perm):
        gp = g.copy()
        for idx in groups:
            gp[idx] = g[rng.permutation(idx)]
        e = np.linalg.eigvalsh(sym(fit(r, gp)))
        hi.append(-e[0]); lo.append(-e[-1])
    rep_p, rep_m = [], []
    for _ in range(a.n_split):
        perm = rng.permutation(len(prompts))
        A = np.isin(prompt, prompts[perm[:len(prompts) // 2]]); B = ~A
        eA, VA = np.linalg.eigh(sym(fit(r[A], g[A])))
        MB = fit(r[B], g[B])
        rep_p.append(-(VA[:, 0] @ MB @ VA[:, 0])); rep_m.append(-(VA[:, -1] @ MB @ VA[:, -1]))
    z = g.mean(0) / (g.std(0) / np.sqrt(n))
    rnd_full = -float(np.mean(np.einsum('ij,ij->i', R, G))) / D
    fixed = {}
    for nm, u in U.items():
        x = -(R @ u) * (G @ u)
        pm = np.array([x[idx].mean() for idx in groups])
        cap = float(np.sqrt(np.mean((R @ u) ** 2) * np.mean((G @ u) ** 2)))
        fixed[nm] = dict(kappa=float(x.mean()), se=float(pm.std(ddof=1) / np.sqrt(len(prompts))), capacity=cap)
    row = dict(layer=L, kappa=kap.tolist(), null_top95=float(np.percentile(hi, 95)), null_bottom5=float(np.percentile(lo, 5)),
               rep_top=float(np.mean(rep_p)), rep_top_same_sign=int(np.sum(np.array(rep_p) > 0)),
               rep_bottom=float(np.mean(rep_m)), rep_bottom_same_sign=int(np.sum(np.array(rep_m) < 0)),
               random_basis=float(-np.trace(M) / K), random_full=rnd_full, chi2=float(np.sum(z ** 2)),
               basis_var_share=var_share, fixed=fixed, top_vec=V[:, 0].tolist(), bottom_vec=V[:, -1].tolist())
    out.append(row)
    say(f'{L:3d} {kap[0]:+6.3f} {kap[1]:+6.3f} {kap[-1]:+7.3f} {kap[-2]:+7.3f} {row["null_top95"]:+6.3f} {row["null_bottom5"]:+6.3f} '
        f'{row["rep_top"]:+6.3f} {row["rep_bottom"]:+6.3f} {row["random_basis"]:+7.4f} {rnd_full:+8.5f} {row["chi2"]:5.1f}   ' +
        ' '.join(f'{f["kappa"]:+.3f}' for f in fixed.values()) + f'   ({time.time() - t0:.0f} s)')
    json.dump({'layers': out, 'window': a.window, 'k': K, 'n': n, 'n_prompts': len(prompts), 'dirs': list(U)},
              open(a.prefix + '.sweep.json', 'w'))
say('columns: kap1/kap2 = most pushed back, kapK/kapK-1 = most amplified; null = 95% edges (G shuffled within prompts); '
    'rep = split-half replication of the top/bottom direction (mean held-out kappa); rnd(K) / rnd(D) = mean kappa of a '
    'random direction in the basis / whole space; chi2 = mean-score check on K dof; then kappa_L of the layer-40 '
    'probing directions (pb = pushed back, am = amplified)')
open(a.prefix + '.sweep.txt', 'w').write('\n'.join(lines) + '\n')
