#!/usr/bin/env python3
"""Pure ancestral rollouts in several languages, for the difficulty-forecast probe (notes: "Plan for the overnight run").

Seeds: the first 3 tokens of random documents, 70% English (FineWeb shard), 15% Chinese and 15% nine other languages
(FineWeb-2 test splits: French, German, Russian, Japanese, Korean, Arabic, Spanish, Hindi, Italian; the languages of
data/ml_seeds.txt). One rollout per document. Lengths (seed included) log-uniform in [160, 2048], so the contexts before
the probed windows vary from a few tokens to ~1,900.
Sampling: temperature 1 with only the temperature sampler in the chain (no top-k / top-p / min-p / typical / penalties;
llama-server's default min_p 0.05 truncated all earlier rollouts). End-of-text is sampled like any token: when the
model ends a document before the target length, the end token stays in the rollout and sampling continues after it.
Token ids are recorded (no retokenization).

  gen_rollouts_ml.py jobs OUT [--n 5000]          writes OUT/jobs.jsonl (seeds tokenized by the server)
  gen_rollouts_ml.py pretrain OUT [--n-pretrain 1667]   writes OUT/pretrain.jsonl: natural windows, 25% of the data
  gen_rollouts_ml.py run OUT --from A --to B      generates jobs A..B-1 into OUT/rollouts.jsonl (resumable)

Fan: a duty cycle keeps the GPU fan near 45% (requests of --seg tokens, started only in the on-part of each minute).
Rollout record: rid, lang, doc_idx, prompt_ids, tokens (generated ids incl. end tokens), n_end, target_len, seed.
"""
import argparse
import json
import math
import os
import random
import subprocess
import sys
import threading
import time
import urllib.request

import pyarrow.parquet as pq

R = '/home/bepis/prog/llm-tests'
FINEWEB = f'{R}/data/fineweb_000.parquet'
FW2 = f'{R}/data/fineweb2'
OTHER = ['fra_Latn', 'deu_Latn', 'rus_Cyrl', 'jpn_Jpan', 'kor_Hang', 'arb_Arab', 'spa_Latn', 'hin_Deva', 'ita_Latn']
LEN_LO, LEN_HI = 160, 2048
EOT = 151329  # <|endoftext|>
PRETRAIN_RID0 = 100000  # rids of the natural windows


def post(server, path, payload, timeout=3600):
    req = urllib.request.Request(server + path, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def make_jobs(a):
    rng = random.Random(20261020)
    n_zh = round(0.15 * a.n)
    n_other = round(0.15 * a.n)
    n_en = a.n - n_zh - n_other
    plan = [('eng_Latn', FINEWEB, n_en), ('cmn_Hani', f'{FW2}/cmn_Hani.test.parquet', n_zh)]
    per = [n_other // len(OTHER) + (i < n_other % len(OTHER)) for i in range(len(OTHER))]
    plan += [(l, f'{FW2}/{l}.test.parquet', k) for l, k in zip(OTHER, per)]
    jobs = []
    for lang, path, k in plan:
        texts = pq.read_table(path, columns=['text']).column('text').to_pylist()
        idx = rng.sample(range(len(texts)), k)
        for di in idx:
            ids = post(a.server, '/tokenize', {'content': texts[di][:512]})['tokens'][:3]
            jobs.append({'lang': lang, 'doc_idx': di, 'prompt_ids': ids})
        print(f'{lang}: {k} seeds from {len(texts)} docs', flush=True)
    rng.shuffle(jobs)  # any prefix of the job list is a representative mix
    for i, j in enumerate(jobs):
        j['rid'] = i
        j['target_len'] = int(round(math.exp(rng.uniform(math.log(LEN_LO), math.log(LEN_HI)))))
        j['seed'] = 1_000_003 * 7 + i
    os.makedirs(a.out, exist_ok=True)
    with open(f'{a.out}/jobs.jsonl', 'w', encoding='utf-8') as f:
        for j in jobs:
            f.write(json.dumps(j, ensure_ascii=False) + '\n')
    tot = sum(j['target_len'] for j in jobs)
    print(f'{len(jobs)} jobs, {tot} tokens (mean length {tot / len(jobs):.0f}) -> {a.out}/jobs.jsonl')


def make_pretrain(a):
    """natural text windows, a quarter of the data (the user's mix: 75% rollouts, 25% pretraining text): same language
    mix and length distribution as the rollouts; a window starts at a random document's beginning and runs on into
    further random documents of the same language, joined by the end-of-text token as in pretraining packing (the
    rollouts likewise run on after the model ends a document). Seed documents of the rollouts are excluded."""
    rng = random.Random(20261021)
    seeds = {}
    for l in open(f'{a.out}/jobs.jsonl', encoding='utf-8'):
        j = json.loads(l)
        seeds.setdefault(j['lang'], set()).add(j['doc_idx'])
    n = a.n_pretrain
    n_zh, n_other = round(0.15 * n), round(0.15 * n)
    plan = [('eng_Latn', FINEWEB, n - n_zh - n_other), ('cmn_Hani', f'{FW2}/cmn_Hani.test.parquet', n_zh)]
    per = [n_other // len(OTHER) + (i < n_other % len(OTHER)) for i in range(len(OTHER))]
    plan += [(l, f'{FW2}/{l}.test.parquet', k) for l, k in zip(OTHER, per)]
    recs = []
    for lang, path, k in plan:
        texts = pq.read_table(path, columns=['text']).column('text').to_pylist()
        pool = [i for i in range(len(texts)) if i not in seeds.get(lang, ())]
        rng.shuffle(pool)
        it = iter(pool)
        for _ in range(k):
            target = int(round(math.exp(rng.uniform(math.log(LEN_LO), math.log(LEN_HI)))))
            toks, docs = [], []
            while len(toks) < target:
                di = next(it)
                if toks:
                    toks.append(EOT)
                toks += post(a.server, '/tokenize', {'content': texts[di]})['tokens'][:target]
                docs.append(di)
            recs.append({'lang': lang, 'kind': 'pretrain', 'doc_idx': docs[0], 'docs': docs, 'prompt_ids': toks[:3],
                         'tokens': toks[3:target], 'target_len': target, 'n_end': len(docs) - 1})
        print(f'{lang}: {k} windows ({sum(len(r["docs"]) for r in recs if r["lang"] == lang)} documents)', flush=True)
    rng.shuffle(recs)
    with open(f'{a.out}/pretrain.jsonl', 'w', encoding='utf-8') as f:
        for i, r in enumerate(recs):
            r['rid'] = PRETRAIN_RID0 + i
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    tot = sum(r['target_len'] for r in recs)
    print(f'{len(recs)} pretraining windows, {tot} tokens (mean {tot / len(recs):.0f}) -> {a.out}/pretrain.jsonl')


class Gate:
    """duty cycle for the GPU fan: in each PERIOD seconds, segments may start during the first duty * PERIOD; the fan
    thread lowers duty when the fan runs above --fan-hi and raises it when it stays below --fan-lo. Lower concurrency
    does not cool a decoding GPU (it stays busy at any batch size), idle time does."""
    PERIOD = 60.0

    def __init__(self, duty):
        self.duty, self.t0 = duty, time.time()

    def wait(self):
        while True:
            ph = (time.time() - self.t0) % self.PERIOD
            if ph < self.duty * self.PERIOD:
                return
            time.sleep(self.PERIOD - ph + 0.01)


def fan():
    try:
        return int(subprocess.run(['nvidia-smi', '--query-gpu=fan.speed', '--format=csv,noheader,nounits'],
                                  capture_output=True, text=True, timeout=20).stdout.strip())
    except Exception:
        return -1


def run(a):
    jobs = [json.loads(l) for l in open(f'{a.out}/jobs.jsonl', encoding='utf-8')][a.frm:a.to]
    path = f'{a.out}/rollouts.jsonl'
    done = set()
    if os.path.exists(path):
        for l in open(path, encoding='utf-8'):
            try:
                done.add(json.loads(l)['rid'])
            except Exception:
                pass
    jobs = [j for j in jobs if j['rid'] not in done]
    jobs.sort(key=lambda j: -j['target_len'])  # longest first: the tail of the chunk is short requests, slots stay full
    print(f'{len(jobs)} rollouts to generate ({sum(j["target_len"] for j in jobs)} tokens), {len(done)} already done', flush=True)
    gate = Gate(a.duty)
    stop = threading.Event()
    dpath = f'{a.out}/duty'

    def guard():
        hist = []
        while not stop.wait(15):
            f = fan()
            if f < 0:
                continue
            hist = (hist + [f])[-12:]
            old = gate.duty
            if len(hist) >= 4 and min(hist[-4:]) > a.fan_hi and gate.duty > 0.1:
                gate.duty = max(0.1, round(gate.duty - 0.05, 2)); hist = []
            elif len(hist) >= 12 and max(hist) < a.fan_lo and gate.duty < 1.0:
                gate.duty = min(1.0, round(gate.duty + 0.05, 2)); hist = []
            if gate.duty != old:
                print(f'{time.strftime("%H:%M:%S")} fan {f}%: duty {old:.2f} -> {gate.duty:.2f}', flush=True)
                open(dpath, 'w').write(f'{gate.duty}\n')

    threading.Thread(target=guard, daemon=True).start()
    out_lock = threading.Lock()
    fout = open(path, 'a', encoding='utf-8')
    t0, n_tok, n_done = time.time(), [0], [0]

    def one(j):
        toks, n_end, seg = [], 0, 0
        need = j['target_len'] - len(j['prompt_ids'])
        while len(toks) < need:
            # one segment of at most SEG tokens; the next segment continues from the slot's KV cache (cache_prompt)
            payload = {'prompt': j['prompt_ids'] + toks, 'n_predict': min(a.seg, need - len(toks)), 'temperature': 1.0,
                       'samplers': ['temperature'], 'top_k': 0, 'top_p': 1.0, 'min_p': 0.0, 'typical_p': 1.0,
                       'repeat_penalty': 1.0, 'presence_penalty': 0.0, 'frequency_penalty': 0.0, 'dry_multiplier': 0.0,
                       'xtc_probability': 0.0, 'mirostat': 0, 'seed': j['seed'] * 1000 + seg, 'return_tokens': True,
                       'cache_prompt': True}
            seg += 1
            for attempt in range(5):
                try:
                    gate.wait()
                    o = post(a.server, '/completion', payload)
                    break
                except Exception as e:
                    if attempt == 4:
                        raise
                    print(f'rid {j["rid"]}: {e}; retrying', flush=True)
                    time.sleep(10)
            new = o['tokens']
            if not new:
                raise RuntimeError(f'rid {j["rid"]}: empty completion ({o.get("stop_type")})')
            toks += new
            if o.get('stop_type') == 'eos':
                n_end += 1  # the model ended a document: the end token stays, sampling continues after it
            elif o.get('stop_type') != 'limit':
                raise RuntimeError(f'rid {j["rid"]}: stopped early ({o.get("stop_type")})')
        rec = dict(j, kind='rollout', tokens=toks[:need], n_end=n_end)
        with out_lock:
            fout.write(json.dumps(rec, ensure_ascii=False) + '\n')
            fout.flush()
            n_tok[0] += need
            n_done[0] += 1
            if n_done[0] % 25 == 0:
                el = time.time() - t0
                print(f'{time.strftime("%H:%M:%S")} {n_done[0]}/{len(jobs)} rollouts, {n_tok[0] / el:.0f} tok/s, '
                      f'duty {gate.duty:.2f}, fan {fan()}%', flush=True)

    ths = []
    it = iter(jobs)
    it_lock = threading.Lock()
    err = []

    def worker():
        while True:
            with it_lock:
                j = next(it, None)
            if j is None or err:
                return
            try:
                one(j)
            except Exception as e:
                err.append(e)
                print(f'FAILED: {e}', flush=True)
                return

    for _ in range(a.conc):
        t = threading.Thread(target=worker)
        t.start()
        ths.append(t)
    for t in ths:
        t.join()
    stop.set()
    fout.close()
    print(f'chunk done: {n_done[0]} rollouts, {n_tok[0]} tokens in {time.time() - t0:.0f} s', flush=True)
    if err:
        sys.exit(1)


ap = argparse.ArgumentParser()
ap.add_argument('cmd', choices=['jobs', 'pretrain', 'run'])
ap.add_argument('out')
ap.add_argument('--server', default='http://127.0.0.1:8056')
ap.add_argument('--n', type=int, default=5000)
ap.add_argument('--n-pretrain', type=int, default=1667)
ap.add_argument('--from', dest='frm', type=int, default=0)
ap.add_argument('--to', type=int, default=None)
ap.add_argument('--conc', type=int, default=32)
ap.add_argument('--seg', type=int, default=128)
ap.add_argument('--duty', type=float, default=0.6)
ap.add_argument('--fan-hi', type=int, default=46)
ap.add_argument('--fan-lo', type=int, default=40)
a = ap.parse_args()
{'jobs': make_jobs, 'pretrain': make_pretrain, 'run': run}[a.cmd](a)
