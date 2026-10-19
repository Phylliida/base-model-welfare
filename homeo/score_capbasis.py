"""Capacity basis of the full state space (plan B2 step 3), from homeo-score output.

Loop capacity of a direction u at block 40: c(u) = sqrt(u'Su * u'Fu), with S the within-prompt covariance of the
readout R (lag window --window) and F = E[G G'] the Fisher matrix of the written tokens for a push held over lags
0-31. Cauchy-Schwarz on the score identity gives |kappa(u)| <= c(u): a direction with low capacity cannot be
strongly regulated (or amplified) through writing.

c(u)^2 is a product of two quadratic forms, so no eigendecomposition ranks directions by it. Instead:
  - greedy basis: u_1 = argmax c(u); u_k = argmax c(u) over the complement of u_1 .. u_{k-1} (projected ascent from
    several starts, batched). The capacities fall with k.
  - certificate: for any lam > 0, sqrt(ab) <= (lam a + b / lam) / 2, so every direction orthogonal to u_1 .. u_k has
        c(u) <= min over lam of  lambda_max(P_k (lam S + F / lam) P_k) / 2
    (P_k the projector onto that complement): an eigenvalue bound over the whole remaining space, no search.
Built on half of the prompts (A); capacities and the certificate are also evaluated on the other half (B), which
is honest for the found directions and conservative for the certificate (noise inflates top eigenvalues). The
same is reported for the top-k PCA directions for comparison. With --all, the basis is rebuilt on all samples and
saved for a screen as PREFIX.capbasis.f32 ([n][n_embd] f32, rows orthonormal, highest capacity first).

usage: score_capbasis.py PREFIX [--window 13-31] [--n-basis 256] [--all] [--gpu]
"""
import argparse
import json
import os
import time

import sys

import torch
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score_io import ScoreRun  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('prefix')
ap.add_argument('--window', default='13-31')
ap.add_argument('--layer', type=int, default=None, help='default: 40 if captured, else the run\'s first layer')
ap.add_argument('--n-basis', type=int, default=256)
ap.add_argument('--checkpoints', default='0,8,16,32,64,128,192,256')
ap.add_argument('--pca-basis', default='/mnt/models/homeo/ident/basis_pca256_L40.f32')
ap.add_argument('--steps', type=int, default=200)
ap.add_argument('--all', action='store_true')
ap.add_argument('--gpu', action='store_true')
a = ap.parse_args()
dev = 'cuda' if a.gpu else 'cpu'
torch.set_grad_enabled(False)
torch.manual_seed(0)
t0 = time.time()

run = ScoreRun(a.prefix)
layer = a.layer if a.layer is not None else (40 if 40 in run.layers else run.layers[0])
D = run.D
prompt = run.prompt
prompts = run.whole_prompts()
rng = np.random.default_rng(0)
perm = rng.permutation(prompts)
halves = {'A': np.isin(prompt, perm[:len(perm) // 2]), 'B': np.isin(prompt, perm[len(perm) // 2:])}
if a.all:
    halves['all'] = np.isin(prompt, prompts)
hn = 257.1  # mean |h_40| of the plan B runs, for printing sigma in |h| units


def moments(mask):
    """within-prompt covariance of R and E[G G'] (float64, D x D)"""
    S = torch.zeros(D, D, dtype=torch.float64, device=dev)
    F = torch.zeros(D, D, dtype=torch.float64, device=dev)
    m = 0
    for q in np.unique(prompt[mask]):
        idx = np.flatnonzero((prompt == q) & mask)
        R = torch.from_numpy(run.R(layer, a.window, idx).astype(np.float64)).to(dev)
        Gm = torch.from_numpy(run.G(layer, idx).astype(np.float64)).to(dev)
        R -= R.mean(0, keepdim=True)
        S += R.T @ R * (len(idx) / (len(idx) - 1))
        F += Gm.T @ Gm
        m += len(idx)
    return S / m, F / m


mats = {h: moments(m) for h, m in halves.items()}
print(f'{a.prefix}: layer {layer}, {halves["A"].sum()} / {halves["B"].sum()} samples in halves A / B ({len(prompts)} whole prompts); '
      f'lags {a.window}; moments {time.time() - t0:.0f} s', flush=True)


def cap(u, S, F):
    """capacity of the columns of u (D x m)"""
    u = u / torch.linalg.norm(u, dim=0, keepdim=True)
    return torch.sqrt((u * (S @ u)).sum(0) * (u * (F @ u)).sum(0))


def lam_grid(S, F):
    l0 = float(torch.sqrt(torch.trace(F) / torch.trace(S)))
    return [l0 * s for s in (1 / 16, 1 / 8, 1 / 4, 1 / 2, 1, 2, 4, 8, 16)]


def certificate(S, F, B):
    """max capacity over the complement of the columns of B (orthonormal; None = whole space): AM-GM eigenvalue bound"""
    best = float('inf')
    for lam in lam_grid(S, F):
        A = lam * S + F / lam
        if B is not None and B.shape[1] > 0:
            AB = A @ B
            A = A - B @ AB.T - AB @ B.T + B @ (B.T @ AB) @ B.T
        A = (A + A.T) / 2
        # exact top eigenvalue: an iterative solver's Rayleigh quotient is <= lambda_max, which would not be a bound
        best = min(best, float(torch.linalg.eigvalsh(A)[-1]) / 2)
    return best


def greedy(S, F, n_basis):
    """greedy orthonormal capacity basis (D x n_basis) and the capacity of each direction on S, F"""
    Sf, Ff = S.float(), F.float()
    lams = lam_grid(S, F)
    B = torch.zeros(D, 0, dtype=torch.float32, device=dev)
    caps = []
    for k in range(n_basis):
        def proj(u):
            u = u - B @ (B.T @ u)
            return u / torch.linalg.norm(u, dim=0, keepdim=True)
        # starts: a few power-iteration steps on the complement for each lam, plus random directions
        U = proj(torch.randn(D, len(lams) + 4, device=dev))
        for _ in range(20):
            V = torch.stack([lam * (Sf @ U[:, i]) + (Ff @ U[:, i]) / lam for i, lam in enumerate(lams)], 1)
            U = torch.cat([proj(V), U[:, len(lams):]], 1)
        for _ in range(a.steps):
            SU, FU = Sf @ U, Ff @ U
            su, fu = (U * SU).sum(0), (U * FU).sum(0)
            gr = 2 * SU / su + 2 * FU / fu
            gr = gr - (gr * U).sum(0) * U
            U = proj(U + 0.02 * gr)
        c = cap(U, Sf, Ff)
        u = U[:, int(torch.argmax(c))]
        B = torch.cat([B, proj(u[:, None])], 1)
        caps.append(float(c.max()))
    return B.double(), caps


ks = [int(x) for x in a.checkpoints.split(',') if int(x) <= a.n_basis]
Qp = torch.from_numpy(np.fromfile(a.pca_basis, dtype=np.float32).reshape(-1, D).astype(np.float64)).T.to(dev)  # D x 256

S_A, F_A = mats['A']
S_B, F_B = mats['B']
BA, capA = greedy(S_A, F_A, a.n_basis)
capB = cap(BA, S_B, F_B).cpu().numpy()
print(f'greedy basis on half A: {a.n_basis} directions ({time.time() - t0:.0f} s)', flush=True)
print('capacity spectrum (direction k: on A / held out on B):')
print('  ' + '  '.join(f'{k + 1}: {capA[k]:.2f}/{capB[k]:.2f}' for k in [0, 1, 2, 3, 4, 7, 15, 31, 63, 127, 191, 255] if k < a.n_basis))
print('largest capacity left in the complement (certificate; A = where the basis was built, B = held out):')
print(f'  {"k":>4s}  {"capacity basis A":>16s} {"held out B":>10s}   {"top-k PCA A":>11s} {"held out B":>10s}   {"share of PCA256 in the capacity basis":>10s}')
for k in ks:
    cbA = certificate(S_A, F_A, BA[:, :k] if k else None)
    cbB = certificate(S_B, F_B, BA[:, :k] if k else None)
    if layer == 40 and k <= Qp.shape[1]:  # the PCA basis was fit at layer 40
        cpA = certificate(S_A, F_A, Qp[:, :k] if k else None)
        cpB = certificate(S_B, F_B, Qp[:, :k] if k else None)
    else:
        cpA = cpB = float('nan')
    share = float((Qp.T @ BA[:, :k]).norm() ** 2 / k) if (k and layer == 40) else float('nan')
    print(f'  {k:4d}  {cbA:16.3f} {cbB:10.3f}   {cpA:11.3f} {cpB:10.3f}   {share:10.2f}', flush=True)

tag = '' if len(run.layers) == 1 else f'.L{layer}'
out = {'layer': layer, 'window': a.window, 'n_A': int(halves['A'].sum()), 'n_B': int(halves['B'].sum()), 'cap_A': capA, 'cap_B': capB.tolist()}
if a.all:
    S, F = mats['all']
    Ball, cap_all = greedy(S, F, a.n_basis)
    Ball.T.contiguous().cpu().numpy().astype(np.float32).tofile(a.prefix + tag + '.capbasis.f32')
    out['cap_all'] = cap_all
    print(f'basis on all samples -> {a.prefix}{tag}.capbasis.f32; spectrum ' + ' '.join(f'{c:.2f}' for c in cap_all[:8]) + ' ...')
json.dump(out, open(a.prefix + tag + '.capbasis.json', 'w'), indent=1)
print(f'done ({time.time() - t0:.0f} s)')
