"""Task files for the auto-interpretation workflow (plan B), from autointerp_data.py's data.json.

Directions get anonymous ids (D01, ...; shuffled) so explainers cannot look up the current labels and judges cannot
tell which description is the baseline. Writes to OUT/tasks/:
  explain_K.md      evidence for explainer K: activation windows and steering examples, per direction
  judge_items_H.md  held-out items for judge half H: detection pairs and intervention pairs, per direction (no answers)
  manifest.json     id -> direction name, the batches, and the baseline descriptions (for the workflow's args)

usage: autointerp_tasks.py [--out /mnt/models/homeo/autointerp] [--n-explain 4] [--n-judge-split 2]
"""
import argparse
import json
import os
import random

ap = argparse.ArgumentParser()
ap.add_argument('--out', default='/mnt/models/homeo/autointerp')
ap.add_argument('--n-explain', type=int, default=4)
ap.add_argument('--n-judge-split', type=int, default=2)
a = ap.parse_args()
data = json.load(open(f'{a.out}/data.json'))
dirs = data['directions']
random.seed(11)
order = list(range(len(dirs)))
random.shuffle(order)
ids = {dirs[i]['name']: f'D{k + 1:02d}' for k, i in enumerate(order)}
by_id = {ids[d['name']]: d for d in dirs}
all_ids = sorted(by_id)
os.makedirs(f'{a.out}/tasks', exist_ok=True)


def chunks(xs, n):
    k = (len(xs) + n - 1) // n
    return [xs[i:i + k] for i in range(0, len(xs), k)]


HEAD_EXPLAIN = """# Evidence for {n} directions in a base language model's hidden state

Each direction is a fixed vector in the residual stream of one layer of GLM-4-32B-Base (a pretrained, not
instruction-tuned model). Its value at a token is the projection of the hidden state there onto the vector, scaled by
the state's norm. Values are in standard deviations of that projection over ordinary web text (0 = typical). Which end
is called high is arbitrary but fixed per direction.

For each direction you get two kinds of evidence:

1. **Activation windows.** 40-token stretches of web text (⏎ = newline). After each token, {{+2}} is the direction's
   value there; tokens with no braces are within 0.5 sd of typical. «» marks the token the window was picked for:
   4 windows around the highest values found, 4 around the lowest, 4 around random tokens.
2. **Steering.** From the end of a prefix on, the hidden state was pushed along the direction (a constant push at every
   later token, about 3.5 natural sd) toward HIGH or toward LOW values while the model kept writing, against an
   unpushed continuation with the same random numbers. Differences between the three continuations are caused by the
   push.

"""

for k, batch in enumerate(chunks(all_ids, a.n_explain)):
    out = [HEAD_EXPLAIN.format(n=len(batch))]
    for i in batch:
        d = by_id[i]
        out.append(f'\n## Direction {i}\n\n### Activation windows\n')
        for kind, w in d['windows']:
            out.append(f'- ({kind}) {w}\n')
        out.append('\n### Steering\n')
        for j, ev in enumerate(d['steer_evidence']):
            out.append(f'\n**Prefix {j + 1}** (end): …{ev["prefix_tail"]}\n')
            for s, sd in enumerate(ev['seeds']):
                out.append(f'- seed {s + 1}, unpushed: {sd["unpushed"]}\n- seed {s + 1}, toward HIGH: {sd["toward_high"]}\n'
                           f'- seed {s + 1}, toward LOW: {sd["toward_low"]}\n')
    open(f'{a.out}/tasks/explain_{k}.md', 'w').write(''.join(out))

HEAD_JUDGE = """# Test items for {n} directions in a base language model's hidden state

Each direction is a fixed vector in one layer of a pretrained language model; its value at a token says how far the
hidden state there points along it. You will be given a description of each direction. For each direction below there
are two kinds of items (⏎ = newline):

- **Detection pairs**: two text contexts, each ending in a «marked» token. Exactly one of them has a HIGH value of the
  direction at the marked token and the other a LOW value. Answer which (A or B) has the HIGHER value.
- **Intervention pairs**: a prefix and two continuations of it. The model wrote both after its hidden state was pushed
  along the direction from the end of the prefix on: one continuation toward HIGH values, the other toward LOW values
  (same random numbers otherwise). Answer which (A or B) was pushed toward HIGH.
"""

for h, half in enumerate(chunks(all_ids, a.n_judge_split)):
    out = [HEAD_JUDGE.format(n=len(half))]
    for i in half:
        d = by_id[i]
        out.append(f'\n## Direction {i}\n\n### Detection pairs ({len(d["detect"])})\n')
        for j, it in enumerate(d['detect']):
            out.append(f'{j + 1}. A: …{it["A"]}\n   B: …{it["B"]}\n')
        out.append(f'\n### Intervention pairs ({len(d["intervene"])})\n')
        for j, it in enumerate(d['intervene']):
            out.append(f'{j + 1}. Prefix (end): …{it["prefix_tail"]}\n   A: {it["A"]}\n   B: {it["B"]}\n')
    open(f'{a.out}/tasks/judge_items_{h}.md', 'w').write(''.join(out))

manifest = {
    'ids': {i: by_id[i]['name'] for i in all_ids},
    'explain_batches': chunks(all_ids, a.n_explain),
    'judge_halves': chunks(all_ids, a.n_judge_split),
    'n_items': {i: {'detect': len(by_id[i]['detect']), 'intervene': len(by_id[i]['intervene'])} for i in all_ids},
    'baseline': {i: by_id[i]['baseline'] for i in all_ids},
    'dir': os.path.abspath(f'{a.out}/tasks'),
}
json.dump(manifest, open(f'{a.out}/tasks/manifest.json', 'w'), ensure_ascii=False, indent=1)
print(f'{len(all_ids)} directions; explain batches {[len(b) for b in manifest["explain_batches"]]}; judge halves {[len(x) for x in manifest["judge_halves"]]}')
for f in sorted(os.listdir(f'{a.out}/tasks')):
    print(f, os.path.getsize(f'{a.out}/tasks/{f}'))
