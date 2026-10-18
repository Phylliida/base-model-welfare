#!/usr/bin/env python3
"""End-to-end check of llama-server --value-probe (the loom's value view).

Starts llama-server with --jlens and --value-probe, then:
  1. sends VL1 windows as token ids and compares the server's readouts at positions 32-158 with the offline
     prediction W h + b from homeo-capture's layer-40 activations of the same windows (the server computes h
     with the jspace forward graph, so small numeric differences are expected)
  2. sends the phrase- and token-loop scenario windows and reports mean stakes in the loop region against
     the same positions of the unmodified windows
  3. times a readouts_only request on a long text
Stops the server at the end.

usage: value_readout_check.py [--port 8098] [--jlens /mnt/models/jlens/jlens_glm4_q4k.jlns]
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

import torch  # noqa: F401  (import before numpy on this box)
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from value_probe import load_acts  # noqa: E402

H = '/mnt/models/homeo'
ROOT = '/home/bepis/prog/llm-tests'
MODEL = '/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf'
P_LO, P_HI = 32, 158


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8098)
    ap.add_argument('--jlens', default='/mnt/models/jlens/jlens_glm4_q4k.jlns')
    ap.add_argument('--readout', default=f'{H}/value_probe/readout_L40')
    ap.add_argument('--n-win', type=int, default=8)
    a = ap.parse_args()
    meta = json.load(open(a.readout + '.json'))
    n, D = len(meta['names']), meta['n_embd']
    buf = np.fromfile(a.readout + '.f32', dtype=np.float32)
    W, b = buf[:n * D].reshape(n, D), buf[n * D:]

    log = open(f'{H}/value_probe/readout_check_server.log', 'w')
    srv = subprocess.Popen([f'{ROOT}/llama.cpp/build-avx2/bin/llama-server', '-m', MODEL, '-ngl', '99', '-c', '4096',
                            '--port', str(a.port), '--jlens', a.jlens, '--value-probe', a.readout, '--no-webui',
                            # the J-lens graphs need every weight on the GPU; llama.cpp keeps token_embd on the CPU by default
                            '-ot', 'token_embd.weight=CUDA0'],
                           stdout=log, stderr=subprocess.STDOUT)

    def post(path, body):
        req = urllib.request.Request(f'http://127.0.0.1:{a.port}{path}', data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.loads(r.read())

    try:
        for _ in range(900):
            if srv.poll() is not None:
                raise RuntimeError(f'llama-server exited ({srv.returncode}); see readout_check_server.log')
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{a.port}/health', timeout=5)
                break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError('llama-server did not come up')

        # 1. server vs offline readouts on the same tokens
        X, _, _ = load_acts(f'{H}/value_probe/main', 1200)
        P = P_HI - P_LO + 1
        diffs, cors = [], []
        for w in range(a.n_win):
            toks = json.load(open(f'{H}/value/w{w:05d}.json'))['tokens']
            r = post('/jlens', {'tokens': toks, 'readouts': True, 'readouts_only': True})
            sv = np.array(r['readouts']['values'])[P_LO:P_HI + 1]
            off = X[w * P:(w + 1) * P] @ W.T + b
            diffs.append(np.abs(sv - off).mean(0))
            cors.append([np.corrcoef(sv[:, k], off[:, k])[0, 1] for k in range(n)])
        d, c = np.mean(diffs, 0), np.mean(cors, 0)
        sd = np.array([meta['stats'][k]['sd'] for k in meta['names']])
        print(f'1. server vs offline readouts, {a.n_win} windows x {P} positions:')
        for k, name in enumerate(meta['names']):
            print(f'   {name:7s} mean |diff| {d[k]:.4f} ({d[k] / sd[k]:.2f} fineweb sd)  corr {c[k]:.4f}')

        # 2. loops
        man = json.load(open(f'{H}/value_scen/manifest.json'))
        ids = np.fromfile(f'{H}/value_scen/scenario_ids.bin', dtype=np.int32).reshape(len(man), 192)
        k = meta['names'].index('stakes')
        groups = {}
        for i, m in enumerate(man):
            if m['scenario'] not in ('phrase loop', 'token loop'):
                continue
            r = post('/jlens', {'tokens': ids[i].tolist(), 'readouts': True, 'readouts_only': True})
            v = np.array(r['readouts']['values'])[100:159, k]
            groups.setdefault(m['scenario'], []).append(v.mean())
            if m['scenario'] == 'phrase loop':
                toks = json.load(open(f'{H}/value/w{m["pair"]:05d}.json'))['tokens']
                r = post('/jlens', {'tokens': toks, 'readouts': True, 'readouts_only': True})
                groups.setdefault('same text without the loop', []).append(np.array(r['readouts']['values'])[100:159, k].mean())
        print('2. mean log stakes (probe), positions 100-158:')
        for g, v in groups.items():
            print(f'   {g:28s} {np.mean(v):+.3f}  (n {len(v)})')

        # 3. timing on a long text
        text = open(f'{H}/value_scen2/texts.jsonl').read()[:12000]
        t0 = time.time()
        r = post('/jlens', {'content': text, 'readouts': True, 'readouts_only': True})
        print(f'3. readouts_only on {r["n_tokens"]} tokens: {time.time() - t0:.2f} s')
    finally:
        srv.terminate()
        srv.wait()


if __name__ == '__main__':
    main()
