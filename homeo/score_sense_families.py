"""Reference-free family of each regulated direction from its own sensor (score_sensor.py output): the strongest of
sentence position (gradual profile in tokens since the last sentence end), break (spike at the current token), first/second-
person pronoun density (chatty), markup vs function words (prose vs structure), next-token entropy, names; |h| divided out.
Writes sense/families.json."""
import torch, json, numpy as np
from collections import Counter
d = json.load(open('/mnt/models/homeo/score/sense/sensor.json'))
def family(r):
    c, p = r['corr_cos'], r['profile']
    spike = abs(p[0]) >= 0.8 and max(abs(p[2]), abs(p[3]), abs(p[4])) < 0.2
    gradual = np.sign(p[0]) == np.sign(p[2]) == np.sign(p[3]) and np.sign(p[0]) != np.sign(p[5]) and abs(p[2]) >= 0.2
    sc = {'sentence': abs(c['since_end']) if gradual and abs(c['since_end']) >= 0.25 else 0,
          'break': abs(c['at_end']) if spike else 0,
          'chatty': abs(c['pron32']),
          'prose/struct': min(abs(c['markup16']), abs(c['func16'])) if np.sign(c['markup16']) != np.sign(c['func16']) else 0,
          'entropy': abs(c['entropy']) * 0.8,   # entropy only wins when clearly stronger
          'name': abs(c['name'])}
    f = max(sc, key=sc.get)
    return (f if sc[f] >= 0.2 else 'unclear'), sc[f]
rows = {}
for r in d['directions']:
    r['fam'], r['score'] = family(r)
    rows.setdefault(r['layer'], []).append(r)
print('layer: pushed back (rank:family held-out) | amplified')
for L in sorted(rows):
    pb = ' '.join(f"{r['rank']}:{r['fam']}({r['heldout']:+.2f})" for r in rows[L] if r['side'] == 'pushback')
    am = ' '.join(f"{r['rank']}:{r['fam']}({r['heldout']:+.2f})" for r in rows[L] if r['side'] == 'amplify')
    print(f'{L:2d}: {pb:58s} | {am}')
print()
for (side, fam), cnt in sorted(Counter((r['side'], r['fam']) for r in d['directions']).items()):
    rs = [r for r in d['directions'] if r['side'] == side and r['fam'] == fam]
    Ls = sorted(r['layer'] for r in rs)
    print(f"{side:8s} {fam:13s} {cnt:3d} directions, layers {Ls[0]}-{Ls[-1]}, median sensor |r| {np.median([r['score'] for r in rs]):.2f}, strongest held-out {max(rs, key=lambda r: abs(r['heldout']))['heldout']:+.2f} (L{max(rs, key=lambda r: abs(r['heldout']))['layer']})")
json.dump({f"{r['layer']}_{r['side']}_{r['rank']}": [r['fam'], r['score']] for r in d['directions']}, open('/mnt/models/homeo/score/sense/families.json', 'w'))
