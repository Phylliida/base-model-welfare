#!/usr/bin/env python3
"""VL3: what are the stable future-value directions? (VL1 found about ten directions of g_fut at layer 40 that
replicate across halves of the windows.)

For the top principal directions u_i of g_fut (second moment over clean positions):
  - share of g_fut's second moment, and split-half |cosine| (half A's i-th direction against its best match
    among half B's top 2n: does the direction itself replicate)
  - orientation: sign chosen so that the projection's skew is positive (the long tail is "+")
  - contexts: the positions with the largest + and - projections, decoded (current token in [brackets],
    next token after |)
  - tokens: current and next tokens most over-represented among the top 1% of |projection|
  - J-lens: the tokens that a push along +u / -u promotes, read through the layer-40 J-lens transport and the
    final norm + unembedding (direction decode: y = J u, logits = W_U (w_norm * y))
  - cosines with the S2 library vectors

usage: value_directions.py [--value /mnt/models/homeo/value] [--n-dir 10] [--jlens PATH] [--json out.json]
"""
import argparse
import json
import os
import sys

import torch
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from value_forecast import blank_tokens  # noqa: E402

H = '/mnt/models/homeo'
MODEL = '/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf'
P_LO, P_HI, D = 32, 158, 6144
P = P_HI - P_LO + 1


def show(toks, vocab, s, before=24, after=6):
    def piece(i):
        return vocab[i].replace('\u0120', ' ').replace('\u010a', '\\n').replace('\u0109', '\\t')
    left = ''.join(piece(t) for t in toks[max(0, s - before):s])
    nxt = ''.join(piece(t) for t in toks[s + 1:s + 1 + after])
    return f'...{left}[{piece(toks[s])}]|{nxt}'


def unembed():
    """Final norm weight and the unembedding as float32 (dequantized from the GGUF; cached)."""
    cache = f'{H}/value/unembed.npy'
    if os.path.exists(cache):
        return np.load(f'{H}/value/out_norm.npy'), np.load(cache, mmap_mode='r')
    sys.path.insert(0, '/home/bepis/prog/llm-tests/llama.cpp/gguf-py')
    from gguf import GGUFReader
    from gguf.quants import dequantize
    r = GGUFReader(MODEL)
    t = {x.name: x for x in r.tensors}
    w = dequantize(t['output_norm.weight'].data, t['output_norm.weight'].tensor_type).astype(np.float32).reshape(-1)
    W = dequantize(t['output.weight'].data, t['output.weight'].tensor_type).astype(np.float32).reshape(-1, D)
    np.save(f'{H}/value/out_norm.npy', w)
    np.save(cache, W)
    return w, W


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--value', default=f'{H}/value')
    ap.add_argument('--n-dir', type=int, default=10)
    ap.add_argument('--jlens', default='/mnt/models/jlens/jlens_glm4_q4k.jlns')
    ap.add_argument('--examples', type=int, default=5)
    ap.add_argument('--json', default=None)
    ap.add_argument('--kind', default='fut', choices=['fut', 'now'])
    ap.add_argument('--normalize', action='store_true', help='principal directions of g / |g| (outlier-robust)')
    a = ap.parse_args()
    torch.set_num_threads(48)
    vocab = json.load(open(f'{a.value}/vocab.json'))
    blank = blank_tokens()
    meta = json.load(open(f'{a.value}/meta.json'))
    L = len(meta['layers'])
    n_win = meta['n_windows']

    fut = np.empty((n_win, P, D), np.float32)
    toks, clean = [], np.zeros((n_win, P), bool)
    for w in range(n_win):
        fut[w] = np.memmap(f'{a.value}/w{w:05d}.bin', dtype=np.float16, mode='r', shape=(L, 3, P, D))[0, 2 if a.kind == 'fut' else 0]
        tk = json.load(open(f'{a.value}/w{w:05d}.json'))['tokens']
        toks.append(tk)
        for i, s in enumerate(range(P_LO, P_HI + 1)):
            clean[w, i] = not any(t in blank for t in tk[s + 1:s + 34])
    G = torch.from_numpy(fut.reshape(-1, D))
    cm = torch.from_numpy(clean.reshape(-1))
    if a.normalize:
        G = G / G.norm(dim=1, keepdim=True).clamp_min(1e-12)
    Gc = G[cm].double()
    C = Gc.T @ Gc / len(Gc)
    e, V = torch.linalg.eigh(C)
    e, V = e.flip(0), V.flip(1)
    share = (e / e.sum()).numpy()
    half = len(Gc) // 2  # windows are in order, so this is a split by window
    Va = torch.linalg.eigh(Gc[:half].T @ Gc[:half])[1].flip(1)
    Vb = torch.linalg.eigh(Gc[half:].T @ Gc[half:])[1].flip(1)
    del Gc

    nd = a.n_dir
    U = V[:, :nd].float().numpy().T  # [nd, D]
    proj = (G @ torch.from_numpy(U).T).numpy().reshape(n_win, P, nd)  # g_fut . u_i
    proj[~clean] = np.nan
    for i in range(nd):
        x = proj[:, :, i][clean]
        if ((x - x.mean()) ** 3).mean() < 0:
            U[i] *= -1
            proj[:, :, i] *= -1
    # split-half replication: direction i of half A against its best match among half B's top 2 * nd
    Ua, Ub = Va[:, :nd].numpy().T, Vb[:, :2 * nd].numpy().T
    rep = [float(np.max(np.abs(Ub @ Ua[i]))) for i in range(nd)]

    # J-lens decode of the directions
    with open(a.jlens, 'rb') as f:
        hdr = np.frombuffer(f.read(16), dtype=np.uint32)
        n_pos = np.frombuffer(f.read(16), dtype=np.uint64)[1]
        assert hdr[0] == 0x4A4C4E53 and hdr[2] == D
        f.seek(32 + 40 * D * D * 4)
        M = np.frombuffer(f.read(D * D * 4), dtype=np.float32).reshape(D, D) / float(n_pos)
    JU = U @ M  # rows: (J u_i)^T; the file stores J column-major, so J u = u @ M
    wn, W = unembed()
    logits = (JU * wn) @ np.asarray(W).T  # [nd, n_vocab]

    lib = {'temperature (S2(c), L40)': f'{H}/s2opt/vec_temp1.3_opt2_L40.f32', 'band p~0.5 (L40)': f'{H}/s2opt/vec_p0.5_opt2_L40.f32'}
    libv = {k: (lambda v: v / np.linalg.norm(v))(np.fromfile(p, dtype=np.float32)) for k, p in lib.items()}

    def piece(i):
        return vocab[i].replace('\u0120', ' ').replace('\u010a', '\\n')

    out = {'share_top': [float(x) for x in share[:nd]], 'directions': []}
    cur_all = np.array([[tk[s] for s in range(P_LO, P_HI + 1)] for tk in toks])
    nxt_all = np.array([[tk[s + 1] for s in range(P_LO, P_HI + 1)] for tk in toks])
    base_cur = np.bincount(cur_all[clean], minlength=len(vocab)) / clean.sum()
    base_nxt = np.bincount(nxt_all[clean], minlength=len(vocab)) / clean.sum()
    print(f'g_{a.kind}{" (normalized)" if a.normalize else ""} at layer 40: {clean.sum()} clean positions; top {nd} directions carry {share[:nd].sum():.1%} of the second moment')
    for i in range(nd):
        x = proj[:, :, i]
        fl = np.where(clean, x, np.nan)
        sd = np.nanstd(fl)
        order = np.argsort(np.where(clean, x, -np.inf).ravel())[::-1]
        order_neg = np.argsort(np.where(clean, x, np.inf).ravel())
        top = np.abs(np.nan_to_num(fl)) >= np.nanpercentile(np.abs(fl), 99)
        cur_top = np.bincount(cur_all[top], minlength=len(vocab)) / top.sum()
        nxt_top = np.bincount(nxt_all[top], minlength=len(vocab)) / top.sum()
        lift_c = [(piece(t), float(cur_top[t]), float(cur_top[t] / max(base_cur[t], 1e-9))) for t in np.argsort(-cur_top)[:6]]
        lift_n = [(piece(t), float(nxt_top[t]), float(nxt_top[t] / max(base_nxt[t], 1e-9))) for t in np.argsort(-nxt_top)[:6]]
        jl_pos = [piece(t) for t in np.argsort(-logits[i])[:12]]
        jl_neg = [piece(t) for t in np.argsort(logits[i])[:12]]
        cos = {k: float(U[i] @ v) for k, v in libv.items()}
        d = dict(share=float(share[i]), split_half=rep[i], sd=float(sd), skew=float(np.nanmean(((fl - np.nanmean(fl)) / sd) ** 3)),
                 frac_pos=float(np.nanmean(fl > 0)), jlens_pos=jl_pos, jlens_neg=jl_neg, cur_top1pct=lift_c, next_top1pct=lift_n,
                 cos=cos, examples_pos=[], examples_neg=[])
        print(f'\n== direction {i + 1}: share {share[i]:.4f}, split-half |cos| (A_i vs best B) {rep[i]:.2f}, sd {sd:.3f}, skew {d["skew"]:+.1f}, '
              f'frac > 0 {d["frac_pos"]:.2f}; cos temp {cos["temperature (S2(c), L40)"]:+.3f}')
        print(f'  J-lens +: {" ".join(repr(t) for t in jl_pos)}')
        print(f'  J-lens -: {" ".join(repr(t) for t in jl_neg)}')
        print('  current token at top 1% |proj|: ' + ', '.join(f'{t!r} {f:.0%} (x{l:.0f})' for t, f, l in lift_c))
        print('  next token at top 1% |proj|:    ' + ', '.join(f'{t!r} {f:.0%} (x{l:.0f})' for t, f, l in lift_n))
        for lab, od, key in [('+', order, 'examples_pos'), ('-', order_neg, 'examples_neg')]:
            seen = set()
            for flat in od:
                w, j = divmod(int(flat), P)
                if w in seen:
                    continue
                seen.add(w)
                txt = show(toks[w], vocab, P_LO + j)
                d[key].append(dict(w=w, s=P_LO + j, proj=float(x[w, j]), text=txt))
                print(f'  {lab} {x[w, j] / sd:+6.1f} sd  w{w} s{P_LO + j}: {txt!r}')
                if len(seen) >= a.examples:
                    break
        out['directions'].append(d)
    # what the subspace is: alignment with the mean residual and with g_now's subspace, coordinate concentration
    hm = np.load(f'{H}/value_probe/mean_h_L40.npy')
    hm = hm / np.linalg.norm(hm)
    out['cos_mean_h'] = [float(U[i] @ hm) for i in range(nd)]
    coord = (U ** 2).sum(0)
    topc = np.argsort(-coord)[:10]
    out['top_coords'] = [(int(c), float(coord[c] / nd)) for c in topc]
    print('\ncos with the mean residual direction: ' + ' '.join(f'{x:+.2f}' for x in out['cos_mean_h']))
    print('coordinates carrying the most of the top-%d subspace: ' % nd + ', '.join(f'{c} ({f:.1%})' for c, f in out['top_coords']))
    print(f'share of the subspace in the top 10 coordinates: {sum(f for _, f in out["top_coords"]):.1%} (uniform: {10 / D:.2%})')
    np.save(f'{a.value}/{a.kind}_dirs_L40{"_norm" if a.normalize else ""}.npy', U)
    if a.json:
        json.dump(out, open(a.json, 'w'), indent=1)


if __name__ == '__main__':
    main()
