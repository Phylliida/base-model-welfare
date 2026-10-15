#!/usr/bin/env python3
"""K4 loop-margin summary for homeo-loop output (NOTES-homeostasis.md, K4).

Per (layer, vector, dose): loop fraction, incoherence fraction, median loop onset, loop period
histogram (period 1 vs longer), mean entropy over the first 32 generated steps, distinct-4-gram
rate, mean steps run. Per vector: loop margin (lowest dose with loop fraction >= 0.5), endpoint
margin (lowest dose with any endpoint >= 0.5), and the two-phase check: does mean entropy rise
above the unsteered level (by --dh nats) at a dose below the loop margin?

usage: k4_loop_summary.py k4_L44.jsonl [k4_L40.jsonl ...] [--json out.json] [--dh 0.5]
"""
import argparse
import json
import statistics
from collections import defaultdict


def distinct4(toks):
    grams = [tuple(toks[i:i + 4]) for i in range(len(toks) - 3)]
    return len(set(grams)) / len(grams) if grams else float('nan')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='+')
    ap.add_argument('--json', default=None)
    ap.add_argument('--dh', type=float, default=0.5, help='entropy rise (nats) that counts as a confusion phase')
    a = ap.parse_args()

    arms = defaultdict(list)  # (layer, vector, dose) -> rows
    for f in a.files:
        for line in open(f):
            if line.strip():
                r = json.loads(line)
                arms[(r['layer'], r['vector'], r['dose'])].append(r)

    stats = {}
    for key, rows in arms.items():
        n = len(rows)
        looped = [r for r in rows if r['loop_period'] > 0]
        h32 = [h for r in rows for h in r['entropies'][:32]]
        d4 = [distinct4(r['tokens']) for r in rows if len(r['tokens']) >= 8]
        stats[key] = {
            'n': n,
            'loop_frac': len(looped) / n,
            'incoh_frac': sum(r['incoh_onset'] >= 0 for r in rows) / n,
            'median_loop_onset': statistics.median(r['loop_onset'] for r in looped) if looped else None,
            'period1': sum(r['loop_period'] == 1 for r in looped),
            'period_gt1': sum(r['loop_period'] > 1 for r in looped),
            'mean_H32': statistics.fmean(h32) if h32 else float('nan'),
            'distinct4': statistics.fmean(d4) if d4 else float('nan'),
            'mean_steps': statistics.fmean(len(r['tokens']) for r in rows),
        }

    out = {'arms': [], 'vectors': []}
    layers = sorted({k[0] for k in stats})
    for L in layers:
        base = stats.get((L, 'none', 0.0))
        h_base = base['mean_H32'] if base else float('nan')
        print(f'\n== layer {L}  (unsteered: loop {base["loop_frac"]:.2f}, incoh {base["incoh_frac"]:.2f}, '
              f'H32 {h_base:.2f}, distinct4 {base["distinct4"]:.3f})' if base else f'\n== layer {L}')
        print('  vector                    dose  loop  incoh  onset  p=1/p>1   H32   dist4  steps')
        vecs = sorted({k[1] for k in stats if k[0] == L and k[1] != 'none'})
        for v in vecs:
            doses = sorted(k[2] for k in stats if k[0] == L and k[1] == v)
            for d in doses:
                s = stats[(L, v, d)]
                on = f'{s["median_loop_onset"]:5.0f}' if s['median_loop_onset'] is not None else '    -'
                print(f'  {v:24s} {d:5.2f}  {s["loop_frac"]:4.2f}  {s["incoh_frac"]:4.2f}  {on}  '
                      f'{s["period1"]:3d}/{s["period_gt1"]:<3d}  {s["mean_H32"]:5.2f}  {s["distinct4"]:5.3f}  {s["mean_steps"]:5.1f}')
                out['arms'].append({'layer': L, 'vector': v, 'dose': d, **s})
            loop_margin = next((d for d in doses if stats[(L, v, d)]['loop_frac'] >= 0.5), None)
            end_margin = next((d for d in doses if stats[(L, v, d)]['loop_frac'] + stats[(L, v, d)]['incoh_frac'] >= 0.5), None)
            below = [d for d in doses if loop_margin is None or d < loop_margin]
            h_peak = max((stats[(L, v, d)]['mean_H32'] for d in below), default=float('nan'))
            two_phase = loop_margin is not None and h_peak > h_base + a.dh
            print(f'  -> {v}: loop margin {loop_margin}, endpoint margin {end_margin}, '
                  f'peak H32 below loop margin {h_peak:.2f} (unsteered {h_base:.2f}), two-phase {"yes" if two_phase else "no"}')
            out['vectors'].append({'layer': L, 'vector': v, 'loop_margin': loop_margin, 'endpoint_margin': end_margin,
                                   'peak_H32_below_loop_margin': h_peak, 'unsteered_H32': h_base, 'two_phase': two_phase})
        if base:
            out['arms'].append({'layer': L, 'vector': 'none', 'dose': 0.0, **base})

    if a.json:
        with open(a.json, 'w') as f:
            json.dump(out, f, indent=2)


if __name__ == '__main__':
    main()
