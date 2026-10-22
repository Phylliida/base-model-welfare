#!/bin/bash
# Inputs: one FineWeb shard (English seeds and natural text) and the FineWeb-2 test splits of 10 languages.
set -e
source "$(dirname "$0")/../config.sh"
mkdir -p "$(dirname "$FINEWEB")" "$FINEWEB2_DIR"
[ -f "$FINEWEB" ] || curl -L -o "$FINEWEB" https://huggingface.co/datasets/HuggingFaceFW/fineweb/resolve/main/sample/10BT/000_00000.parquet
for L in cmn_Hani fra_Latn deu_Latn rus_Cyrl jpn_Jpan kor_Hang arb_Arab spa_Latn hin_Deva ita_Latn; do
  [ -f "$FINEWEB2_DIR/$L.test.parquet" ] || curl -L -o "$FINEWEB2_DIR/$L.test.parquet" \
    "https://huggingface.co/datasets/HuggingFaceFW/fineweb-2/resolve/main/data/$L/test/000_00000.parquet"
done
ls -la "$FINEWEB" "$FINEWEB2_DIR"
