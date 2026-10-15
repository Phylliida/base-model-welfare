#!/usr/bin/env python3
"""S2(c) layer sweep summary: per layer, the fraction of the held-out CE gap (v = 0 -> floor H(r))
closed by the optimized vector, next to the best global temperature's fraction.

Files for the same band/target (e.g. a run and its resumes, *_rN.json) are merged by layer.

usage: s2sweep_summary.py /mnt/models/homeo/s2sweep/p0.25*.json [...]
"""
import json
import os
import re
import sys


def main():
    groups = {}
    for path in sys.argv[1:]:
        R = json.load(open(path))
        key = re.sub(r'_r\d+$', '', os.path.basename(path)[:-5])  # p0.25_r1.json -> p0.25
        if key in groups:
            groups[key][1]['layers'] += R['layers']
        else:
            groups[key] = (path, R)
    for path, R in groups.values():
        R['layers'].sort(key=lambda L: L['layer'])
        ce0, ceT, floor = R['test_v0']['ce'], R['test_best_temperature']['ce'], R['ce_floor_H_r']
        gap = ce0 - floor
        stem = re.sub(r'_r\d+$', '', os.path.basename(path)[:-5])
        tag = f"temperature target {stem[4:]}" if stem.startswith('temp') else f"band p~{stem[1:]}"
        print(f"\n{path.split('/')[-1]}: {tag}  (held-out CE v=0 {ce0:.4f}, best T={R['test_best_temperature']['T']:.2f} {ceT:.4f}, floor {floor:.4f})")
        print(f"  best temperature closes {100 * (ce0 - ceT) / gap:5.1f}% of the gap")
        print('  layer  |h|     closed@30  closed@60  band ratio  KL(nonband)')
        best = None
        for L in R['layers']:
            ev = L['test_eval']
            fr = [100 * (ce0 - e['ce']) / gap for e in ev]
            last = ev[-1]
            print(f"  L{L['layer']:02d}  {L['resid_norm']:7.1f}  " + '  '.join(f'{x:8.1f}%' for x in fr) +
                  f"   {last['band_ratio']:7.3f}    {last['kl_nonband']:.4f}")
            m = max(fr)
            if best is None or m > best[1]:
                best = (L['layer'], m)
        if best:
            print(f"  max over layers: L{best[0]:02d} closes {best[1]:.1f}%")


if __name__ == '__main__':
    main()
