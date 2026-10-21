#!/usr/bin/env python3
"""Stream text out of a FineWeb parquet shard into a single UTF-8 corpus file.

Stops after --max-chars characters (corpus for jlens-prep tokenization).
"""
import argparse
import sys

import pyarrow.parquet as pq


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("parquet")
    ap.add_argument("out")
    ap.add_argument("--max-chars", type=int, default=40_000_000)
    args = ap.parse_args()

    pf = pq.ParquetFile(args.parquet)
    written = 0
    n_docs = 0
    with open(args.out, "w", encoding="utf-8") as f:
        for batch in pf.iter_batches(batch_size=256, columns=["text"]):
            for text in batch.column("text").to_pylist():
                if not text:
                    continue
                f.write(text)
                f.write("\n\n")
                written += len(text) + 2
                n_docs += 1
                if written >= args.max_chars:
                    print(f"extract_fineweb: {n_docs} docs, {written} chars -> {args.out}")
                    return
    print(f"extract_fineweb: exhausted shard at {n_docs} docs, {written} chars -> {args.out}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
