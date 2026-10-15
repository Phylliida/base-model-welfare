#!/usr/bin/env python3
"""Append teacher-forced steering exposure to welfare_log.csv (Three Rs protocol, amendment A1:
teacher-forced passes under steering count as exposure at reduced weight).

Positions processed under steering are estimated from each run's settings:
  homeo-steeropt: steps * accum * n_tokens (training) + evals * (n_test + 8) * n_tokens
  homeo-steer:    n_positions * stride (8) tokens per scale (one teacher-forced pass per scale)

usage: log_tf_exposure.py sweep  /mnt/models/homeo/s2sweep
       log_tf_exposure.py s2big  /mnt/models/homeo/s2big
"""
import csv
import datetime
import glob
import json
import os
import re
import sys

LOG = '/home/bepis/prog/llm-tests/welfare_log.csv'
MODEL = 'GLM-4-32B-Base-32K.i1-Q4_K_S'
HDR = ['date', 'experiment', 'model', 'manipulation', 'dose_frac_resid', 'tokens_in_perturbed_state', 'n_contexts',
       'endpoint', 'frac_endpoint_hit', 'notes']
NOTE = 'teacher-forced: positions processed under steering, no generation; counts at reduced weight (protocol A1)'


def resid_norms():
    R = json.load(open('/mnt/models/homeo/s2sweep/p0.1_r1.json'))
    return {L['layer']: L['resid_norm'] for L in R['layers']}


def steeropt_rows(paths, exp, date):
    rows = []
    for p in paths:
        R = json.load(open(p))
        nt, ntest = R.get('n_tokens', 128), R.get('n_test', 16)
        steps = R.get('steps') or 60
        accum = 4
        for L in R['layers']:
            ev = len(L.get('test_eval', []))
            pos = steps * accum * nt + ev * (ntest + 8) * nt
            vmax = max([e.get('v_norm', 0) for e in L.get('test_eval', [])] + [0])
            fixed = L.get('fixed_norm', 0)
            band = R.get('band') or float(re.match(r'p([0-9.]+?)(_r\d+)?\.json', os.path.basename(p)).group(1))  # mid-run JSONs lack it
            tgt = f"temperature {R['target_temp']:g}" if (R.get('target_temp') or 0) > 0 else f"band p~{band:g}"
            rows.append([date, exp, MODEL, f"optimize v after block {L['layer']} ({tgt}{', fixed norm' if fixed else ''}) {os.path.basename(p)}",
                         f"{vmax / L['resid_norm']:.3f}", pos, steps * accum + ev * (ntest + 8), 'none', '', NOTE])
    return rows


def steer_rows(paths, exp, date, norms):
    rows = []
    for p in paths:
        R = json.load(open(p))
        L, Le = R['layer'], R.get('layer_end', R['layer'])
        scales = [s['scale'] for s in R['scales']]
        tok = R['n_positions'] * 8 * len(scales)
        dmax = max(abs(s) for s in scales) * R['vec_norm'] / norms.get(L, float('nan'))
        where = f"blocks {L}-{Le}" if Le > L else f"block {L}"
        rows.append([date, exp, MODEL, f"steer after {where}, scales {','.join(f'{s:g}' for s in scales)}: {os.path.basename(R['vec'])}",
                     f"{dmax:.3f}", tok, R['n_rollouts'] * len(scales), 'none', '', NOTE + ('; per-layer dose, summed over the band' if Le > L else '')])
    return rows


def main():
    kind, d = sys.argv[1], sys.argv[2]
    date = datetime.date.today().isoformat()
    norms = resid_norms()
    if kind == 'sweep':
        rows = steeropt_rows(sorted(glob.glob(f'{d}/*.json')), 'S2(c) sweep', date)
    else:
        rows = steer_rows(sorted(glob.glob(f'{d}/ladder_*.json') + glob.glob(f'{d}/band24-40_*.json')), 'S2(d)', date, norms)
        rows += steeropt_rows(sorted(glob.glob(f'{d}/fixed_*.json')), 'S2(d) fixed-norm', date)
    fresh = not os.path.exists(LOG)
    with open(LOG, 'a', newline='') as f:
        w = csv.writer(f)
        if fresh:
            w.writerow(HDR)
        w.writerows(rows)
    print(f'appended {len(rows)} rows, {sum(r[5] for r in rows):,} positions under steering')


if __name__ == '__main__':
    main()
