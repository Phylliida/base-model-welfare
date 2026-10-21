import torch, numpy as np, json, os
rng = np.random.default_rng(0)
SAMPLE = np.dtype([('seq','<i4'),('pos','<i4'),('token','<i4'),('kind','<i4'),('bin','<i4'),('rank_prev','<i4'),('surprisal','<f4'),('entropy_prev','<f4'),('entropy','<f4'),('pad','<f4',3)])
LABEL = np.dtype([('seq','<i4'),('pos','<i4'),('token','<i4'),('rank_prev','<i4'),('surprisal','<f4'),('entropy_prev','<f4'),('entropy','<f4'),('pad','<f4')])
langs = ['eng_Latn']*7 + ['cmn_Hani']*2 + ['fra_Latn']
dirw = np.random.default_rng(1).standard_normal(6144).astype(np.float32)
for k in range(2):
    S = f'/dev/shm/rollprobe_fake/c{k}'; os.makedirs(S, exist_ok=True)
    seqs, labs, smps, acts = [], [], [], []
    for q in range(150):
        n = int(rng.integers(160, 600))
        c = np.abs(rng.standard_normal(n)) * 2 + np.repeat(rng.uniform(0, 3, n // 40 + 1), 40)[:n]
        c[0] = np.nan
        L = np.zeros(n, LABEL); L['seq'] = q; L['pos'] = np.arange(n); L['token'] = rng.integers(0, 1000, n); L['surprisal'] = c; L['entropy'] = rng.uniform(0, 5, n)
        labs.append(L)
        ds = sorted(set(rng.integers(16, n - 133, 4).tolist()))
        ds2 = []
        for d in ds:
            if not ds2 or d > ds2[-1] + 1: ds2.append(d)
        pos = sorted(p for d in ds2 for p in (d, d + 1))
        for p in pos:
            s = np.zeros(1, SAMPLE); s['seq'] = q; s['pos'] = p; s['token'] = L['token'][p]; smps.append(s)
            fut = np.nanmean(c[p + 2:p + 130])
            acts.append(fut * dirw[None] * 0.1 + rng.standard_normal((1, 6144)).astype(np.float32))
        seqs.append({'rid': k * 1000 + q, 'lang': langs[q % 10], 'kind': 'rollout' if q % 4 else 'pretrain', 'n_end': 0})
    np.concatenate(labs).tofile(f'{S}/labels.bin'); smp = np.concatenate(smps); smp.tofile(f'{S}/samples.bin')
    A = np.concatenate(acts).astype(np.float16)
    for l in range(61):
        (A + np.float16(l * 0.01)).tofile(f'{S}/acts_L{l:02d}.f16')
    json.dump({'n_samples': len(smp)}, open(f'{S}/meta.json', 'w'))
    with open(f'/dev/shm/rollprobe_fake/capture_c{k}.jsonl', 'w') as f:
        for s in seqs: f.write(json.dumps(s) + '\n')
    print(k, len(smp))
