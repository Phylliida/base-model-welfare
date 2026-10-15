#!/usr/bin/env python3
"""Scenario windows for the value lens (Antra's three scenarios: degenerate loops, boring text, rich
worldbuilding). Boring and dense text come from the main fineweb run itself (its easiest and hardest
windows); this script builds the other two as 192-token windows for homeo-value --stride 192:

- phrase loop: the first 96 tokens of main-run window w, then the 12-token chunk ending at 96 repeated
- token loop:  the first 96 tokens of window w, then token 95 repeated ("the the the")
  (both paired with the unmodified window w from the main run, w = 0..15)
- fiction: worldbuilding openings continued by the base model itself (unsteered, temperature 1, no
  truncation), first 192 tokens of prompt + continuation

Writes OUT/scenario_ids.bin (i32, back to back) and OUT/manifest.json.

usage: value_scenarios_prep.py [--out /mnt/models/homeo/value_scen] [--pairs 16]
"""
import argparse
import json
import os
import subprocess

import torch  # noqa: F401  (import before numpy on this box)
import numpy as np

ROOT = '/home/bepis/prog/llm-tests'
MODEL = '/home/bepis/prog/SimpleBot/models/GLM-4-32B-Base-32K.i1-Q4_K_S.gguf'
BIN = f'{ROOT}/llama.cpp/build-avx2/bin'
T = 192
PROMPTS = [
    "Chapter One\n\nThe city of Vael was built on the back of a sleeping god, and every morning the bakers",
    "The cartographers of the Ninth Archive kept three kinds of maps: maps of places that existed, maps of places that",
    "In the year the rivers ran backward, my grandmother opened her tea shop on the edge of the salt flats.",
    "The colony ship Perennial had been underway for four hundred years when the gardeners discovered",
    "Every child in Hollowmere is given a lantern on their seventh birthday. Mine was",
    "The treaty between the moth-people and the glassblowers' guild had held for a century, until",
    "Nobody in the valley remembered who had built the singing towers, but everyone knew the rules:",
    "Captain Ilse Marrow read the weather the way other sailors read charts. That morning the sky over the Shattered Sea",
    "The last librarian of Kethra walked the stacks at night, because at night the books",
    "When the second moon came back, the tide-priests declared a festival, and my brother and I",
    "Under the old law of the mountain clans, a debt could be paid in stories. Tamsin owed",
    "The orchard on the far side of the wall grew fruit that tasted like other people's memories.",
]


def tokenize(text, tmp):
    with open(tmp + '.txt', 'w') as f:
        f.write(text)
    subprocess.run([f'{BIN}/jlens-prep', '-m', MODEL, '--text', tmp + '.txt', '--out', tmp + '.bin'],
                   check=True, capture_output=True)
    return np.fromfile(tmp + '.bin', dtype=np.int32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='/mnt/models/homeo/value_scen')
    ap.add_argument('--main', default='/mnt/models/homeo/value')
    ap.add_argument('--pairs', type=int, default=16)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    windows, manifest = [], []

    for w in range(a.pairs):
        toks = json.load(open(f'{a.main}/w{w:05d}.json'))['tokens']
        head = toks[:96]
        unit = toks[84:96]
        phrase = head + (unit * 8)[:96]
        single = head + [toks[95]] * 96
        windows.append(phrase); manifest.append(dict(scenario='phrase loop', pair=w, loop_start=96))
        windows.append(single); manifest.append(dict(scenario='token loop', pair=w, loop_start=96))

    for i, prompt in enumerate(PROMPTS):
        gen = subprocess.run([f'{BIN}/llama-completion', '-m', MODEL, '-p', prompt, '-n', '360', '--temp', '1.0',
                              '--top-k', '0', '--top-p', '1.0', '--min-p', '0', '--repeat-penalty', '1.0', '-s', str(1000 + i),
                              '-ngl', '99', '-c', '1024', '--no-display-prompt', '-no-cnv'],
                             capture_output=True, text=True, check=True)
        cont = gen.stdout.rstrip()
        if cont.endswith('[end of text]'):  # llama-completion's EOG marker, not model text
            cont = cont[:-len('[end of text]')].rstrip()
        text = prompt + cont
        ids = tokenize(text, f'{a.out}/fiction_{i:02d}')
        if len(ids) < T:
            print(f'fiction {i}: only {len(ids)} tokens, skipped')
            continue
        windows.append(ids[:T].tolist())
        manifest.append(dict(scenario='fiction', prompt=i, text=text[:1500]))
        print(f'fiction {i}: {len(ids)} tokens: {text[:120]!r}')

    np.array([t for w in windows for t in w], dtype=np.int32).tofile(f'{a.out}/scenario_ids.bin')
    json.dump(manifest, open(f'{a.out}/manifest.json', 'w'), indent=1)
    print(f'wrote {len(windows)} windows to {a.out}/scenario_ids.bin')


if __name__ == '__main__':
    main()
