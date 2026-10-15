#!/usr/bin/env python3
"""S1 surprise probe (NOTES-homeostasis.md): is "the previous token was unlikely"
linearly decodable from the residual stream, and how unlikely?

Reads homeo-capture output. Ridge probes per layer with doc-grouped K-fold CV
(lambda chosen on an inner validation fold). Feature standardization uses train
stats. All probes share one eigendecomposition per (layer, fold).

Sets:
  forced   kind 1+2: one token per log10-p bin at a shared prefix (branch path)
  natural  kind 0: rollout tokens (min_p 0.05 rollouts, so a thin surprisal tail)

usage: s1_probe.py DATA_DIR [--rollouts data/rollouts.jsonl] [--model GGUF]
                   [--folds 5] [--out DATA_DIR/s1_results.json]
"""
import torch  # import before numpy: numpy's libz/libstdc++ come from torch's libs on this box
import argparse
import json
import sys
import time

import numpy as np

LABEL = np.dtype([('seq', 'i4'), ('pos', 'i4'), ('token', 'i4'), ('rank', 'i4'),
                  ('s', 'f4'), ('Hp', 'f4'), ('H', 'f4'), ('pad', 'f4')])
SAMPLE = np.dtype([('seq', 'i4'), ('pos', 'i4'), ('token', 'i4'), ('kind', 'i4'), ('bin', 'i4'),
                   ('rank', 'i4'), ('s', 'f4'), ('Hp', 'f4'), ('H', 'f4'), ('pad', '3f4')])
LAMS = [1e0, 1e1, 1e2, 1e3, 1e4, 1e5]
DEV = 'cuda' if torch.cuda.is_available() else 'cpu'


def load(data_dir):
    meta = json.load(open(f'{data_dir}/meta.json'))
    labels = np.fromfile(f'{data_dir}/labels.bin', dtype=LABEL)
    samples = np.fromfile(f'{data_dir}/samples.bin', dtype=SAMPLE)
    assert len(samples) == meta['n_samples']
    return meta, labels, samples


def acts(data_dir, meta, il):
    return np.memmap(f'{data_dir}/acts_L{il:02d}.f16', dtype=np.float16, mode='r').reshape(-1, meta['n_embd'])


class RidgeCV:
    """Doc-grouped K-fold ridge over standardized features, many targets at once."""

    def __init__(self, X, fold, n_folds):
        self.X, self.fold, self.K = X, fold, n_folds  # X: torch f16 on DEV
        self.cache = {}

    def _fit_basis(self, mask):
        key = mask.tobytes()
        if key in self.cache:
            return self.cache[key]
        idx = torch.from_numpy(np.nonzero(mask)[0]).to(DEV)
        D = self.X.shape[1]
        s1 = torch.zeros(D, dtype=torch.float64, device=DEV)
        G = torch.zeros(D, D, dtype=torch.float32, device=DEV)
        for c in idx.split(16384):
            s1 += self.X[c].double().sum(0)
        mu = (s1 / len(idx)).float()
        s2 = torch.zeros(D, dtype=torch.float64, device=DEV)
        for c in idx.split(16384):
            xc = self.X[c].float() - mu
            s2 += (xc.double() ** 2).sum(0)
        sd = (s2 / len(idx)).sqrt().float().clamp_min(1e-6)
        for c in idx.split(16384):
            xs = (self.X[c].float() - mu) / sd
            G += xs.T @ xs
        e, V = torch.linalg.eigh(G)
        out = (idx, mu, sd, e.clamp_min(0), V)
        self.cache = {key: out}  # keep only the latest basis (GPU memory)
        return out

    def _weights(self, basis, Y):
        idx, mu, sd, e, V = basis
        ym = Y[idx].mean(0)
        b = torch.zeros(self.X.shape[1], Y.shape[1], dtype=torch.float32, device=DEV)
        for c in idx.split(16384):
            b += ((self.X[c].float() - mu) / sd).T @ (Y[c] - ym)
        Vb = V.T @ b
        return ym, [(V @ (Vb / (e[:, None] + lam))) for lam in LAMS]

    def _predict(self, basis, rows, ym, W):
        _, mu, sd, _, _ = basis
        out = []
        for c in torch.from_numpy(rows).to(DEV).split(16384):
            out.append(((self.X[c].float() - mu) / sd) @ W + ym)
        return torch.cat(out)

    def run(self, Y, use):
        """Y: [N, T] float32 torch on DEV. use: bool mask of rows in this experiment.
        Returns out-of-fold predictions [N, T] (nan outside use) and chosen lambdas."""
        N, T = Y.shape
        pred = torch.full((N, T), float('nan'), device=DEV)
        lam_pick = []
        for f in range(self.K):
            v = (f + 1) % self.K
            tr_in = use & (self.fold != f) & (self.fold != v)
            va = use & (self.fold == v)
            basis = self._fit_basis(tr_in)
            ym, Ws = self._weights(basis, Y)
            vrows = np.nonzero(va)[0]
            yv = Y[torch.from_numpy(vrows).to(DEV)]
            sse = torch.stack([((self._predict(basis, vrows, ym, W) - yv) ** 2).sum(0) for W in Ws])  # [L, T]
            best = sse.argmin(0)  # per target
            lam_pick.append([LAMS[i] for i in best.tolist()])
            tr = use & (self.fold != f)
            basis = self._fit_basis(tr)
            ym, Ws = self._weights(basis, Y)
            W = torch.stack([Ws[best[t]][:, t] for t in range(T)], 1)
            te = np.nonzero(use & (self.fold == f))[0]
            pred[torch.from_numpy(te).to(DEV)] = self._predict(basis, te, ym, W)
        return pred, lam_pick

    def fit_all(self, Y, use, lams):
        """Final fit on all `use` rows with one lambda per target; returns mu, sd, W_std."""
        basis = self._fit_basis(use)
        idx, mu, sd, e, V = basis
        ym = Y[idx].mean(0)
        b = torch.zeros(self.X.shape[1], Y.shape[1], dtype=torch.float32, device=DEV)
        for c in idx.split(16384):
            b += ((self.X[c].float() - mu) / sd).T @ (Y[c] - ym)
        Vb = V.T @ b
        W = torch.stack([V @ (Vb[:, t] / (e + lams[t])) for t in range(Y.shape[1])], 1)
        return mu, sd, W, ym


def r2(y, p):
    ok = np.isfinite(y) & np.isfinite(p)
    y, p = y[ok], p[ok]
    return float(1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum())


def corr(a, b):
    ok = np.isfinite(a) & np.isfinite(b)
    return float(np.corrcoef(a[ok], b[ok])[0, 1])


def within_group_r(y, p, g):
    """correlation after removing per-group means (groups with >= 2 members)"""
    ok = np.isfinite(y) & np.isfinite(p)
    y, p, g = y[ok], p[ok], g[ok]
    _, inv, cnt = np.unique(g, return_inverse=True, return_counts=True)
    keep = cnt[inv] >= 2
    y, p, inv = y[keep], p[keep], inv[keep]
    ym = np.bincount(inv, y) / np.bincount(inv)
    pm = np.bincount(inv, p) / np.bincount(inv)
    return corr(y - ym[inv], p - pm[inv])


def embed_rows(model_path, tokens):
    sys.path.insert(0, 'llama.cpp/gguf-py')
    import gguf
    from gguf.quants import dequantize
    r = gguf.GGUFReader(model_path)
    t = next(t for t in r.tensors if t.name == 'token_embd.weight')
    uniq, inv = np.unique(tokens, return_inverse=True)
    E = dequantize(t.data[uniq], t.tensor_type).astype(np.float16)
    return E[inv]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('data')
    ap.add_argument('--rollouts', default='data/rollouts.jsonl')
    ap.add_argument('--model', default='/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf')
    ap.add_argument('--folds', type=int, default=5)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--layers', default='')
    ap.add_argument('--lags', default='0,1,2,3,4,6,8,12,16,24,32')
    ap.add_argument('--out', default='')
    args = ap.parse_args()
    out_path = args.out or f'{args.data}/s1_results.json'

    meta, labels, S = load(args.data)
    layers = [int(x) for x in args.layers.split(',')] if args.layers else meta['layers']
    doc = np.array([json.loads(l)['doc_idx'] for l in open(args.rollouts)])[S['seq']]
    rng = np.random.default_rng(args.seed)
    udoc = np.unique(doc)
    doc_fold = dict(zip(udoc, rng.permutation(len(udoc)) % args.folds))
    fold = np.array([doc_fold[d] for d in doc])

    forced = S['kind'] >= 1
    natural = S['kind'] == 0
    ctx_id = S['seq'].astype(np.int64) * 100000 + S['pos']  # forced context id

    # lagged labels for the natural memory curve
    lags = [int(x) for x in args.lags.split(',')]
    key = labels['seq'].astype(np.int64) * 100000 + labels['pos']
    order = np.argsort(key)
    def lagged(field, k):
        q = S['seq'].astype(np.int64) * 100000 + (S['pos'] - k)
        pos = np.searchsorted(key[order], q)
        pos = np.clip(pos, 0, len(order) - 1)
        hit = key[order][pos] == q
        out = np.full(len(S), np.nan, dtype=np.float32)
        out[hit] = labels[field][order][pos[hit]]
        return out

    exc = S['s'] - S['Hp']
    targets = {
        's': S['s'], 'Hp': S['Hp'], 'exc': exc, 'H': S['H'],
        'logrank': np.log1p(S['rank'].astype(np.float32)),
    }
    for k in lags:
        if k > 0:
            targets[f's_lag{k}'] = lagged('s', k)
    tnames = list(targets)
    Ynp = np.stack([targets[t] for t in tnames], 1).astype(np.float32)
    Ynp_f = np.nan_to_num(Ynp, nan=0.0)  # fills are excluded via per-target masks below
    Y = torch.from_numpy(Ynp_f).to(DEV)
    finite = np.isfinite(Ynp)

    res = {'layers': layers, 'n_forced': int(forced.sum()), 'n_natural': int(natural.sum()),
           'targets': tnames, 'by_layer': {}}
    print(f'samples: forced {forced.sum()} natural {natural.sum()}  docs {len(udoc)}  folds {args.folds}  dev {DEV}')

    def experiments(X_np, tag):
        X = torch.from_numpy(np.ascontiguousarray(X_np)).to(DEV)
        cv = RidgeCV(X, fold, args.folds)
        out = {}
        for set_name, use in (('forced', forced), ('natural', natural)):
            tsel = [t for t in tnames if set_name == 'natural' or not t.startswith('s_lag')]
            cols = [tnames.index(t) for t in tsel]
            use_all = use & finite[:, cols].all(1)
            pred, lam = cv.run(Y[:, cols], use_all)
            pred = pred.cpu().numpy()
            o = {}
            for j, t in enumerate(tsel):
                y = Ynp[:, cols[j]]
                m = use_all
                o[t] = {'r2': r2(y[m], pred[m, j]), 'r': corr(y[m], pred[m, j])}
            js = tsel.index('s')
            if set_name == 'forced':
                o['s']['within_ctx_r'] = within_group_r(S['s'][use_all], pred[use_all, js], ctx_id[use_all])
                o['exc']['within_ctx_r'] = within_group_r(exc[use_all], pred[use_all, tsel.index('exc')], ctx_id[use_all])
                o['s']['bin_mean_pred'] = [float(np.nanmean(pred[use_all & (S['bin'] == b), js])) if (use_all & (S['bin'] == b)).any() else None for b in range(12)]
            else:
                o['s']['within_token_r'] = within_group_r(S['s'][use_all], pred[use_all, js], S['token'][use_all])
                o['exc']['within_token_r'] = within_group_r(exc[use_all], pred[use_all, tsel.index('exc')], S['token'][use_all])
            o['lambdas'] = lam
            out[set_name] = o
        # transfer: forced-trained s probe applied to natural rows and vice versa
        js = tnames.index('s')
        for src, dst, nm in ((forced, natural, 'forced->natural'), (natural, forced, 'natural->forced')):
            lam = out['forced' if src is forced else 'natural']['lambdas']
            lam_s = float(np.median([l[0] for l in lam]))
            mu, sd, W, ym = cv.fit_all(Y[:, [js]], src, [lam_s])
            rows = np.nonzero(dst)[0]
            p = torch.cat([((X[torch.from_numpy(c).to(DEV)].float() - mu) / sd) @ W + ym
                           for c in np.array_split(rows, max(1, len(rows) // 16384))]).cpu().numpy()[:, 0]
            out[nm] = {'r2': r2(S['s'][rows], p), 'r': corr(S['s'][rows], p)}
        del X, cv
        torch.cuda.empty_cache()
        return out

    t0 = time.time()
    # token-identity baseline: raw (dequantized) input embedding of the token
    print('embedding baseline...', flush=True)
    res['embedding'] = experiments(embed_rows(args.model, S['token']), 'emb')

    probe_dirs = {}
    for il in layers:
        print(f'layer {il} ({time.time() - t0:.0f}s)...', flush=True)
        X_np = np.asarray(acts(args.data, meta, il))
        res['by_layer'][il] = experiments(X_np, f'L{il}')
        # save s / exc probe directions (fit on all forced rows) + CAA-style surprise vector
        X = torch.from_numpy(np.ascontiguousarray(X_np)).to(DEV)
        cv = RidgeCV(X, fold, args.folds)
        lam_f = res['by_layer'][il]['forced']['lambdas']
        cols = [tnames.index('s'), tnames.index('exc')]
        use = forced & finite[:, cols].all(1)
        mu, sd, W, ym = cv.fit_all(Y[:, cols], use, [float(np.median([l[0] for l in lam_f])), float(np.median([l[2] for l in lam_f]))])
        hi = forced & (S['bin'] >= 8)
        lo = forced & (S['bin'] <= 1)
        caa = X_np[hi].astype(np.float32).mean(0) - X_np[lo].astype(np.float32).mean(0)
        probe_dirs[il] = dict(mu=mu.cpu().numpy(), sd=sd.cpu().numpy(), w_std=W.cpu().numpy(),
                              w_raw=(W / sd[:, None]).cpu().numpy(), caa_hi_lo=caa)
        del X, cv
        torch.cuda.empty_cache()
        b = res['by_layer'][il]
        print(f"  forced s r2 {b['forced']['s']['r2']:.3f} (within-ctx r {b['forced']['s']['within_ctx_r']:.3f})  "
              f"exc r2 {b['forced']['exc']['r2']:.3f}  | natural s r2 {b['natural']['s']['r2']:.3f} "
              f"(within-token r {b['natural']['s']['within_token_r']:.3f}) exc r2 {b['natural']['exc']['r2']:.3f}  "
              f"| f->n r {b['forced->natural']['r']:.3f}", flush=True)

    np.savez(f'{args.data}/s1_probe_dirs.npz', layers=np.array(layers),
             **{f'{k}_L{il}': v for il, d in probe_dirs.items() for k, v in d.items()})
    json.dump(res, open(out_path, 'w'), indent=1)
    print(f'wrote {out_path} and s1_probe_dirs.npz ({time.time() - t0:.0f}s)')


if __name__ == '__main__':
    main()
