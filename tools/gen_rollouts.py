#!/usr/bin/env python3
# gen_rollouts.py: base-model rollout dataset for lens fitting.
#
# Samples N documents uniformly at random from the FineWeb parquet shard,
# takes the first 3 tokens of each as the prompt, and generates R rollouts of
# T tokens each with UNBIASED ancestral sampling (temp=1.0, no top-k/top-p,
# ignore_eos) so the rollouts reflect the model's true distribution —
# including document restarts via EOS-like tokens.
#
# Output JSONL: {"doc_idx", "rollout_idx", "prompt_ids", "text", "tokens"} (tokens: generated ids; homeo-capture
# uses them instead of retokenizing the text).
#
# usage: gen_rollouts.py PARQUET OUT.jsonl [--server URL] [--n-docs N]
#        [--rollouts R] [--tokens T] [--seed S]

import argparse
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor

import pyarrow.parquet as pq
import urllib.request


def post(server: str, path: str, payload: dict, timeout: int = 600) -> dict:
    req = urllib.request.Request(server + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("parquet", nargs="?")
    ap.add_argument("out")
    ap.add_argument("--server", default="http://127.0.0.1:8391")
    ap.add_argument("--n-docs", type=int, default=64)
    ap.add_argument("--rollouts", type=int, default=3)
    ap.add_argument("--tokens", type=int, default=2048)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--seeds-file", help="one seed text per line; first 3 tokens become the prompt (overrides parquet sampling)")
    args = ap.parse_args()

    if args.seeds_file:
        lines = [l for l in open(args.seeds_file, encoding="utf-8").read().split("\n") if l.strip()]
        prompts = []
        for i, line in enumerate(lines):
            ids = post(args.server, "/tokenize", {"content": line})["tokens"]
            prompts.append(ids[:3])
        doc_idxs = list(range(len(lines)))  # doc_idx = line number
        print(f"{len(prompts)} seeds from {args.seeds_file}")
    else:
        table = pq.read_table(args.parquet, columns=["text"])
        texts = table.column("text").to_pylist()
        print(f"{len(texts)} docs in shard")

        rng = random.Random(args.seed)
        doc_idxs = sorted(rng.sample(range(len(texts)), args.n_docs))
        print(f"sampled {len(doc_idxs)} docs: {doc_idxs[:8]}...")

        # first 3 tokens of each doc (tokenize a prefix, keep the leading 3 ids)
        prompts = []
        for di in doc_idxs:
            prefix = texts[di][:512]
            ids = post(args.server, "/tokenize", {"content": prefix})["tokens"]
            prompts.append(ids[:3])
        print("prompts tokenized")

    jobs = [(di, ri, prompts[i]) for i, di in enumerate(doc_idxs) for ri in range(args.rollouts)]

    # resume: skip (doc_idx, rollout_idx) pairs already in the output file
    done_pairs = set()
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    done_pairs.add((rec["doc_idx"], rec["rollout_idx"]))
                except Exception:
                    pass
    before = len(done_pairs)
    jobs = [j for j in jobs if (j[0], j[1]) not in done_pairs]
    if before:
        print(f"resuming: {before} rollouts already done, {len(jobs)} to go")

    def run(job):
        di, ri, pids = job
        payload = {
            "prompt": pids,
            "n_predict": args.tokens,
            "temperature": 1.0,   # pure ancestral: no truncation bias
            "samplers": ["temperature"],  # nothing else in the chain (llama-server's default min_p 0.05 clipped
            "top_p": 1.0,                 # every rollout made before 2026-10-20)
            "top_k": 0,
            "min_p": 0.0,
            "typical_p": 1.0,
            "repeat_penalty": 1.0,
            "return_tokens": True,
            "ignore_eos": True,   # keep generating through document restarts
            "seed": args.seed * 100003 + di * 131 + ri,
            "stream": False,
        }
        for attempt in range(3):
            try:
                out = post(args.server, "/completion", payload)
                return {"doc_idx": di, "rollout_idx": ri, "prompt_ids": pids, "text": out["content"], "tokens": out["tokens"]}
            except Exception as e:
                if attempt == 2:
                    raise
                print(f"doc {di} rollout {ri}: {e}; retrying", flush=True)
                time.sleep(5)

    t0 = time.time()
    done = 0
    with open(args.out, "a", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=4) as pool:
        for rec in pool.map(run, jobs):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            done += 1
            if done % 12 == 0:
                rate = done / (time.time() - t0)
                print(f"{done}/{len(jobs)} rollouts ({rate * args.tokens:.0f} tok/s agg)", flush=True)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
