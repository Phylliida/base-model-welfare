#!/usr/bin/env python3
"""S2b: selectivity table for band steering vectors (homeo-steer JSON outputs).

For each vector and scale: per probability band, mass_q / mass_p (steered over unsteered band
mass) and the same ratio for the temperature-matched p_T. A vector that promotes only tokens of
probability P raises the P band above its temperature match and leaves the other bands alone.
'inv' is how often the steered argmax is a P-band token that was not the unsteered argmax.

usage: s2b_summarize.py RES.json [RES.json ...]
"""
import json
import sys


def main():
    for path in sys.argv[1:]:
        R = json.load(open(path))
        lv = R['levels']
        print(f"\n{path.split('/')[-1]}  (layer {R['layer']}, {R['n_positions']} positions)")
        print('  scale   E[-ln p]  T    | band mass ratio q/p  (temperature-matched p_T/p in brackets)')
        print('                         | ' + ''.join(f'{"p~%g" % x:>16}' for x in lv) + '   inv@target')
        for s in R['scales']:
            cells = ''.join(f"{b['mass_q'] / max(b['mass_p'], 1e-12):7.2f} [{b['mass_pT'] / max(b['mass_p'], 1e-12):5.2f}] " for b in s['bands'])
            tgt = path.split('vec_p')[-1].split('_')[0] if 'vec_p' in path else None
            inv = ''
            if tgt is not None:
                for b in s['bands']:
                    if abs(b['level'] - float(tgt)) < 1e-6:
                        inv = f"{b['argmax_inverted_into_band']:.4f}"
            print(f"  {s['scale']:+.2f}  {s['E_surprisal']:7.3f}  {s['T_geomean']:4.2f} | {cells}  {inv}")


if __name__ == '__main__':
    main()
