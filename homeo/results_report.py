#!/usr/bin/env python3
"""Build the S1-S2(d) and K4/K4b results report (HTML with inline SVG charts) from the result files.

Rerun after the layer sweep finishes; the sweep chart and tables read the current JSONs.

usage: results_report.py OUT.html
"""
import glob
import html
import json
import os
import re
import sys

H = '/mnt/models/homeo'

COLORS = {  # token name -> (light, dark)
    'temp': ('#2b5c8e', '#84b2e2'),
    'p0.5': ('#b4561f', '#ec9a62'),
    'p0.25': ('#2d7652', '#7cc8a0'),
    'p0.1': ('#7a4fa3', '#bf9be3'),
    'p0.03': ('#a23b5a', '#e58aa6'),
    'grey': ('#7d8796', '#8e98a7'),
}


def esc(s):
    return html.escape(str(s))


# ---------------------------------------------------------------- charts

def line_chart(series, xlim, ylim, xticks, yticks, xlabel, ylabel, hlines=(), w=680, h=330, yfmt='{:g}'):
    """series: dicts with name, color, pts [(x, y)], dash (bool), markers (bool). Points outside ylim are
    drawn as triangles on the edge and break the line."""
    ml, mr, mt, mb = 56, 18, 14, 46
    pw, ph = w - ml - mr, h - mt - mb
    cc = lambda c: c.replace('.', '_')  # css class names cannot contain dots
    X = lambda x: ml + (x - xlim[0]) / (xlim[1] - xlim[0]) * pw
    Y = lambda y: mt + (1 - (y - ylim[0]) / (ylim[1] - ylim[0])) * ph
    o = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(ylabel)} by {esc(xlabel)}">']
    for t in yticks:
        o.append(f'<line class="grid{" zero" if t == 0 else ""}" x1="{ml}" x2="{ml + pw}" y1="{Y(t):.1f}" y2="{Y(t):.1f}"/>')
        o.append(f'<text class="tick" x="{ml - 8}" y="{Y(t) + 4:.1f}" text-anchor="end">{esc(yfmt.format(t))}</text>')
    for t in xticks:
        o.append(f'<line class="axis" x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{mt + ph}" y2="{mt + ph + 5}"/>')
        o.append(f'<text class="tick" x="{X(t):.1f}" y="{mt + ph + 19}" text-anchor="middle">{esc(t)}</text>')
    o.append(f'<line class="axis" x1="{ml}" x2="{ml + pw}" y1="{mt + ph}" y2="{mt + ph}"/>')
    o.append(f'<text class="label" x="{ml + pw / 2:.1f}" y="{h - 6}" text-anchor="middle">{esc(xlabel)}</text>')
    o.append(f'<text class="label" transform="translate(14 {mt + ph / 2:.1f}) rotate(-90)" text-anchor="middle">{esc(ylabel)}</text>')
    for y, color, txt in hlines:
        o.append(f'<line class="href c-{cc(color)}" x1="{ml}" x2="{ml + pw}" y1="{Y(y):.1f}" y2="{Y(y):.1f}"/>')
        if txt:
            o.append(f'<text class="hlabel f-{cc(color)}" x="{ml + pw - 4}" y="{Y(y) - 5:.1f}" text-anchor="end">{esc(txt)}</text>')
    for s in series:
        segs, cur = [], []
        for x, y in s['pts']:
            if ylim[0] <= y <= ylim[1]:
                cur.append((x, y))
            else:
                if cur:
                    segs.append(cur)
                cur = []
                yy = ylim[0] if y < ylim[0] else ylim[1]
                d = 1 if y < ylim[0] else -1
                px, py = X(x), Y(yy)
                o.append(f'<path class="f-{cc(s["color"])}" d="M{px - 5:.1f} {py - 7 * d:.1f} L{px + 5:.1f} {py - 7 * d:.1f} L{px:.1f} {py:.1f} Z"/>')
        if cur:
            segs.append(cur)
        for seg in segs:
            if len(seg) > 1:
                pts = ' '.join(f'{X(x):.1f},{Y(y):.1f}' for x, y in seg)
                o.append(f'<polyline class="line c-{cc(s["color"])}{" dash" if s.get("dash") else ""}" points="{pts}"/>')
            if s.get('markers', len(seg) == 1):
                for x, y in seg:
                    o.append(f'<circle class="f-{cc(s["color"])}" cx="{X(x):.1f}" cy="{Y(y):.1f}" r="3.2"/>')
    o.append('</svg>')
    leg = ''.join(f'<li><span class="sw{" dashsw" if s.get("dash") else ""} b-{cc(s["color"])}"></span>{esc(s["name"])}</li>' for s in series)
    return f'<div class="chart">{"".join(o)}</div><ul class="legend">{leg}</ul>'


def dose_grid(arms, rows, doses, caption_id):
    """Rows of (key, label, group) against doses. Each cell: share of 16 sequences that looped (violet, from the
    left) and that went incoherent (raspberry, from the right). Dashed outline: ladder stopped before this dose."""
    cw, ch, gap, lw, top = 50, 22, 4, 250, 34
    groups = []
    for r in rows:
        if not groups or groups[-1][0] != r[2]:
            groups.append((r[2], []))
        groups[-1][1].append(r)
    nrow = len(rows) + len(groups)
    w = lw + len(doses) * (cw + gap) + 10
    h = top + nrow * (ch + gap) + 8
    o = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-describedby="{caption_id}">']
    for j, d in enumerate(doses):
        o.append(f'<text class="tick" x="{lw + j * (cw + gap) + cw / 2:.1f}" y="{top - 10}" text-anchor="middle">{esc(f"{d:g}")}</text>')
    y = top
    for g, rs in groups:
        o.append(f'<text class="glabel" x="0" y="{y + ch - 7}">{esc(g)}</text>')
        y += ch + gap
        for key, label, _ in rs:
            o.append(f'<text class="rlabel" x="12" y="{y + ch - 7}">{esc(label)}</text>')
            for j, d in enumerate(doses):
                x = lw + j * (cw + gap)
                a = arms.get((key, d))
                if a is None:
                    o.append(f'<rect class="gstop" x="{x}" y="{y}" width="{cw}" height="{ch}" rx="2"/>')
                    continue
                o.append(f'<rect class="gbg" x="{x}" y="{y}" width="{cw}" height="{ch}" rx="2"/>')
                lf, inf = a['loop_frac'], a['incoh_frac']
                if lf > 0:
                    o.append(f'<rect class="f-p0_1" x="{x}" y="{y}" width="{cw * lf:.1f}" height="{ch}" rx="2"/>')
                if inf > 0:
                    o.append(f'<rect class="f-p0_03" x="{x + cw * (1 - inf):.1f}" y="{y}" width="{cw * inf:.1f}" height="{ch}" rx="2"/>')
                o.append(f'<title>{esc(label)} at {d:g}: loops {lf:.0%}, incoherent {inf:.0%}, mean entropy {a["mean_H32"]:.2f} nats</title>')
            y += ch + gap
    o.append('</svg>')
    return '<div class="chart gridchart">' + ''.join(o) + '</div>'


def k4_arms(path, layer_names):
    S = json.load(open(path))
    out = {}
    for a in S['arms']:
        out[(layer_names.get(a['layer'], a['layer']), a['vector'], round(a['dose'], 4))] = a
    return out


def within_token_band_effect(path, band, n=64, width=1.5):
    """Corrected within-token analysis (see homeo/s2d_within_token.py): band minus rest of the residual boost
    after removing the temperature line, raw and within token."""
    import torch  # noqa: F401  (import before numpy on this box)
    import numpy as np
    rec = np.fromfile(path, dtype=np.dtype([('id', '<i4'), ('lp', '<f4'), ('lq', '<f4')]))
    P = len(rec) // n
    rec = rec[:P * n].reshape(P, n)
    ids, lp, lq = rec['id'], rec['lp'].astype(np.float64), rec['lq'].astype(np.float64)
    d = lq - lp
    keep = lp / np.log(10) > -3.5
    cnt = keep.sum(1, keepdims=True)
    dc = d - (d * keep).sum(1, keepdims=True) / cnt
    lc = lp - (lp * keep).sum(1, keepdims=True) / cnt
    ids, l10, d, x = ids[keep], (lp / np.log(10))[keep], dc[keep], lc[keep]
    res = d - (d * x).sum() / (x * x).sum() * x
    _, inv, c = np.unique(ids, return_inverse=True, return_counts=True)
    resw = res - (np.bincount(inv, weights=res) / c)[inv]
    multi = c[inv] >= 3
    lo, hi = np.log10(band / width), np.log10(band * width)
    ib = (l10 >= lo) & (l10 <= hi)
    return res[ib].mean() - res[~ib].mean(), resw[ib & multi].mean() - resw[~ib & multi].mean()


def exposure_totals():
    import csv
    free_tok = free_ctx = tf_pos = 0
    with open('/home/bepis/prog/llm-tests/welfare_log.csv') as f:
        for r in csv.DictReader(f):
            if 'smoke test' in r['notes']:
                continue
            if r['notes'].startswith('teacher-forced'):
                tf_pos += int(r['tokens_in_perturbed_state'])
            else:
                free_tok += int(r['tokens_in_perturbed_state'])
                free_ctx += int(r['n_contexts'])
    return free_tok, free_ctx, tf_pos


# ---------------------------------------------------------------- data

def load_sweep():
    groups = {}
    for path in sorted(glob.glob(f'{H}/s2sweep/*.json')):
        R = json.load(open(path))
        key = re.sub(r'_r\d+$', '', os.path.basename(path)[:-5])
        if key in groups:
            groups[key]['layers'] += R['layers']
        else:
            groups[key] = R
    out = {}
    for key, R in groups.items():
        ce0, ceT, floor = R['test_v0']['ce'], R['test_best_temperature']['ce'], R['ce_floor_H_r']
        gap = ce0 - floor
        lay = sorted(R['layers'], key=lambda L: L['layer'])
        out[key] = dict(
            best_T=R['test_best_temperature']['T'], best_T_frac=100 * (ce0 - ceT) / gap,
            pts=[(L['layer'], 100 * (ce0 - L['test_eval'][-1]['ce']) / gap) for L in lay],
            pts30=[(L['layer'], 100 * (ce0 - L['test_eval'][0]['ce']) / gap) for L in lay])
    return out


def main():
    out_path = sys.argv[1]
    S1 = json.load(open(f'{H}/s1/s1_results.json'))
    bl = S1['by_layer']
    layers = S1['layers']
    emb = S1['embedding']
    s2 = {k: json.load(open(f'{H}/s2/res_{k}.json')) for k in ['caa_L44', 'caa_L32', 'probe_s_L44', 'rand_L44']}
    sw = load_sweep()

    # S1 chart: R2 by layer
    c_s1 = line_chart(
        [dict(name='Surprisal, forced tokens', color='temp', markers=True, pts=[(L, bl[str(L)]['forced']['s']['r2']) for L in layers]),
         dict(name='Surprisal, natural text', color='p0.25', markers=True, pts=[(L, bl[str(L)]['natural']['s']['r2']) for L in layers]),
         dict(name='Previous-step entropy, natural text', color='p0.1', markers=True, pts=[(L, bl[str(L)]['natural']['H']['r2']) for L in layers])],
        (0, 60), (0, 1), list(range(0, 61, 10)), [0, 0.2, 0.4, 0.6, 0.8, 1.0], 'Layer (of 61)', 'Held-out R²',
        hlines=[(emb['forced']['s']['r2'], 'temp', f'embedding baseline, forced: {emb["forced"]["s"]["r2"]:.2f}')], yfmt='{:.1f}')

    # S1 memory curve at L44
    n44 = bl['44']['natural']
    lag = [(0, n44['s']['r2'])] + [(int(k[5:]), n44[k]['r2']) for k in n44 if k.startswith('s_lag')]
    c_mem = line_chart(
        [dict(name='R² of surprisal k tokens back, decoded from the current state (L44)', color='temp', markers=True, pts=lag)],
        (0, 32), (0, 0.7), [0, 4, 8, 12, 16, 20, 24, 28, 32], [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7], 'Lag k (tokens)', 'Held-out R²', yfmt='{:.1f}')

    # S2 chart: E[-ln p] vs scale
    def es(R):
        return sorted([(0.0, 0.705)] + [(s['scale'], s['E_surprisal']) for s in R['scales']])
    c_s2 = line_chart(
        [dict(name='Contrastive "weird token" vector, L44', color='temp', markers=True, pts=es(s2['caa_L44'])),
         dict(name='Contrastive vector, L32', color='p0.5', markers=True, pts=es(s2['caa_L32'])),
         dict(name='Surprise probe readout direction, L44', color='p0.1', markers=True, pts=es(s2['probe_s_L44'])),
         dict(name='Random direction, L44', color='grey', markers=True, dash=True, pts=es(s2['rand_L44']))],
        (-0.5, 0.5), (0, 3.2), [-0.5, -0.25, 0, 0.25, 0.5], [0, 0.5, 1, 1.5, 2, 2.5, 3], 'Steering scale (fraction of mean residual norm)',
        'Mean next-token surprisal (nats)')

    # sweep chart
    names = {'temp1.3': ('Temperature 1.3 target (control)', 'temp'), 'p0.5': ('Band p ≈ 0.5', 'p0.5'),
             'p0.25': ('Band p ≈ 0.25', 'p0.25'), 'p0.1': ('Band p ≈ 0.1', 'p0.1'), 'p0.03': ('Band p ≈ 0.03', 'p0.03')}
    order = [k for k in ['temp1.3', 'p0.5', 'p0.25', 'p0.1', 'p0.03'] if k in sw]
    c_sweep = line_chart(
        [dict(name=names[k][0], color=names[k][1], markers=(k == 'temp1.3' or len(sw[k]['pts']) < 30), pts=sw[k]['pts']) for k in order],
        (0, 60), (-20, 80), list(range(0, 61, 10)), [-20, -10, 0, 10, 20, 30, 40, 50, 60, 70, 80],
        'Layer where the vector is added', 'Held-out gap closed (%)', yfmt='{:g}%')

    expected = {'temp1.3': 7, 'p0.25': 61, 'p0.1': 61, 'p0.5': 16, 'p0.03': 16}
    rows = []
    for k in order:
        d = sw[k]
        inner = [(L, v) for L, v in d['pts'] if L > 0]
        bL, bv = max(inner, key=lambda t: t[1]) if inner else (None, float('nan'))
        l0 = [v for L, v in d['pts'] if L == 0]
        n = len(d['pts'])
        status = 'complete' if n >= expected[k] else f'{n} of {expected[k]} layers'
        rows.append(f'<tr><td>{esc(names[k][0])}</td><td>{d["best_T_frac"]:.1f}% (T = {d["best_T"]:.2f})</td>'
                    f'<td>{bv:.1f}% (L{bL})</td><td>{(f"{l0[0]:.0f}%" if l0 else "not run")}</td><td>{status}</td></tr>')
    sweep_table = ''.join(rows)
    sweep_done = all(len(sw[k]['pts']) >= expected[k] for k in expected if k in sw) and len(sw) == 5

    # ---- S2(d) ----
    B = f'{H}/s2big'
    wt_rows = []
    for label, f, band in [('Temperature vector, L50 (control)', 'wt_temp1.3_L50_s1', 0.03), ('Temperature vector, L50, 4×', 'wt_temp1.3_L50_s4', 0.03),
                           ('p ≈ 0.03 vector, L56, learned size', 'wt_p0.03_L56_s1', 0.03), ('p ≈ 0.03 vector, L56, 4×', 'wt_p0.03_L56_s4', 0.03),
                           ('p ≈ 0.03 vector, L56, 16×', 'wt_p0.03_L56_s16', 0.03), ('p ≈ 0.1 vector, L53, 4×', 'wt_p0.1_L53_s4', 0.1),
                           ('p ≈ 0.1 vector, L53, 16×', 'wt_p0.1_L53_s16', 0.1)]:
        raw, wtk = within_token_band_effect(f'{B}/{f}.bin', band)
        wt_rows.append(f'<tr><td>{esc(label)}</td><td>{band:g}</td><td>{raw:+.3f}</td><td>{wtk:+.3f}</td></tr>')
    LV = json.load(open(f'{B}/ladder_p0.03_sweep_L56.json'))
    lad_rows = []
    for sc in LV['scales']:
        bands = {round(b['level'], 4): b for b in sc['bands']}
        b3, b1 = bands[0.03], bands[0.01]
        lad_rows.append(f'<tr><td>{sc["scale"]:g}×</td><td>{sc["added_norm"] / 866.8:.2f}×</td><td>×{b3["mass_q"] / b3["mass_p"]:.2f}</td>'
                        f'<td>×{b3["mass_pT"] / b3["mass_p"]:.2f}</td><td>×{b1["mass_q"] / b1["mass_p"]:.2f}</td><td>{sc["KL_q_p"]:.2f}</td>'
                        f'<td>{sc["argmax_agree"]:.0%}</td></tr>')
    fx = {}
    for f in glob.glob(f'{B}/fixed_*.json'):
        m = re.match(r'fixed_(.+)_L(\d+)_s([0-9.]+)_(rand|small)\.f32\.json', os.path.basename(f))
        R = json.load(open(f)); L = R['layers'][0]
        ce0, floor = R['test_v0']['ce'], R['ce_floor_H_r']
        fx.setdefault((m.group(1), int(m.group(2))), {}).setdefault(float(m.group(3)), []).append(100 * (ce0 - L['test_eval'][-1]['ce']) / (ce0 - floor))
    fx_names = {'temp1.3': 'Temperature 1.3 target (control)', 'p0.25': 'Band p ≈ 0.25', 'p0.1': 'Band p ≈ 0.1'}
    fx_rows = []
    for (t, L) in sorted(fx, key=lambda k: (k[0] != 'temp1.3', k[0], k[1])):
        cells = ''.join(f'<td>{int(round(min(fx[(t, L)][s_])))}% to {int(round(max(fx[(t, L)][s_])))}%</td>' if s_ in fx[(t, L)] else '<td>-</td>' for s_ in (0.5, 1.0, 2.0))
        fx_rows.append(f'<tr><td>{esc(fx_names.get(t, t))}, L{L}</td>{cells}</tr>')
    tail = LV['scales'][1]
    tb = LV['base_mass']
    def grp(m):
        return [m[0], sum(m[1:5]), m[5], sum(m[6:])]
    tail_rows = ''.join(f'<tr><td>{n}</td><td>{a:.3f}</td><td>{b:.3f}</td><td>{c:.3f}</td></tr>' for n, a, b, c in zip(
        ['Very likely (p &gt; 0.32)', 'Plausible (0.001 to 0.32)', 'Rare (0.0001 to 0.001)', 'Junk (below 0.0001)'],
        grp(tb), grp(tail['tmass']), grp(tail['mass'])))

    # ---- K4 grids ----
    A1 = k4_arms(f'{H}/k4/k4_summary.json', {})
    A1 = {(f'{k[0]}:{k[1]}', k[2]): v for k, v in A1.items()}
    rows1 = [('40:vec_temp1.3_opt2_L40_neg', 'temperature vector, negated (L40)', 'Toward certainty'),
             ('44:vec_caa_L44_neg', 'contrastive vector, negated (L44)', 'Toward certainty'),
             ('40:vec_p0.25_opt2_L40', 'p ≈ 0.25 vector, mild sharpener (L40)', 'Toward certainty'),
             ('40:vec_temp1.3_opt2_L40', 'temperature vector (L40)', 'Toward uncertainty'),
             ('44:vec_caa_L44', 'contrastive "weird token" vector (L44)', 'Toward uncertainty'),
             ('44:vec_probe_s_L44', 'surprise probe direction (L44)', 'Toward uncertainty'),
             ('44:vec_probe_s_L44_neg', 'surprise probe direction, negated (L44)', 'Toward uncertainty'),
             ('40:vec_p0.25_opt2_L40_neg', 'p ≈ 0.25 vector, negated (L40)', 'Toward uncertainty')]
    rows1 += [(f'{L}:rand{i}', f'random direction {i + 1} (L{L})', 'Random') for L in (40, 44) for i in range(4)]
    rows1 += [('44:vec_rand_L44', 'S2 random direction (L44)', 'Random'), ('44:vec_rand_L44_neg', 'S2 random direction, negated (L44)', 'Random')]
    g1 = dose_grid(A1, rows1, [0.25, 0.5, 0.75, 1, 1.5, 2, 3], 'cap-k4')
    A2 = k4_arms(f'{H}/k4/k4b_summary.json', {})
    A2 = {(k[1], k[2]): v for k, v in A2.items()}
    rows2 = [('vec_caa_L32_neg', 'contrastive vector, negated', 'Toward certainty'), ('vec_caa_L32', 'contrastive "weird token" vector', 'Toward uncertainty')]
    rows2 += [(f'rand{i}', f'random direction {i + 1}', 'Random') for i in range(4)]
    g2 = dose_grid(A2, rows2, [0.01, 0.02, 0.05, 0.1, 0.25, 0.5], 'cap-k4b')
    free_tok, free_ctx, tf_pos = exposure_totals()

    page = TEMPLATE
    subs = {
        '@@CHART_S1@@': c_s1, '@@CHART_MEM@@': c_mem, '@@CHART_S2@@': c_s2, '@@CHART_SWEEP@@': c_sweep,
        '@@SWEEP_TABLE@@': sweep_table,
        '@@SWEEP_STATUS@@': ('The sweep is complete.' if sweep_done else
                             'The sweep is still running; rows marked with a layer count are partial, and this report is regenerated when it finishes.'),
        '@@CHIP_SWEEP@@': ('<span class="chip m">Complete</span>' if sweep_done else '<span class="chip p">In progress</span>'),
        '@@LATE_BULLETS@@': late_bullets(sw, names),
        '@@CSS_COLORS@@': css_colors(),
        '@@WT_ROWS@@': ''.join(wt_rows), '@@LAD_ROWS@@': ''.join(lad_rows), '@@FX_ROWS@@': ''.join(fx_rows),
        '@@TAIL_ROWS@@': tail_rows, '@@GRID_K4@@': g1, '@@GRID_K4B@@': g2,
        '@@EXPO@@': f'{free_tok:,} generated tokens across {free_ctx:,} contexts in free-running perturbed states (K4, K4b), and {tf_pos / 1e6:.1f} million positions processed under teacher-forced steering (S2(c) sweep, S2(d))',
    }
    for k, v in subs.items():
        page = page.replace(k, v)
    with open(out_path, 'w') as f:
        f.write(page)
    print('wrote', out_path, '| sweep groups:', {k: len(v['pts']) for k, v in sw.items()})


def late_bullets(sw, names):
    """One bullet per band: the late-layer (>= 40) peak against the best global temperature."""
    out = []
    for k in ['p0.5', 'p0.25', 'p0.1', 'p0.03']:
        if k not in sw:
            continue
        late = [(L, v) for L, v in sw[k]['pts'] if L >= 40]
        if not late:
            continue
        bL, bv = max(late, key=lambda t: t[1])
        bt = sw[k]['best_T_frac'] + 0.0
        bt = 0.0 if abs(bt) < 0.05 else bt  # avoid printing -0.0
        if bv > bt + 2:
            cmp = ('above the best global temperature (%.1f%%): a small effect beyond temperature. It may be bias toward particular '
                   'token types close to the output head; the within-token test in S2(d) checks this for the layer-%d vector.' % (bt, bL))
        elif bv >= bt - 2:
            cmp = 'about the same as the best global temperature (%.1f%%), consistent with a temperature-like vector.' % bt
        else:
            cmp = 'below the best global temperature (%.1f%%).' % bt
        out.append(f'<li><strong>{esc(names[k][0])}, layers 40 to 60:</strong> peak {bv:.1f}% at layer {bL}, {cmp}</li>')
    return '\n'.join(out)


def css_colors():
    light = ' '.join(f'--c-{k.replace(".", "")}: {v[0]};' for k, v in COLORS.items())
    dark = ' '.join(f'--c-{k.replace(".", "")}: {v[1]};' for k, v in COLORS.items())
    cls = '\n'.join(f'.c-{k.replace(".", "_")} {{ stroke: var(--c-{k.replace(".", "")}); }} '
                    f'.f-{k.replace(".", "_")} {{ fill: var(--c-{k.replace(".", "")}); }} '
                    f'.b-{k.replace(".", "_")} {{ background: var(--c-{k.replace(".", "")}); border-color: var(--c-{k.replace(".", "")}); }}'
                    for k in COLORS)
    return (f':root {{ {light} }}\n@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ {dark} }} }}\n'
            f':root[data-theme="dark"] {{ {dark} }}\n{cls}')


TEMPLATE = r'''<title>Surprise and Steering in GLM-4</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,500;6..72,600&family=Source+Sans+3:ital,wght@0,400;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: one reading column (~68ch) with full-width charts; same family as the program's proposals. */
:root {
  --bg: #f4f6f8; --surface: #e9edf2; --fg: #18202b; --muted: #586374; --rule: #d3d9e1; --accent: #2b5c8e;
  --measured: #2d7652; --measured-bg: #e0efe6; --proposed: #87570f; --proposed-bg: #f4e8d4;
  --font-display: "Newsreader", "Iowan Old Style", Georgia, serif;
  --font-body: "Source Sans 3", "Segoe UI", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
  --step-0: 1.0625rem; --step-1: 1.25rem; --step-2: 1.6rem; --step-3: 2.6rem;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #11151b; --surface: #1a2029; --fg: #e3e7ed; --muted: #9aa4b3; --rule: #2b333f; --accent: #84b2e2;
    --measured: #7cc8a0; --measured-bg: #1b3127; --proposed: #e0b46c; --proposed-bg: #392d19;
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #11151b; --surface: #1a2029; --fg: #e3e7ed; --muted: #9aa4b3; --rule: #2b333f; --accent: #84b2e2;
  --measured: #7cc8a0; --measured-bg: #1b3127; --proposed: #e0b46c; --proposed-bg: #392d19;
  color-scheme: dark;
}
@@CSS_COLORS@@
body { background: var(--bg); color: var(--fg); font-family: var(--font-body); font-size: var(--step-0); line-height: 1.6; }
.wrap { max-width: 46rem; margin: 0 auto; padding-inline: 20px; padding-block: 32px 72px; }
article { min-width: 0; }
.eyebrow { font: 500 0.75rem var(--font-mono); letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); margin: 0 0 6px; }
h1 { font-family: var(--font-display); font-weight: 600; font-size: var(--step-3); line-height: 1.1; margin: 0 0 12px; text-wrap: balance; }
.deck { font-size: var(--step-1); color: var(--muted); margin: 0 0 18px; line-height: 1.45; }
.meta { display: flex; flex-wrap: wrap; gap: 6px 18px; font: 0.8rem var(--font-mono); color: var(--muted); margin: 0 0 8px; padding: 0; list-style: none; }
h2 { font-family: var(--font-display); font-weight: 600; font-size: var(--step-2); line-height: 1.2; margin: 44px 0 10px; padding-top: 18px; border-top: 1px solid var(--rule); text-wrap: balance; }
h3 { font-family: var(--font-body); font-weight: 600; font-size: var(--step-1); margin: 26px 0 6px; }
p, ul, ol { margin: 0 0 14px; }
ul, ol { padding-left: 1.3em; }
li { margin: 0 0 6px; }
li::marker { color: var(--muted); }
strong { font-weight: 600; }
.chip { display: inline-block; font: 500 0.7rem var(--font-mono); letter-spacing: 0.06em; text-transform: uppercase; padding: 2px 7px; border-radius: 3px; vertical-align: 0.35em; margin-left: 8px; }
.chip.m { color: var(--measured); background: var(--measured-bg); }
.chip.p { color: var(--proposed); background: var(--proposed-bg); }
.key { background: var(--surface); border-radius: 4px; padding: 14px 18px 4px; margin: 0 0 16px; }
.key ol { margin: 0 0 10px; }
code { font-family: var(--font-mono); font-size: 0.86em; background: var(--surface); padding: 1px 4px; border-radius: 3px; overflow-wrap: anywhere; }
.table { overflow-x: auto; margin: 0 0 16px; }
table { border-collapse: collapse; width: 100%; min-width: 36rem; font-size: 0.93rem; font-variant-numeric: tabular-nums; }
th, td { text-align: left; vertical-align: top; padding: 7px 10px; border-bottom: 1px solid var(--rule); }
th { font: 500 0.72rem var(--font-mono); letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
figure { margin: 6px 0 22px; }
figcaption { font-size: 0.92rem; color: var(--muted); margin-top: 4px; }
.chart { overflow-x: auto; }
.chart svg { display: block; width: 100%; min-width: 520px; height: auto; font-family: var(--font-mono); }
.grid { stroke: var(--rule); stroke-width: 1; fill: none; }
.grid.zero { stroke: var(--muted); stroke-width: 1; }
.axis { stroke: var(--muted); stroke-width: 1; fill: none; }
.tick { fill: var(--muted); font-size: 12px; }
.label { fill: var(--fg); font-size: 12.5px; }
.hlabel { font-size: 11.5px; }
.href { stroke-width: 1.2; stroke-dasharray: 5 4; fill: none; }
.line { fill: none; stroke-width: 2.2; stroke-linejoin: round; stroke-linecap: round; }
.line.dash { stroke-dasharray: 6 5; }
.legend { list-style: none; padding: 0; margin: 8px 0 0; display: flex; flex-wrap: wrap; gap: 4px 18px; font-size: 0.9rem; color: var(--muted); }
.legend li { display: flex; align-items: center; gap: 7px; margin: 0; }
.sw { display: inline-block; width: 18px; height: 3px; border-radius: 2px; }
.sw.dashsw { height: 0; border-top: 3px dashed; background: none !important; }
.credits { color: var(--muted); font-size: 0.95rem; }
.gridchart svg { min-width: 560px; }
.glabel { fill: var(--fg); font-size: 12px; font-weight: 500; font-family: var(--font-body); }
.rlabel { fill: var(--muted); font-size: 11.5px; font-family: var(--font-body); }
.gbg { fill: var(--surface); }
.gstop { fill: none; stroke: var(--rule); stroke-dasharray: 3 3; }
.gkey { display: flex; flex-wrap: wrap; gap: 4px 18px; font-size: 0.9rem; color: var(--muted); list-style: none; padding: 0; margin: 6px 0 0; }
.gkey li { display: flex; align-items: center; gap: 7px; margin: 0; }
.gkey i { display: inline-block; width: 14px; height: 10px; border-radius: 2px; }
@media (max-width: 480px) { :root { --step-3: 2.1rem; --step-2: 1.4rem; } }
</style>

<div class="wrap">
<article>
  <p class="eyebrow">Results &middot; homeostasis in base models</p>
  <h1>Surprise and Steering in GLM-4</h1>
  <p class="deck">What a base model tracks about its own surprise, how it responds to it, and what can be steered on the "how likely is the next token" axis, and how steering breaks it. Experiments S1 to S2(d), a 61-layer optimizer sweep, and loop-margin tests K4 and K4b.</p>
  <ul class="meta">
    <li>2026-10-13 to 14</li>
    <li>GLM-4-32B-Base-32K, Q4_K_S, one RTX 3090</li>
    <li>All numbers are held-out unless stated</li>
  </ul>

  <h2>Key findings</h2>
  <div class="key">
  <ol>
    <li><strong>The model keeps a graded, linearly readable record of how surprising the last token was.</strong> On forced tokens, held-out R² reaches 0.895 at layer 44, with r = 0.96 between tokens forced into the same context. A token-embedding baseline gets R² 0.34. The coding is graded across about ten orders of magnitude of probability; it is not a junk-token flag.</li>
    <li><strong>It also tracks a slow, document-level "how predictable is this text" variable</strong> (R² 0.72), and the part of a token's surprise it did not expect (surprisal minus entropy, within-token r = 0.47).</li>
    <li><strong>Its first response to a surprise is to widen its predictions.</strong> Next-token entropy rises from 0.6 nats after a likely forced token to 5.6 nats after one with p &lt; 1e-10. A steering vector built from this state works as a two-way temperature dial.</li>
    <li><strong>Reading is not writing.</strong> Steering along the surprise probe's readout direction has no directional effect.</li>
    <li><strong>On the probability axis, steering gives temperature plus one more shape, and no band dial.</strong> No contrastive, bracketed, logit-band or backprop-optimized vector promotes tokens of a chosen probability level, at any layer, including a search constrained to doses of 0.5 to 2× the residual norm. Late layers add one shape beyond temperature: at the same average surprise, a vector moves probability from the top token into plausible alternatives and leaves the junk tail alone, like truncation followed by temperature. Vectors trained for different bands make the same shape.</li>
    <li><strong>Steering breaks the model in two ways, and the direction decides which.</strong> Pushing toward certainty makes it loop: phrase loops when one layer is steered, "the the the" when a band of layers is. Random directions and pushes toward uncertainty make it incoherent instead. Random single-layer directions reach incoherence at 1 to 3× the residual norm and essentially never loop.</li>
  </ol>
  <p>For homeostasis this means the model has a sensor (findings 1 and 2), but its first response to a deviation is positive feedback (finding 3). The actuators found on this axis are a global temperature dial and a plausible-tail shape (findings 4 and 5). The healthy regime sits between two traps on the temperature axis: loops on the certain side, incoherence on the uncertain side (finding 6). Whether anything later restores the slow surprise level after a kick is the open question for the kick test (K1).</p>
  </div>

  <h2>Setup</h2>
  <ul>
    <li><strong>Model:</strong> GLM-4-32B-Base-32K at Q4_K_S (61 layers, residual width 6144, vocabulary 151,343). One model and one quantization throughout. It was chosen because it seems well adjusted in long looming sessions.</li>
    <li><strong>Text:</strong> 192 rollouts of about 2,000 tokens each, sampled at temperature 1. They were generated with llama-server's default min_p = 0.05 (see Caveats).</li>
    <li><strong>Tools:</strong> a llama.cpp fork with tools for capture with KV-cache branching (<code>homeo-capture</code>), exact steered distributions (<code>homeo-steer</code>), band-sampled branches (<code>homeo-band</code>), and a backprop steering optimizer built on a hand-written GLM-4 graph with ggml backward (<code>homeo-steeropt</code>).</li>
  </ul>

  <h2>S1: Does the model represent "the last token was unlikely"? <span class="chip m">Measured</span></h2>
  <h3>Method</h3>
  <ul>
    <li><strong>Forced set (56,440 samples):</strong> at sampled positions, branch the KV cache and decode one token from each of 12 log10-probability bins at the same position.</li>
    <li><strong>Natural set (96,962 samples):</strong> the rollouts' own tokens.</li>
    <li><strong>Targets:</strong> surprisal <var>s</var>, the previous step's entropy <var>H</var>, the unexpected part <var>s</var> − <var>H</var> (which has zero mean given the prefix, so nothing computed before the token can predict it), log rank, and surprisal <var>k</var> tokens back.</li>
    <li><strong>Probes:</strong> ridge regression at every 4th layer, 5 folds split by document (64 documents).</li>
    <li><strong>Controls:</strong> a token-embedding baseline; within-context correlation (same prefix, different forced tokens); within-token correlation (the same token in different contexts).</li>
  </ul>
  <h3>Results</h3>
  <figure>
    @@CHART_S1@@
    <figcaption>Held-out R² of linear probes by layer. Forced-token surprisal peaks at 0.895 at layer 44. The dashed line is the token-embedding baseline on the forced set (on natural text the embedding baseline is 0.02).</figcaption>
  </figure>
  <ul>
    <li><strong>Graded and calibrated.</strong> At layer 44, per-bin mean predictions track true surprisal from about 4 to 27 nats; the lowest bin is overestimated by about 1 nat. Within each single bin, the prediction still correlates with exact surprisal (r = 0.12 to 0.40 in all 12 bins).</li>
    <li><strong>Natural text.</strong> R² 0.645 at layer 44 against 0.02 for the embedding. For the same token in different contexts, r = 0.78 (embedding: −0.20). The unexpected part <var>s</var> − <var>H</var> is still decodable within token at r = 0.47. Because <var>H</var> itself is decodable (R² 0.78), the forced within-context result is the clean evidence.</li>
    <li><strong>Transfer between sets is partial.</strong> A probe trained on forced tokens keeps the ordering on natural text (r = 0.52 at layer 44; natural to forced r = 0.81) but not the scale (negative R²). The two regimes share part of the readout direction, not its calibration.</li>
  </ul>
  <h3>A surprising token makes the model uncertain</h3>
  <div class="table"><table>
    <thead><tr><th>Forced token's probability</th><th>p &gt; 0.3</th><th>p ≈ 1e-2</th><th>p ≈ 1e-5</th><th>p &lt; 1e-10</th></tr></thead>
    <tbody><tr><td>Mean next-token entropy (nats)</td><td>0.6</td><td>1.4</td><td>2.5</td><td>5.6</td></tr></tbody>
  </table></div>
  <h3>How long the model remembers being surprised</h3>
  <figure>
    @@CHART_MEM@@
    <figcaption>R² of surprisal <var>k</var> tokens back, decoded from the state at layer 44 on natural text. It falls quickly over 3 tokens, then flattens at about 0.22.</figcaption>
  </figure>
  <p>The floor is the document's surprise level. The mean surprisal over the 64 tokens before position <var>t</var> − 32 is decodable from the current state with R² 0.715, and on its own it explains the surprisal at <var>t</var> − 32 with r² 0.25. The model tracks a slow "how predictable is this text" variable.</p>

  <h2>S2: Steering the surprise state <span class="chip m">Measured</span></h2>
  <h3>Method</h3>
  <ul>
    <li>Exact next-token distributions at 2,024 positions in 8 rollouts. A vector is added at one layer, with scale in units of the mean residual norm (354 at layer 44, 120 at layer 32).</li>
    <li>Each steered distribution is compared with the temperature-scaled distribution that has the same mean surprisal.</li>
    <li>Vectors: a contrastive "just saw a weird token" vector (mean state after forced tokens with p &lt; 1e-8, minus mean state after tokens with p &gt; 0.1); the S1 probe's readout direction (cosine with the contrastive vector: 0.16); a random direction of the same norm.</li>
  </ul>
  <h3>Results</h3>
  <figure>
    @@CHART_S2@@
    <figcaption>Mean next-token surprisal under steering. Unsteered: 0.705 nats. The contrastive vector moves it both ways; the probe direction and the random direction raise it for both signs, which is generic damage.</figcaption>
  </figure>
  <div class="table"><table>
    <thead><tr><th>Contrastive vector, L44</th><th>Mean surprisal</th><th>Matched temperature</th><th>KL to unsteered</th><th>KL to matched temperature</th></tr></thead>
    <tbody>
      <tr><td>−0.25</td><td>0.575</td><td>0.85</td><td>0.042</td><td>0.024</td></tr>
      <tr><td>+0.25</td><td>1.116</td><td>1.29</td><td>0.090</td><td>0.024</td></tr>
      <tr><td>+0.5</td><td>2.973</td><td>1.67</td><td>0.940</td><td>0.188</td></tr>
    </tbody>
  </table></div>
  <ul>
    <li><strong>Mostly a temperature knob.</strong> For positive scales, the matched temperature accounts for 73 to 80% of the divergence from the unsteered distribution. The argmax is kept about as often as under a random push of the same size.</li>
    <li><strong>Beyond −0.25 the dial breaks:</strong> at −0.5, mean surprisal rises again (0.652), a sign of damage.</li>
    <li>The only extra beyond temperature is a mild excess of mid-range probability mass (p between 1e-6 and 1e-3) at +0.5, not separated from token-class bias.</li>
    <li>This is the causal side of the S1 entropy result: writing the surprise state raises the model's uncertainty.</li>
  </ul>

  <h2>S2b: A vector per probability level <span class="chip m">Measured</span></h2>
  <p>Question: is there a steering vector that makes the model favor tokens of one probability level <var>p</var>, and only those?</p>
  <h3>Method</h3>
  <ul>
    <li>384 prefixes from the rollouts, each continued in several arms: a normal arm at temperature 1, and band arms for <var>P</var> in {0.8, 0.5, 0.25, 0.1, 0.03, 0.01} that sample among tokens with <var>p</var> in [<var>P</var>/1.5, 1.5<var>P</var>] when any exist, and sample normally otherwise. 32 steps per arm; the last 24 are captured.</li>
    <li>Band tokens are often unavailable: one exists at 26% of steps for <var>P</var> = 0.25, 34% for 0.1, and 47% for 0.03.</li>
    <li>Two vectors per level: band minus normal; and a bracket vector, band minus its neighbor bands weighted so the neighbors' realized surprisal matches. The bracket cancels anything linear in surprisal.</li>
  </ul>
  <h3>Results</h3>
  <ul>
    <li><strong>Band minus normal is just the surprise axis.</strong> It is reliable only for <var>P</var> ≤ 0.03 (split-half cosine above 0.8), where it matches the S1 surprise vector (cosine 0.75 to 0.84). For <var>P</var> ≥ 0.5 it is the negative surprise vector (−0.6 to −0.7). For <var>P</var> = 0.25 it is noise.</li>
    <li><strong>Bracket vectors are noise</strong> at every level and layer (split-half cosine −0.1 to 0.2). Once surprise is controlled, band-sampled text has no reliable activation signature.</li>
    <li><strong>No vector promotes only its band</strong> (layer 40, exact distributions). Raising the target band always comes with equal or larger changes elsewhere:</li>
  </ul>
  <div class="table"><table>
    <thead><tr><th>Vector</th><th>Target band</th><th>Matched temperature</th><th>Other bands</th></tr></thead>
    <tbody>
      <tr><td>p ≈ 0.5 at +0.2</td><td>×1.12</td><td>×1.14 (T = 0.87)</td><td></td></tr>
      <tr><td>p ≈ 0.25 at +0.4</td><td>×1.07</td><td>×1.04</td><td>0.1: ×1.14; 0.03: ×1.22</td></tr>
      <tr><td>p ≈ 0.1 at +0.4</td><td>×1.10</td><td>×1.02</td><td>0.03: ×1.48; 0.01: ×1.99</td></tr>
      <tr><td>p ≈ 0.03 at +0.4</td><td>×1.64</td><td>×1.39</td><td>0.01: ×2.37</td></tr>
    </tbody>
  </table></div>
  <p>Bracket vectors stay within about 3% of their temperature match up to +0.2, and at +0.4 raise the tails like a random push.</p>

  <h2>S2c: Bands on raw logits instead of probabilities <span class="chip m">Measured</span></h2>
  <ul>
    <li>Raw logits at 4,048 positions over the full vocabulary. The top logit has median 25.1 (5 to 95%: 17.2 to 30.1), so a fixed logit band maps to very different probabilities in different contexts.</li>
    <li><strong>Context, not token identity, decides band membership.</strong> For every band that holds real probability (roughly the top 40 tokens), a token in the band at one position is in the same band at a random other position only 0 to 3% of the time. No token is in-band at half or more of positions.</li>
    <li>Token identity explains 47% of raw-logit variance over the whole vocabulary, but that is the junk tail that is always low.</li>
    <li>Conclusion: within a context, logit order equals probability order, and there is no fixed set of tokens a bias vector could target. Logit bands face the same problem as probability bands.</li>
  </ul>

  <h2>S2(c): A vector optimized through the model <span class="chip m">Measured</span></h2>
  <h3>Method</h3>
  <ul>
    <li>A learnable vector added after one layer at every position. Loss: cross-entropy against a target distribution proportional to <var>p</var> · (1 + 3 · [token in band]), that is, band tokens ×4 and everything else in proportion.</li>
    <li>Backward runs through the later layers and the output head; Adam on the host. 48 training and 16 held-out windows of 128 tokens, split by document.</li>
    <li>Positive control: the same optimizer with a temperature-1.3 target.</li>
    <li>Score: the fraction of the held-out gap closed, between no vector and the best achievable (the target's entropy).</li>
    <li>Gradient check: finite-difference to analytic ratio 1.11, 0.88 and 0.50 at step sizes 8, 16 and 32. Large steps add curvature; small steps hit 8-bit activation rounding.</li>
  </ul>
  <h3>At layer 40 (200 steps)</h3>
  <div class="table"><table>
    <thead><tr><th>Target</th><th>No vector</th><th>Best temperature</th><th>Optimized vector</th><th>Floor</th></tr></thead>
    <tbody>
      <tr><td>Temperature 1.3 (control)</td><td>2.553</td><td>2.380</td><td>2.429 (72% of gap)</td><td>2.380</td></tr>
      <tr><td>p ≈ 0.5</td><td>1.1235</td><td>1.1125 (T = 0.90)</td><td>1.1163 at step 50, 1.1194 at 200</td><td>1.0705</td></tr>
      <tr><td>p ≈ 0.25</td><td>1.2113</td><td>1.2077 (T = 0.95)</td><td>1.2189</td><td>1.1459</td></tr>
      <tr><td>p ≈ 0.1</td><td>1.3195</td><td>1.3195 (T = 1.00)</td><td>1.3259</td><td>1.2397</td></tr>
      <tr><td>p ≈ 0.03</td><td>1.4265</td><td>1.4255 (T = 1.05)</td><td>1.4248 at step 50, 1.4285 at 200</td><td>1.3613</td></tr>
    </tbody>
  </table></div>
  <p>Held-out cross-entropy in nats. The best single temperature matches or beats the optimized vector for every band. Exact evaluation agrees: the p ≈ 0.5 vector is a sharpener (its band ×1.12, the same as its matched temperature), the p ≈ 0.03 vector flattens with a tail bias, and the p ≈ 0.25 and 0.1 vectors do almost nothing.</p>

  <h3>Across all 61 layers @@CHIP_SWEEP@@</h3>
  <p>60 steps per layer, gradient accumulation 4, learning rate 0.006 × the layer's mean residual norm, held-out evaluation at steps 30 and 60. The temperature control ran at every 10th layer; bands p ≈ 0.25 and 0.1 at every layer, p ≈ 0.5 and 0.03 at every 4th layer.</p>
  <figure>
    @@CHART_SWEEP@@
    <figcaption>Held-out gap closed at step 60. Triangles on the bottom edge mark layer-0 band runs that diverged, far below the chart. The temperature control rises from about 11% at layer 10 to 69% at layer 50; the band targets stay within a few percent of zero at every layer.</figcaption>
  </figure>
  <div class="table"><table>
    <thead><tr><th>Target</th><th>Best global temperature closes</th><th>Best layer (excluding 0)</th><th>Layer 0</th><th>Status</th></tr></thead>
    <tbody>@@SWEEP_TABLE@@</tbody>
  </table></div>
  <ul>
    <li><strong>Where the control works, the bands still fail.</strong> The temperature control closes 24% at layer 20, 43% at 30, 62% at 40 and 69% at 50. Over the same layers the band targets close about −4% to +3%.</li>
@@LATE_BULLETS@@
    <li><strong>Below about layer 15 the method is blind.</strong> The temperature control closes −14% at layer 0 and 11% at layer 10, so band nulls there say nothing yet. Layer 0 diverged for the band targets. The early layers need a retuned control before their band results count.</li>
    <li>@@SWEEP_STATUS@@</li>
  </ul>
  <p><strong>Conclusion, for small doses.</strong> In GLM-4-32B-Base, no single additive steering vector of up to about 0.5× the residual norm, at any tested layer, promotes only tokens of a given probability, or of a given raw logit. S2(d) tests large doses and explains the late-layer bump.</p>

  <h2>S2(d): Large doses <span class="chip m">Measured</span></h2>
  <p>In hands-on steering, a vector that seems to do nothing often just needs to be turned up much further. The S2(c) vectors stayed at 0.03 to 0.14× the residual norm, and gradient descent from zero would miss an effect that only appears past a hump. This experiment pushes doses far past the margin on purpose. All of it is teacher-forced: no text is generated in steered states.</p>
  <h3>Method</h3>
  <ul>
    <li><strong>Dose ladders:</strong> the optimized vectors at 1 to 64× their learned size (up to about 4 to 9× the residual norm), and the S2 and S2b vectors at up to 4×, each at a single layer.</li>
    <li><strong>Multi-layer steering:</strong> one direction added after every block from 24 to 40.</li>
    <li><strong>Fixed-dose search:</strong> the optimizer searches directions on a sphere of 0.5, 1 or 2× the residual norm, starting from a random direction and from the small learned vector.</li>
    <li><strong>Within-token test:</strong> for the late-layer band vectors, the top 64 tokens at each of 4,048 positions. It asks whether a boost depends on a token's probability in context or only on which token it is.</li>
  </ul>
  <h3>A second shape besides temperature</h3>
  <p>The layer-56 vector trained for p ≈ 0.03, at 4× its learned size (0.3× the residual norm), against exact temperature tuned per position to the same average surprise (T = 1.20). Share of samples by how likely the unsteered model thought the token was:</p>
  <div class="table"><table>
    <thead><tr><th>Token group</th><th>Unsteered</th><th>Temperature 1.20</th><th>Vector</th></tr></thead>
    <tbody>@@TAIL_ROWS@@</tbody>
  </table></div>
  <p>Temperature more than doubles the junk tail. The vector leaves it where it was and moves the mass into plausible alternatives instead, like truncation followed by temperature. Interactive version: <a href="https://claude.ai/artifact/6KuTYAQqyhGrXPjL1hYJ1y">Same Surprise, Different Tail</a>.</p>
  <p>The within-token test removes the best temperature line from each token's boost, then compares tokens in the band with the rest, both raw and within token (each token's mean across contexts subtracted). The temperature vector shows almost no band effect, as it should. The p ≈ 0.03 vector's effect survives within token, so it depends on contextual probability, not token identity. In nats:</p>
  <div class="table"><table>
    <thead><tr><th>Vector</th><th>Band</th><th>Band minus rest, raw</th><th>Within token</th></tr></thead>
    <tbody>@@WT_ROWS@@</tbody>
  </table></div>
  <p>It is a shape, not a dial. The p ≈ 0.1 vector makes a similar bump around p ≈ 0.01 to 0.03, not at 0.1, and its within-token band effect is gone at 16×.</p>
  <h3>Turning it up</h3>
  <div class="table"><table>
    <thead><tr><th>Size</th><th>Of residual norm</th><th>Band ≈ 0.03</th><th>Matched temperature</th><th>Band ≈ 0.01</th><th>KL to unsteered</th><th>Top token kept</th></tr></thead>
    <tbody>@@LAD_ROWS@@</tbody>
  </table></div>
  <p>The effect grows up to about 1× the residual norm, with the 0.01 band always rising more than the 0.03 band. Past about 1 to 2×, every vector tested destroys the output (KL above 10, top token almost never kept). Over layers 24 to 40, even 0.25× per layer destroys it.</p>
  <h3>Fixed-dose search</h3>
  <p>Held-out gap closed at the end of the search, as a range over the two starting points (negative: worse than adding no vector).</p>
  <div class="table"><table>
    <thead><tr><th>Target</th><th>0.5× residual norm</th><th>1×</th><th>2×</th></tr></thead>
    <tbody>@@FX_ROWS@@</tbody>
  </table></div>
  <p>At 0.5× the search still finds the temperature direction, but every band search ends worse than adding no vector. At 1× and 2× even the control mostly fails, so steering at those doses is mostly damage. There is no hidden large-dose band direction.</p>

  <h2>K4: Where the model loops <span class="chip m">Measured</span></h2>
  <p>Turned up far enough, steering vectors often make models loop, and heavy quantization often fails into loops too. That suggests not looping might be a maintained state, bounded by a repetition trap. K4 measures the dose at which the model falls into a loop.</p>
  <h3>Method</h3>
  <ul>
    <li>A direction added after one layer (40 or 44) at every position, from 0.25 to 3× the residual norm: the S2 and S2(c) vectors, their negations, and random directions.</li>
    <li>16 held-out prefixes of 256 tokens, then up to 128 tokens generated at temperature 1 with no truncation, with the same random numbers in every arm.</li>
    <li>Endpoints, following the Three Rs protocol: a sequence stops when it loops (period 16 or less, repeated over at least 12 tokens) or goes incoherent (entropy above 6 nats for 16 steps). A direction's ladder stops once 75% of sequences loop.</li>
  </ul>
  <figure>
    @@GRID_K4@@
    <ul class="gkey"><li><i class="b-p0_1"></i>share that looped</li><li><i class="b-p0_03"></i>share that went incoherent</li><li><i style="border:1px dashed var(--rule)"></i>not run (ladder stopped)</li></ul>
    <figcaption id="cap-k4">Each cell is 16 sequences at one dose; columns are multiples of the residual norm at the steered layer. Hover or tap a cell for its mean entropy.</figcaption>
  </figure>
  <ul>
    <li><strong>Random directions do not loop.</strong> Across 10 random directions, loops are essentially absent at every dose. The model goes incoherent instead, at 1 to 3× the residual norm, with entropy climbing to 8 to 9 nats.</li>
    <li><strong>Loops come from pushing toward certainty.</strong> The negated temperature vector loops in 75% of sequences at 1×, with entropy falling to 0.3 nats. The negated contrastive vector and the mildly sharpening p ≈ 0.25 vector also loop at 0.75 to 2×.</li>
    <li><strong>Single-layer loops are phrase-level</strong>, often with drift ("Black Nail with Glitter / Black Nail with Gliter"), not single-token spam.</li>
    <li><strong>Pushes toward uncertainty go incoherent soonest:</strong> the temperature and contrastive vectors at 0.5×.</li>
  </ul>

  <h2>K4b: Steering a band of layers <span class="chip m">Measured</span></h2>
  <p>Hand-made control vectors are usually applied across a band of layers. K4b adds one direction after every block from 24 to 40. Doses are per layer, as multiples of the residual norm at layer 24, and the ladder also stops after two doses in a row where most sequences hit any endpoint.</p>
  <figure>
    @@GRID_K4B@@
    <figcaption id="cap-k4b">Same encoding as K4. Columns: dose per layer, added at each of the 17 layers.</figcaption>
  </figure>
  <ul>
    <li><strong>Toward certainty gives "the the the".</strong> At 0.5 per layer, all 16 sequences of the negated contrastive vector collapse into single-token spam within three tokens. At 0.25 the text degrades and slides into "and, and, and,".</li>
    <li><strong>Random directions give multilingual mush</strong> ("ufc党和乐于 fair Tenqual roasted*num…") and almost never loop.</li>
  </ul>
  <div class="table"><table>
    <thead><tr><th>Direction</th><th>One layer</th><th>Layers 24 to 40</th></tr></thead>
    <tbody>
      <tr><td>Toward certainty</td><td>phrase loops</td><td>single-token spam</td></tr>
      <tr><td>Random, or toward uncertainty</td><td>incoherence</td><td>multilingual mush</td></tr>
    </tbody>
  </table></div>
  <p>Single-token spam fits a constant push at many layers flattening every position toward the same state. Phrase loops fit the model's copying machinery taking over. A guess for why hand-made vectors loop so often: concept vectors make the model more certain about the concept, so they carry a sharpening component and collapse onto the concept's words when turned up. That is testable by measuring a concept vector's component along the temperature axis and running it through K4.</p>

  <h2>Exposure log</h2>
  <p>Following the group's Three Rs protocol, every steered run is logged in <code>welfare_log.csv</code>. So far: @@EXPO@@. The free-running runs used humane endpoints, which cut most incoherent runs at about 16 tokens.</p>

  <h2>Caveats</h2>
  <ul>
    <li><strong>The rollouts are not pure ancestral samples.</strong> They used llama-server's default min_p = 0.05. Measured: mean surprisal 0.51 nats against mean entropy 0.70 (these are equal for true samples), and only 0.15% of tokens above 5 nats. This affects the S1 natural set and the S2b prefixes; the forced set is unaffected. New rollouts need min_p = 0.</li>
    <li><strong>Batch shape changes the numerics.</strong> Branch decodes and full passes differ by a median 1.5 to 2% in the residual stream (99th percentile 3 to 15%), and by a median 0.001 nats in next-token entropy. Comparisons between branches must use matched batch shapes.</li>
    <li><strong>Quantization.</strong> Q4_K_S weights and 8-bit activation rounding limit finite-difference checks to step sizes of 16 or more.</li>
    <li><strong>Doses.</strong> S2 to S2(c) used small doses (up to 0.5× the residual norm). S2(d) tested large doses separately and found no band direction there either. Its multi-layer ladder started too high (0.25 per layer already destroys the output), so K4b used much lower doses.</li>
    <li><strong>K4 sampling.</strong> Temperature 1, no truncation, no repetition penalty. Hands-on setups (lower temperature, top-p, penalties) shift the balance between loops and incoherence. With 16 prefixes, fractions are resolved to 1/16.</li>
    <li><strong>One model, linear tools.</strong> Probes and steering vectors are linear and position-independent. The steering nulls do not exclude nonlinear or position-dependent mechanisms.</li>
    <li><strong>Optimizer settings.</strong> The sweep uses 60 steps per layer (the layer-40 run used 200; its control reached 62% at step 60 against 72% at step 200).</li>
  </ul>

  <h2>What comes next</h2>
  <ul>
    <li><strong>Concept vectors and loops:</strong> build a concept vector on GLM, measure its component along the temperature axis, and run it through K4 and K4b.</li>
    <li><strong>K1, kick test:</strong> does the slow surprise level return after a forced surprising token faster than evidence alone predicts? Needs fresh rollouts with min_p = 0.</li>
    <li><strong>The value lens:</strong> pricing directions by their effect on future predictability, with candidate good states as its first readout (protocol amendment A5).</li>
  </ul>

  <h2>Where things are</h2>
  <ul>
    <li>Data: <code>/mnt/models/homeo/</code> (<code>s1</code>, <code>s2</code>, <code>s2b</code>, <code>band2</code>, <code>logits</code>, <code>s2opt</code>, <code>s2sweep</code>, <code>s2big</code>, <code>k4</code>)</li>
    <li>Analysis: <code>homeo/s1_probe.py</code>, <code>s2_make_vecs.py</code>, <code>s2b_band_vecs.py</code>, <code>s2b_summarize.py</code>, <code>s2c_logit_identity.py</code>, <code>s2sweep_summary.py</code>, <code>s2d_within_token.py</code>, <code>k4_loop_summary.py</code>, <code>log_tf_exposure.py</code>; this report: <code>homeo/results_report.py</code></li>
    <li>Tools: <code>llama.cpp/tools/homeo/</code> and <code>llama.cpp/tools/jspace/</code></li>
    <li>Running notes: <code>NOTES-homeostasis.md</code></li>
  </ul>
  <p class="credits">Experiments run and report drafted by Claude (Opus 5.5) in collaboration. This is a working report to base an official write-up on.</p>
</article>
</div>
'''

if __name__ == '__main__':
    main()
