"""Score the auto-interpretation workflow (plan B): blind judges' answers against the held-out keys.

Inputs in OUT: tasks/manifest.json (anonymous ids), keys.json (answers, by direction name), results.json (the
workflow's return value: {"explanations": {id: {...}}, "judgments": {"auto"|"baseline": {id: {"detect": [...],
"intervene": [...]}}}}). Accuracy per direction, description source (the explainers' "auto" descriptions, or the current
labels, "baseline") and task (detection extreme / moderate, intervention), with binomial 95% intervals over items and a
paired auto-vs-baseline comparison over directions. Writes OUT/scores.json and OUT/scores.txt.

usage: autointerp_score.py [--out /mnt/models/homeo/autointerp]
"""
import argparse
import json
import math

ap = argparse.ArgumentParser()
ap.add_argument('--out', default='/mnt/models/homeo/autointerp')
a = ap.parse_args()
man = json.load(open(f'{a.out}/tasks/manifest.json'))
keys = json.load(open(f'{a.out}/keys.json'))
res = json.load(open(f'{a.out}/results.json'))
P = json.load(open('/mnt/models/homeo/score/probe_dirs.json'))
BY = {d['name']: d for d in P['directions']}


def wilson(k, n):
    if n == 0:
        return (float('nan'),) * 3
    p, z = k / n, 1.96
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return p, c - h, c + h


rows, pooled = [], {}
for i, name in man['ids'].items():
    key = keys[name]
    d = BY[name]
    row = {'id': i, 'name': name, 'layer': d['layer'], 'side': d['side'], 'rank': d['rank'], 'family': d['family_label'], 'heldout': d['heldout']}
    for src in ('auto', 'baseline'):
        j = res['judgments'].get(src, {}).get(i)
        if not j:
            continue
        for task, ans, kk in (('detect_extreme', j.get('detect', []), [x for x, k_ in zip(key['detect'], key['detect_kind']) if k_ == 'extreme']),
                              ('detect_moderate', j.get('detect', []), [x for x, k_ in zip(key['detect'], key['detect_kind']) if k_ == 'moderate']),
                              ('intervene', j.get('intervene', []), key['intervene'])):
            if task.startswith('detect'):
                sel = [m for m, k_ in enumerate(key['detect_kind']) if k_ == task.split('_')[1]]
                ans = [ans[m] if m < len(ans) else None for m in sel]
            n_ok = sum(1 for x, y in zip(ans, kk) if x == y)
            n = len(kk)
            row[f'{src}_{task}'] = (n_ok, n)
            pk = pooled.setdefault((src, task), [0, 0])
            pk[0] += n_ok; pk[1] += n
    rows.append(row)

lines = []
say = lambda s='': (print(s), lines.append(s))
say(f'Scored auto-interpretation: {len(rows)} directions; blind judges answer held-out items from a description alone (chance 50%).')
say('auto = descriptions written by explainer agents from activation windows and steering examples; baseline = the current labels '
    '(family, natural-text reading, effector tokens).')
say()
say('pooled accuracy (95% interval over items):')
for task in ('detect_extreme', 'detect_moderate', 'intervene'):
    s = []
    for src in ('auto', 'baseline'):
        k, n = pooled.get((src, task), (0, 0))
        p, lo, hi = wilson(k, n)
        s.append(f'{src} {p:.2f} [{lo:.2f}, {hi:.2f}] ({k}/{n})')
    say(f'  {task:16s} ' + '   '.join(s))
say()
# paired comparison over directions
for task in ('detect_extreme', 'detect_moderate', 'intervene'):
    diffs = []
    for r in rows:
        if f'auto_{task}' in r and f'baseline_{task}' in r and r[f'auto_{task}'][1] and r[f'baseline_{task}'][1]:
            diffs.append(r[f'auto_{task}'][0] / r[f'auto_{task}'][1] - r[f'baseline_{task}'][0] / r[f'baseline_{task}'][1])
    if diffs:
        m = sum(diffs) / len(diffs)
        sd = math.sqrt(sum((x - m) ** 2 for x in diffs) / max(1, len(diffs) - 1))
        say(f'  auto - baseline, {task}: {m:+.3f} +- {sd / math.sqrt(len(diffs)):.3f} (se over {len(diffs)} directions; '
            f'auto better on {sum(x > 0 for x in diffs)}, worse on {sum(x < 0 for x in diffs)})')
say()
say('per direction (accuracy; detection pools extreme + moderate):')
say(f'{"id":4s} {"direction":16s} {"family":26s} {"kappa":>6s} | {"auto det":>8s} {"auto int":>8s} | {"base det":>8s} {"base int":>8s} | auto label')
for r in sorted(rows, key=lambda r: (r['layer'], r['side'], r['rank'])):
    f = lambda src, t: (lambda k, n: f'{k / n:.2f}' if n else '  -')(*r.get(f'{src}_{t}', (0, 0)))
    fd = lambda src: (lambda e, m: f'{(e[0] + m[0]) / (e[1] + m[1]):.2f}' if e[1] + m[1] else '  -')(r.get(f'{src}_detect_extreme', (0, 0)), r.get(f'{src}_detect_moderate', (0, 0)))
    lab = res['explanations'].get(r['id'], {}).get('label', '')
    say(f'{r["id"]:4s} {r["name"]:16s} {r["family"]:26s} {r["heldout"]:+6.2f} | {fd("auto"):>8s} {f("auto", "intervene"):>8s} | {fd("baseline"):>8s} {f("baseline", "intervene"):>8s} | {lab}')
json.dump({'rows': rows, 'pooled': {f'{k[0]}_{k[1]}': v for k, v in pooled.items()}, 'explanations': res['explanations']},
          open(f'{a.out}/scores.json', 'w'), ensure_ascii=False, indent=1)
open(f'{a.out}/scores.txt', 'w').write('\n'.join(lines) + '\n')
