# Loop-capacity bound check: |kappa(u)| <= sigma_u * sqrt(I_F,u)  (Cauchy-Schwarz on the score-function identity)
#   sigma_u : within-prompt sd of the readout (layer-40 state averaged over written tokens 13-31, |h| units), along u
#   I_F,u   : E[S_u^2], S_u = |h| * sum over a 32-token window of d(log-lik of later tokens)/d h_s . u
# sigma from the plan B main run (diverged arms vs the unpushed arm), I_F from the VL1 gradients (now + fut, fineweb).
import torch  # noqa: F401
import numpy as np, json, glob
P = '/mnt/models/homeo/ident/main'
meta = json.load(open(P + '.meta.json')); NP, G, K, NPR, hn = meta['n_prefix'], meta['n_gen'], meta['k'], meta['n_probe'], meta['resid_norm']
alpha = meta['doses'][0]
REC = np.dtype([('dproj', np.float16, (NP, G, K)), ('dnorm', np.float32, (NP, G)), ('ent', np.float32, (NP, G)),
                ('tok', np.int32, (NP, G)), ('first_div', np.int32, (NP,)), ('endpoint', np.int32, (NP,))])
recs = np.memmap(P + '.bin', dtype=REC, mode='r'); n_pairs = (len(recs) - 1) // 2
Q = np.fromfile(meta['basis'], dtype=np.float32, count=K * 6144).reshape(K, 6144)
Z = np.fromfile(P + '.z.f32', dtype=np.float32).reshape(NPR, K)[:n_pairs].astype(np.float64)

# readout per arm: window mean over lags 13-31, |h| units
R = np.zeros((2 * n_pairs, NP, K), np.float32); FD = np.zeros((2 * n_pairs, NP), np.int32)
for c0 in range(0, 2 * n_pairs, 512):
    c1 = min(2 * n_pairs, c0 + 512)
    R[c0:c1] = np.nanmean(recs['dproj'][1 + c0:1 + c1].astype(np.float32)[:, :, 13:32], axis=2) / hn
    FD[c0:c1] = recs['first_div'][1 + c0:1 + c1]
# within-prompt covariance: early-diverged arms vs the unpushed arm, Var(diff) = 2 Sigma (+ a small push response)
ok = (FD >= 0) & (FD <= 8) & ~np.isnan(R).any(axis=2)
D = R[ok].astype(np.float64)
Sig = D.T @ D / len(D) / 2
print(f'Sigma from {len(D)} early-diverged sequences; sd along basis directions: median {np.median(np.sqrt(np.diag(Sig))):.4f}')

# M (response per unit push, lags 13-31) refit from all pairs, as ident_fit.py
odd = (R[0::2] - R[1::2]) / (2 * alpha)            # [pairs, NP, K]
odd = np.nanmean(odd, axis=1).astype(np.float64)
Mt, *_ = np.linalg.lstsq(Z, odd, rcond=None); M = Mt.T
print(f'trace/K of -M: {-np.trace(M) / K:+.4f} (main run: -0.0262)')

# Fisher in basis coordinates from VL1 gradients
vm = json.load(open('/mnt/models/homeo/value/meta.json')); NL = len(vm['layers']); PP = vm['positions'][1] - vm['positions'][0] + 1
S = []
for f in sorted(glob.glob('/mnt/models/homeo/value/w*.bin')):
    a = np.memmap(f, dtype=np.float16, mode='r', shape=(NL, 3, PP, 6144))
    gp = (a[0, 0].astype(np.float32) + a[0, 2].astype(np.float32)) @ Q.T
    for s0 in range(0, PP - 32, 32):
        S.append(hn * gp[s0:s0 + 32].sum(0))
S = np.array(S, np.float64)
F = S.T @ S / len(S)
print(f'Fisher from {len(S)} windows; mean score along basis directions (should be ~0 for model samples): median |mean|/sd {np.median(np.abs(S.mean(0)) / S.std(0)):.3f}')

def stats(v):
    v = v / np.linalg.norm(v)
    sg, I = np.sqrt(v @ Sig @ v), v @ F @ v
    return -(v @ M @ v), sg, np.sqrt(I), sg * np.sqrt(I)

out = {'dirs': []}
print(f'\n{"direction":12s} {"kappa":>8s} {"sigma":>7s} {"sqrtI":>7s} {"bound":>7s} {"k/bound":>8s}')
for name in [f'pushback_{i}' for i in range(4)] + [f'amplify_{i}' for i in range(4)]:
    u = np.fromfile(f'{P}_dirs/dir_{name}.f32', dtype=np.float32).astype(np.float64)
    v = Q.astype(np.float64) @ u
    k, sg, sI, b = stats(v)
    print(f'{name:12s} {k:+8.3f} {sg:7.4f} {sI:7.2f} {b:7.3f} {k / b:+8.2f}  (|v| in basis {np.linalg.norm(v):.3f})')
    out['dirs'].append(dict(name=name, kappa=k, sigma=sg, sqrtI=sI, bound=b))
rng = np.random.default_rng(0)
rs = np.array([stats(rng.standard_normal(K)) for _ in range(2000)])
print(f'\nrandom directions: median kappa {np.median(rs[:, 0]):+.3f}, median bound {np.median(rs[:, 3]):.3f}, '
      f'median |kappa|/bound {np.median(np.abs(rs[:, 0]) / rs[:, 3]):.2f}, max |kappa|/bound {np.max(np.abs(rs[:, 0]) / rs[:, 3]):.2f}')
# largest bound anywhere in the subspace: maximize log(v'Sig v) + log(v'F v) on the sphere
best = 0
for _ in range(50):
    v = rng.standard_normal(K); v /= np.linalg.norm(v)
    for _ in range(500):
        gr = 2 * Sig @ v / (v @ Sig @ v) + 2 * F @ v / (v @ F @ v)
        v = v + 0.02 * (gr - (gr @ v) * v); v /= np.linalg.norm(v)
    best = max(best, stats(v)[3])
print(f'largest bound in the 32-dim subspace: {best:.3f}; largest |kappa| found: {np.max(np.abs(np.linalg.eigvalsh((M + M.T) / 2))):.3f}')
out.update(random_median_bound=float(np.median(rs[:, 3])), max_bound=float(best))
json.dump(out, open('/mnt/models/homeo/ident/capacity_bound.json', 'w'), indent=1)
