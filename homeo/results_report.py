#!/usr/bin/env python3
"""Build the S1-S2(d), K4/K4b and VL1/VL2 results report (HTML with inline SVG charts) from the result files.

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
    subs.update(value_sections())
    subs.update(lean_section())
    subs.update(vl4_section())
    for k, v in subs.items():
        page = page.replace(k, v)
    assert '@@' not in page, re.findall(r'@@\w+@@', page)
    with open(out_path, 'w') as f:
        f.write(page)
    print('wrote', out_path, '| sweep groups:', {k: len(v['pts']) for k, v in sw.items()})


def value_sections():
    """VL1 (value lens) and VL2 (value probe) tables and the lag chart."""
    V = json.load(open(f'{H}/value/summary_clean.json'))
    lag = None
    for f in glob.glob(f'{H}/value/w*.json'):
        a = json.load(open(f))['lag_norm']
        lag = a if lag is None else [x + y for x, y in zip(lag, a)]
    n = len(glob.glob(f'{H}/value/w*.json'))
    lag = [x / n for x in lag]
    c_lag = line_chart([dict(name='Mean |∂l(s+k) / ∂h(s)| at layer 40', color='temp', markers=True, pts=list(enumerate(lag)))],
                       (0, 32), (0, 0.16), [0, 4, 8, 12, 16, 20, 24, 28, 32], [0, 0.04, 0.08, 0.12, 0.16],
                       'Lag k (tokens ahead)', 'Gradient size', yfmt='{:.2f}')
    lib = V['library']
    show = [('temperature 1.3, optimized (S2(c))', 'Temperature 1.3, optimized'), ('temperature 1.3, sweep (L50)', 'Temperature 1.3, sweep'),
            ('band p~0.5, optimized', 'Band p ≈ 0.5, optimized'), ('band p~0.25, optimized', 'Band p ≈ 0.25, optimized'),
            ('band p~0.1, optimized', 'Band p ≈ 0.1, optimized'), ('band p~0.03, optimized', 'Band p ≈ 0.03, optimized'),
            ('plausible-tail (p~0.03 sweep, L56)', 'Plausible-tail shape (S2(d))'),
            ('contrastive "weird token" (S2)', 'Contrastive "weird token"'), ('surprise probe direction (S2)', 'Surprise probe direction')]
    rows = []
    for k, label in show:
        d = lib[k]
        rows.append(f'<tr><td>{esc(label)}</td><td>{d["layer"]}</td><td>{d["now"]["mean_per_0p1"]:+.4f}</td>'
                    f'<td>{d["fut"]["mean_per_0p1"]:+.4f}</td><td>{d["fut"]["t"]:+.1f}</td><td>{d["fut"]["sd_ratio_vs_random"]:.2f}</td></tr>')
    rows.append('<tr><td>Random directions (32 per layer)</td><td>40 to 56</td><td></td><td>|mean| 0.0001 to 0.0002 (max 0.0012)</td><td></td><td>1</td></tr>')
    st = V['structure']
    scen = {}
    for line in open(f'{H}/value_scen/summary.txt'):
        m = re.match(r'\s+(.+?)\s{2,}(\d+)\s+([-+0-9. ]+)$', line)
        if m:
            scen[m.group(1).strip()] = (int(m.group(2)), [float(x) for x in m.group(3).split()])
    sl = [('fineweb, all', 'Fineweb, all'), ('fineweb, easiest tenth (boring)', 'Fineweb, easiest tenth ("boring")'),
          ('fineweb, hardest tenth', 'Fineweb, hardest tenth'), ('fiction (model-written)', 'Fiction, model-written'),
          ('paired fineweb, same positions', 'Same text without the loop'), ('phrase loop (period 12)', 'Phrase loop (period 12)'),
          ('token loop ("the the the")', 'Token loop ("the the the")')]
    srows = []
    for k, label in sl:
        nn, v = scen[k]
        loop = 'loop' in k or 'paired' in k
        b = '<strong>' if 'loop' in k else ''
        e = '</strong>' if b else ''
        srows.append(f'<tr><td>{esc(label)}{" †" if loop else ""}</td><td>{nn}</td><td>{v[0]:.2f}</td><td>{b}{v[1]:.3f}{e}</td>'
                     f'<td>{v[2]:.3f}</td><td>{b}{v[3]:+.3f}{e}</td></tr>')
    PR = json.load(open(f'{H}/value_probe/probe.json'))
    RB = json.load(open(f'{H}/value/structure_robust.json'))
    FC = json.load(open(f'{H}/value_probe/forecast_L40.json'))
    pl = [('stakes', 'Stakes, log |g_fut|'), ('now', 'log |g_now|'), ('temp fut', 'Temperature price, fut'),
          ('temp now', 'Temperature price, now'), ('band fut', 'Band p ≈ 0.5 price, fut'), ('pc1', 'g_fut along its top direction'),
          ('level', 'Log-probability of the actual next token'), ('entropy', 'Next-token entropy (sanity check)')]
    prow = []
    for k, label in pl:
        b = '<strong>' if k == 'stakes' else ''
        e = '</strong>' if b else ''
        base = '1 (a feature)' if k == 'entropy' else f'{PR["base_r2"][k]:.2f}'.replace('-0.00', '0.00')
        f2 = lambda x: f'{x:.2f}'.replace('-0.00', '0.00')
        prow.append(f'<tr><td>{esc(label)}</td><td>{b}{f2(PR["test_r2"][k])}{e}</td><td>{f2(PR["test_r2_within"][k])}</td>'
                    f'<td>{base}</td><td>{f2(PR["tok_r2"][k])}</td></tr>')
    sc = PR['scenarios']
    orow = []
    for k, label in [('fineweb test windows', 'Fineweb test windows'), ('fiction', 'Fiction, model-written'),
                     ('phrase loop, loop region', 'Phrase loop †'), ('token loop, loop region', 'Token loop †')]:
        a_, p_ = sc[k]['mean']['stakes']
        na, np_ = sc[k]['mean']['now']
        orow.append(f'<tr><td>{esc(label)}</td><td>{sc[k]["n"]}</td><td>{a_:.2f}</td><td>{p_:.2f}</td><td>{na:.2f}</td><td>{np_:.2f}</td></tr>')
    return {
        '@@CHART_LAG@@': c_lag, '@@VL_LIB_ROWS@@': ''.join(rows), '@@VL_SCEN_ROWS@@': ''.join(srows),
        '@@VL_PROBE_ROWS@@': ''.join(prow), '@@VL_OOD_ROWS@@': ''.join(orow),
        '@@VL_POS@@': f'{V["positions"]:,}', '@@VL_COS@@': f'{st["cos_now_fut_median"]:+.3f}',
        '@@VL_FUT10@@': f'{st["fut"]["split_half_overlap"]["10"]:.2f}', '@@VL_FUT50@@': f'{st["fut"]["split_half_overlap"]["50"]:.2f}',
        '@@VL_NOW10@@': f'{st["now"]["split_half_overlap"]["10"]:.3f}', '@@VL_NOW50@@': f'{st["now"]["split_half_overlap"]["50"]:.2f}',
        '@@VL_SHARE10@@': f'{100 * st["fut"]["share_top"][1]:.1f}%',
        '@@VL_CORR@@': f'{V["contexts"]["corr_level_stakes"]:+.3f}',
        '@@VP_STAKES@@': f'{PR["test_r2"]["stakes"]:.2f}', '@@VP_TOK@@': f'{PR["tok_r2"]["stakes"]:.2f}',
        '@@VP_BASE@@': f'{PR["base_r2"]["stakes"]:.2f}',
        '@@VR_FUTN@@': f'{RB["fut"]["offset blocks / normalized"]["overlap"]["10"]:.2f}',
        '@@VR_NOWN@@': f'{RB["now"]["offset blocks / normalized"]["overlap"]["10"]:.2f}',
        '@@VR_FUTT@@': f'{RB["fut"]["offset blocks / trimmed"]["overlap"]["10"]:.2f}',
        '@@VR_NOWT@@': f'{RB["now"]["offset blocks / trimmed"]["overlap"]["10"]:.2f}',
        '@@VR_CONC_FUT@@': f'{100 * RB["fut"]["concentration"]["top 1%"]:.0f}%',
        '@@VR_CONC_NOW@@': f'{100 * RB["now"]["concentration"]["top 1%"]:.0f}%',
        '@@H2_ROWS@@': ''.join(f'<tr><td>Next {k.split()[1]} tokens</td><td>{FC[k]["base"]:.3f}</td><td>{FC[k]["probe"]:.3f}</td>'
                               f'<td>{FC[k]["combined"]:.3f}</td><td><strong>{FC[k]["added"]:+.3f}</strong></td></tr>' for k in ('next 8', 'next 32')),
    }


def lean_section():
    """H3 (lean test): gate and real-text fits from homeo/lean_fit.py (final fit if present, else block 1)."""
    f = f'{H}/lean/lean_fit.json'
    if not os.path.exists(f):
        f = f'{H}/lean/lean_fit_step1.json'
    L = json.load(open(f))
    grow = ''.join(f'<tr><td>{g["beta"]:+.2f}</td><td>{g["b_VB"]:+.3f}</td><td>{g["b_VA"]:+.3f}</td></tr>' for g in L['gate'])
    R = L['real']
    rl = [('V', 'Ease of the future (V)', 'b'), ('V + frequency + classes', '+ token frequency and classes', 'b'),
          ('V + token mean V (within-token)', "+ the token's own average V (within-token)", 'b'),
          ('V + all covariates', '+ all of these', 'b'), ('V1 + V_late', "Next step's entropy (fit jointly)", 'b1'),
          ('V1 + V_late', 'Steps 2 to 16 (fit jointly)', 'b_late'), ('realized surprisal instead of entropy', 'Realized surprisal instead of entropy', 'b')]
    rrow = []
    for k, label, par in rl:
        b, se = R[k]['theta'][par], R[k]['se'][par]
        strong = k == 'V' and par == 'b'
        rrow.append(f'<tr><td>{esc(label)}</td><td>{"<strong>" if strong else ""}{b:+.3f}{"</strong>" if strong else ""}</td>'
                    f'<td>{se:.3f}</td><td>{b / se:+.1f}</td></tr>')
    b, se = R['V']['theta']['b'], R['V']['se']['b']
    gb = {g['beta']: g['b_VB'] for g in L['gate']}
    f = f'{H}/lean/lean_copy.json'
    C = json.load(open(f if os.path.exists(f) else f'{H}/lean/lean_copy_step1.json'))['fits']
    cv, cn, cw = C['V + copy'], C['V, no candidate is a bigram copy'], C['V, some candidate is a bigram copy']
    return {
        '@@H3_GATE_ROWS@@': grow, '@@H3_REAL_ROWS@@': ''.join(rrow),
        '@@H3_POS@@': f'{L["n_positions"]:,}', '@@H3_WIN@@': f'{L["n_positions"] // 6:,}', '@@H3_USED@@': f'{L["n_used"]:,}',
        '@@H3_USEDPCT@@': f'{100 * L["n_used"] / L["n_positions"]:.0f}%', '@@H3_SDV@@': f'{L["sd_V_within"]:.2f}',
        '@@H3_SH@@': f'{L["split_half_r"]:.2f}', '@@H3_REL@@': f'{L["reliability_full"]:.2f}',
        '@@H3_B@@': f'{b:+.2f}', '@@H3_SE@@': f'{se:.2f}', '@@H3_LO@@': f'{b - 1.96 * se:+.2f}', '@@H3_HI@@': f'{b + 1.96 * se:+.2f}',
        '@@H3_PERSD@@': f'{b * L["sd_V_within"]:+.2f}', '@@H3_A@@': f'{R["V"]["theta"]["a"]:.2f}',
        '@@H3_G025@@': f'{gb[-0.25]:+.2f}', '@@H3_G05@@': f'{gb[-0.5]:+.2f}',
        '@@H3C_B@@': f'{cv["theta"]["b"]:+.2f}', '@@H3C_SE@@': f'{cv["se"]["b"]:.2f}',
        '@@H3C_WB@@': f'{cw["theta"]["b"]:+.2f}', '@@H3C_WBSE@@': f'{cw["se"]["b"]:.2f}',
        '@@H3_ST0@@': f'{L["strata"]["0-1"]["b"]:+.2f}', '@@H3_ST0SE@@': f'{L["strata"]["0-1"]["se_b"]:.2f}',
        '@@H3C_NB@@': f'{cn["theta"]["b"]:+.2f}', '@@H3C_NBSE@@': f'{cn["se"]["b"]:.2f}',
        '@@H3_NLL@@': f'{R["calibration only"]["nll"] - R["V"]["nll"]:.4f}',
        '@@H3_SD1@@': f'{R["V1 + V_late"]["theta"]["b1"] * L["sd_V1_within"]:+.3f}',
        '@@H3_SDL@@': f'{R["V1 + V_late"]["theta"]["b_late"] * L["sd_VL_within"]:+.3f}',
    }


def vl4_section():
    """VL4 (scenario set 2, all model-written) from homeo/value_scenarios2.py (final summary if present)."""
    f = f'{H}/value_scen2/summary.json'
    if not os.path.exists(f):
        f = f'{H}/value_scen2/summary_first96.json'
    S = json.load(open(f))
    G, M, D = S['groups'], S['matched'], S['diffs']
    labels = {'fiction': 'Fiction', 'boring': 'Boring prose', 'structured': 'Structured text'}
    rows = []
    for g in ('fiction', 'boring', 'structured'):
        r = G[g]
        m = M['groups'][g]
        rows.append(f'<tr><td>{labels[g]}</td><td>{r["prompts"]}</td><td>{r["windows"]}</td><td>{r["level"]["mean"]:.2f}</td>'
                    f'<td>{r["stakes"]["mean"]:.3f} ({r["stakes"]["se"]:.3f})</td><td><strong>{m["mean"]:+.3f}</strong> ({m["se"]:.3f})</td>'
                    f'<td>{m["corr_within"]:+.2f}</td></tr>')
    rows.append(f'<tr><td>Fineweb (human), for reference</td><td></td><td>1,200</td><td>{G["fineweb"]["level"]["mean"]:.2f}</td>'
                f'<td>{G["fineweb"]["stakes"]["mean"]:.3f}</td><td>0</td><td>{M["corr_fineweb"]:+.2f}</td></tr>')
    pf = lambda p: '&lt; 0.001' if p < 0.001 else f'{p:.3f}' if p < 0.01 else f'{p:.2f}'
    ex = []
    for g in ('structured', 'boring', 'fiction'):
        e = S['repetition'][g]['extremes']
        for side, items in (('lowest', e[:2]), ('highest', e[-2:][::-1])):
            for it in items:
                t = re.sub(r'\s*\n+\s*', ' / ', it['text'])[:100]
                ex.append(f'<tr><td>{labels[g]}</td><td>{side}</td><td>{it["stakes"]:.3f}</td><td>{esc(t)}…</td></tr>')
    return {
        '@@VL4_ROWS@@': ''.join(rows), '@@VL4_EX_ROWS@@': ''.join(ex), '@@VL4_N@@': str(S['n_windows']),
        '@@VL4_FB@@': f'{D["fiction - boring"]["stakes"]["diff"]:+.3f}', '@@VL4_FB_P@@': pf(D['fiction - boring']['stakes']['p']),
        '@@VL4_SB@@': f'{D["structured - boring"]["stakes"]["diff"]:+.3f}', '@@VL4_SB_P@@': pf(D['structured - boring']['stakes']['p']),
        '@@VL4_MSB@@': f'{M["diffs"]["structured - boring"]["diff"]:+.3f}', '@@VL4_MSB_P@@': pf(M['diffs']['structured - boring']['p']),
        '@@VL4_MB@@': f'{M["groups"]["boring"]["mean"]:+.3f}', '@@VL4_MS@@': f'{M["groups"]["structured"]["mean"]:+.3f}',
        '@@VL4_MB_LR@@': f'{M["low_repeat"]["boring"]["mean"]:+.3f}',
        '@@VL4_MS_LR@@': f'{M["low_repeat"]["structured"]["mean"]:+.3f} ± {M["low_repeat"]["structured"]["se"]:.3f}',
        '@@VL4_MS_LRN@@': str(M['low_repeat']['structured']['n']), '@@VL4_MS_N@@': str(G['structured']['windows']),
        '@@VL4_R2@@': f'{M["r2"]:.2f}',
    }


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
.note { color: var(--muted); font-size: 0.9rem; margin-top: -8px; }
li.correction { border-left: 3px solid var(--c-p05); padding-left: 10px; }
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
  <p class="deck">What a base model tracks about its own surprise, how it responds to it, and what can be steered on the "how likely is the next token" axis, and how steering breaks it; then, where its present state matters for its own future. Experiments S1 to S2(d), a 61-layer optimizer sweep, loop-margin tests K4 and K4b, and the value lens VL1 and VL2.</p>
  <ul class="meta">
    <li>2026-10-13 to 16</li>
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
    <li><strong>The present matters most in structured text, and least in loops and boilerplate.</strong> The value lens measures how much the model's next 32 predictions depend on its current state ("stakes"). Stakes is unrelated to how easy the text is. In human web text it is highest in procedures, lists and verse and lowest in boilerplate and spam, and loops cut it by 1.6 to 4×. When the model writes the text itself, fiction and verse stay high, while boilerplate and step-by-step procedures fall well below human text of the same difficulty. The steering knobs above are nearly neutral for the future, and none lies along the roughly ten stable directions that do move it.</li>
    <li><strong>The model represents its stakes, but not which way to go.</strong> A linear probe on layer 40 reads stakes with R² 0.38, against 0.04 for token identity. No direction's price is readable. It also forecasts how hard the coming text will be, beyond its running averages of how hard it has been (added R² 0.05).</li>
    <li><strong>The model does not lean toward easy futures.</strong> Among its top candidates, the ones that lead to more predictable continuations get slightly less probability than real text supports, not more (b = @@H3_B@@, SE @@H3_SE@@). The test recovers a planted lean. Nothing in its next-token choices so far looks like steering toward comfortable states.</li>
  </ol>
  <p>For homeostasis this means the model has a sensor (findings 1 and 2), but its first response to a deviation is positive feedback (finding 3). The actuators found on this axis are a global temperature dial and a plausible-tail shape (findings 4 and 5). The healthy regime sits between two traps on the temperature axis: loops on the certain side, incoherence on the uncertain side (finding 6). Whether anything later restores the slow surprise level after a kick is the open question for the kick test (K1). For valence, the model represents what is at stake and how hard the future will be (finding 8), but its choices don't favor easier futures (finding 9). Representation without a lean fits a predictor with no preferences over its own states, though it does not rule them out.</p>
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

  <h2>VL1: The value lens <span class="chip m">Measured</span></h2>
  <p>Question: which directions in the model's state would help or hurt its own future predictions, and where does the present state matter most? From the <a href="https://claude.ai/artifact/DvMrx6NYbLuAgj8ZrNc6FM">Value Lens</a> proposal.</p>
  <h3>Method</h3>
  <ul>
    <li><strong>Data:</strong> 1,200 windows of 192 fineweb tokens, teacher-forced; positions 32 to 158 in each (@@VL_POS@@ positions after dropping the 3% whose horizon crosses a blank line, usually a document boundary; with them in, the numbers barely change).</li>
    <li><strong>Gradients</strong> of log-likelihood with respect to the residual stream after block 40 (also read at 44, 50 and 56): <strong>now</strong>, <var>g</var><sub>now</sub> = ∂<var>l</var><sub>s</sub>/∂<var>h</var><sub>s</sub>, for the next token; <strong>future</strong>, <var>g</var><sub>fut</sub> = Σ<sub>k=1..32</sub> ∂<var>l</var><sub>s+k</sub>/∂<var>h</var><sub>s</sub>, for the 32 tokens after it.</li>
    <li><strong>Price</strong> of a direction <var>u</var>: <var>g</var> · <var>u</var>, the change in log-likelihood per unit push. Quoted per push of 0.1× the residual norm. <strong>Stakes:</strong> |<var>g</var><sub>fut</sub>|, how much the future depends on the present state at all.</li>
    <li>One backward pass per target token through a hand-written GLM-4 graph. Checked against finite differences and bitwise across slot layers; an independent code review found no result-affecting bugs. 109 s per window, 36 hours in all.</li>
  </ul>
  <figure>
    @@CHART_LAG@@
    <figcaption>How strongly the state at one position affects predictions <var>k</var> tokens later, averaged over all positions. The 32-token horizon captures most of it.</figcaption>
  </figure>
  <h3>The steering knobs barely matter to the future</h3>
  <div class="table"><table>
    <thead><tr><th>Direction</th><th>Layer</th><th>Now price</th><th>Future price</th><th>t (future)</th><th>Spread vs random</th></tr></thead>
    <tbody>@@VL_LIB_ROWS@@</tbody>
  </table></div>
  <ul>
    <li>Mean prices in nats per push of 0.1× the residual norm; t over windows. "Spread vs random" is the price's standard deviation over the same for random directions.</li>
    <li><strong>Real but tiny.</strong> The temperature vectors are worth +0.004 nats over the next 32 tokens (about 0.0001 per token), 20 times a random direction's typical mean. Sharpening (band p ≈ 0.5) costs about as much. To first order, the same push along each position's own <var>g</var><sub>fut</sub> would be worth about 3.5 nats, so the knobs buy about 0.1% of what is available.</li>
    <li><strong>Flattening helps later tokens but not the next one</strong>: the temperature vector's now price is zero.</li>
    <li>No price correlates with the current entropy or surprisal (all |r| &lt; 0.035).</li>
  </ul>
  <h3>Prices move along a small, very stable set of axes</h3>
  <ul>
    <li>Per position, what would help the next token and what would help the 32 after it are unrelated: the median cosine of <var>g</var><sub>now</sub> and <var>g</var><sub>fut</sub> is @@VL_COS@@.</li>
    <li><strong>Both gradients have a stable ten-dimensional subspace.</strong> On unit-normalized gradients, the top 10 directions from one half of the windows overlap the other half's by @@VR_FUTN@@ for <var>g</var><sub>fut</sub> and @@VR_NOWN@@ for <var>g</var><sub>now</sub> (chance 0.002). That holds with halves that share no document. Each gradient puts about 3% of its direction there (18 times chance).</li>
    <li class="correction"><strong>Correction.</strong> The first analysis used the raw second moment and found a weaker overlap (@@VL_FUT10@@ for <var>g</var><sub>fut</sub>) and none for <var>g</var><sub>now</sub> (@@VL_NOW10@@). Gradients are outlier-heavy: the top 1% of positions carry @@VR_CONC_FUT@@ of <var>g</var><sub>fut</sub>'s second moment and @@VR_CONC_NOW@@ of <var>g</var><sub>now</sub>'s. Different outliers land in each half and scramble the raw directions. Trimming the top 0.1% already gives @@VR_FUTT@@ and @@VR_NOWT@@.</li>
    <li><strong>The axes are symmetric and not semantic.</strong> Along each, pushing helps the future at about half the positions and hurts at the rest. They are not the residual stream's massive-activation coordinates (cosine with the mean state at most 0.12). Their most extreme contexts and J-lens decodes have no common theme. They look like generic channels through which a layer-40 state reaches later computation, with prices set locally on top.</li>
    <li><strong>None of the steering vectors lie along them</strong> (|cosine| with the temperature vector at most 0.025).</li>
  </ul>
  <h3>Where the present matters</h3>
  <p>Following protocol amendment A5, candidate good states come first. Per window, stakes is uncorrelated with how predictable the text is (r = @@VL_CORR@@).</p>
  <ul>
    <li><strong>Highest stakes:</strong> a step-by-step procedure (pursuit curves on a polygon); the Moby-Dick list "and Captain Ahab; and the leg he had lost; and the Cape Horn fit…"; a scholarly book description; Shakespeare.</li>
    <li><strong>Lowest stakes:</strong> SEO boilerplate ("it is a good idea to look for one that has plenty of information…"), a repetitive XML form, casino spam.</li>
    <li>Stakes is high where the present constrains a structured future, and low where the future is formulaic or noise whatever the present does. It tracks "the present matters", not "the text is easy". It is not valence.</li>
  </ul>
  <h3>Loops, boring text and fiction</h3>
  <p>The group's three scenarios: degenerate loops, boring text, rich worldbuilding. Loops are the first 96 tokens of a fineweb window followed by a repeated 12-token phrase or a repeated single token. Fiction is 12 worldbuilding openings continued by the model itself at temperature 1 with no truncation. Layer 40, means.</p>
  <div class="table"><table>
    <thead><tr><th>Text</th><th>Windows</th><th>Level (log p)</th><th>Stakes</th><th>Now |g|</th><th>Temperature price</th></tr></thead>
    <tbody>@@VL_SCEN_ROWS@@</tbody>
  </table></div>
  <p class="note">† Positions 100 to 158, all inside the loop, against the same positions of the same 16 windows without it. Temperature price: future part, temperature vector at layer 40.</p>
  <ul>
    <li><strong>Loops collapse stakes</strong>: 4× lower in phrase loops and 1.6× lower in token loops than in the same text without the loop. In a phrase loop the present barely matters, now or later.</li>
    <li><strong>In loops, flattening would hurt</strong>: the temperature price turns negative, at 7 to 20 times its usual size. This is because what comes next is more loop. The value lens is teacher-forced: it measures what helps predict the actual continuation, so it cannot say whether the model "wants" the loop.</li>
    <li><strong>Fiction and boring text are indistinguishable on stakes</strong> at this sample size (12 fiction windows). Level runs the other way from the expected ordering (rich &gt; boring &gt; loops): loops are the easiest text. Both the easiest and the hardest tenths have higher stakes than average.</li>
  </ul>

  <h2>VL2: Does the model represent its own stakes? <span class="chip m">Measured</span></h2>
  <p>If the value lens can be read linearly off the residual stream, later layers could use it, which is the "represented" half of the group's criterion for a welfare-relevant state. It would also make a live readout cheap: no backward passes.</p>
  <h3>Method</h3>
  <ul>
    <li>Layer-40 activations on the same windows (forward passes only). Ridge regression from the activation at <var>s</var> to each readout at <var>s</var>; fit on windows 0 to 799, ridge strength chosen on 800 to 899, tested on 900 to 1199.</li>
    <li>Baselines: least squares on entropy, the current token's surprisal and position; and the average per current token.</li>
  </ul>
  <div class="table"><table>
    <thead><tr><th>Readout</th><th>Probe R²</th><th>Within window</th><th>Entropy, surprisal, position</th><th>Per-token average</th></tr></thead>
    <tbody>@@VL_PROBE_ROWS@@</tbody>
  </table></div>
  <ul>
    <li><strong>Stakes is linearly represented</strong>: R² @@VP_STAKES@@ against @@VP_BASE@@ for entropy, surprisal and position and @@VP_TOK@@ for token identity, and about the same within windows, so it is per position. The target also depends on future tokens the model has not seen, so this is a lower bound.</li>
    <li><strong>The direction of value is not</strong>: no price, including the stable future directions, is predictable (R² ≤ 0.005). The model encodes how much is at stake, not which way to move.</li>
  </ul>
  <div class="table"><table>
    <thead><tr><th>Text (mean log stakes and log |g<sub>now</sub>|)</th><th>Windows</th><th>Stakes</th><th>Probe</th><th>Now</th><th>Probe</th></tr></thead>
    <tbody>@@VL_OOD_ROWS@@</tbody>
  </table></div>
  <p>The probe was fit on fineweb only. It transfers to fiction. In loops it sees lower stakes but misses about two thirds of the collapse (in log terms), while the now size transfers well.</p>
  <p class="note">Train and test windows here are contiguous blocks of the fineweb file, so no document is in both. (The VL1 windows sit at random offsets and 35 pairs overlap; the index split gave the same R².)</p>

  <h2>VL4: Stakes when every text is model-written <span class="chip m">Measured</span></h2>
  <p>VL1's scenarios compared model-written fiction with human web text, so authorship and genre were confounded. Here every group is written by the model. The prompts are 36 fiction openings, 36 boring openings (SEO filler, policies, listings, corporate prose) and 24 structured ones (procedures, recipes, proofs, verse, code). Each is continued at temperature 1 with no truncation, then put through the value lens as in VL1 (@@VL4_N@@ windows). Standard errors and tests use the prompt as the unit.</p>
  <div class="table"><table>
    <thead><tr><th>Group</th><th>Prompts</th><th>Windows</th><th>Log-likelihood</th><th>Stakes (|g_fut|)</th><th>Stakes vs human text of the same difficulty</th><th>Within-group corr(log-likelihood, stakes)</th></tr></thead>
    <tbody>@@VL4_ROWS@@</tbody>
  </table></div>
  <ul>
    <li><strong>Fiction has the highest stakes</strong>, above boring prose by @@VL4_FB@@ (p @@VL4_FB_P@@). It sits above human text of the same difficulty, as in VL1.</li>
    <li><strong>Difficulty confounds the raw ordering.</strong> Fiction is much harder to predict than the other two. In human text stakes barely depends on difficulty (a quadratic fit has R² @@VL4_R2@@), so each window is compared with human text of the same log-likelihood.
      <ul>
        <li>Model-written boring prose then sits well below human text (@@VL4_MB@@), robustly: dropping its most repetitive windows changes nothing (@@VL4_MB_LR@@).</li>
        <li>Structured text also sits below (@@VL4_MS@@), but only its step-by-step windows do. These are derivations, assembly and recipe steps, code and patterns, which are also the ones with more than 5% repeated 4-grams. The rest (verse, proofs, an itinerary, chess notes) are at the human level (@@VL4_MS_LR@@, @@VL4_MS_LRN@@ of @@VL4_MS_N@@ windows).</li>
        <li>Structured and boring text no longer differ: @@VL4_MSB@@ (p @@VL4_MSB_P@@), against a raw difference of @@VL4_SB@@ (p @@VL4_SB_P@@).</li>
      </ul>
    </li>
    <li><strong>Within model-written boring and structured text, the easier a window, the lower its stakes.</strong> In human text there is no such relation.</li>
  </ul>
  <div class="table"><table>
    <thead><tr><th>Group</th><th>End</th><th>Stakes</th><th>Window opening</th></tr></thead>
    <tbody>@@VL4_EX_ROWS@@</tbody>
  </table></div>
  <p>The lowest-stakes windows are the most predictable ones: step-by-step derivations and marketing filler. The highest are verse, a proof, meeting minutes and invented-world fiction. A conjecture: when the model writes text it finds easy, the continuation is nearly forced and many states lead to the same future, so no single state matters much. Human text that is easy to predict often still hinges on specifics such as names and numbers. That would also explain why "structured" is not one thing for stakes: derivations are low and verse is high. It is a reading of a dozen windows, not a test.</p>

  <h2>VL3: What the stable axes are <span class="chip m">Measured</span></h2>
  <p>VL1 found a small set of directions along which the future-value gradient reliably points. Here they come from unit-normalized gradients, so a few extreme positions don't dominate them. Each is read through its extreme contexts, the tokens around them, and the J-lens.</p>
  <ul>
    <li><strong>Every one replicates, and every one is two-sided.</strong> The top 10 directions of g_fut have split-half |cos| 0.91 to 1.00. Each is positive at 47 to 49% of positions with no skew: pushing along it helps the future at about half the positions and hurts it at the other half. Prices are set locally, around a fixed set of axes.</li>
    <li><strong>They are not the massive-activation coordinates.</strong> The mean layer-40 state is dominated by three huge coordinates, but the subspace has cosine at most 0.12 with it. g_fut's subspace is spread out (its top 10 coordinates hold 10%); g_now's leans more on a few (25%).</li>
    <li><strong>They are not semantically legible.</strong> The most extreme contexts reach only 5 to 7 sd and share no theme. The J-lens reads mostly rare multilingual tokens. Exceptions are punctuation and line ends on one side of three directions, and abstract Latinate words on one.</li>
    <li><strong>The steering knobs are not in them</strong> (|cos| with the temperature vector at most 0.025).</li>
  </ul>
  <p>These look like the generic routes by which a layer-40 state affects later computation, rather than represented objects or goals.</p>

  <h2>H2: Does the model forecast its own future predictability? <span class="chip m">Measured</span></h2>
  <p>Step 3 of the Value Lens proposal: can the state predict how hard the coming text will be, beyond what the model already knows about how hard it has been? This is prediction, not valence. It is the "represented" half of the criterion.</p>
  <ul>
    <li><strong>Target:</strong> mean surprisal of the next 8 or 32 tokens after the next one.</li>
    <li><strong>Baseline</strong> (all known at the current position): current entropy, mean surprisal over the last 32 and last 8 tokens (the slow document variable from S1), the current token's surprisal, position.</li>
    <li><strong>Combined:</strong> the baseline plus a ridge probe from the layer-40 state to what the baseline misses. Held-out documents only.</li>
  </ul>
  <div class="table"><table>
    <thead><tr><th>Target</th><th>Baseline R²</th><th>State alone</th><th>Combined</th><th>Added by the state</th></tr></thead>
    <tbody>@@H2_ROWS@@</tbody>
  </table></div>
  <p><strong>H2 holds, modestly.</strong> The state carries about 0.05 of R² about the coming text's difficulty beyond the running averages, on documents it was not fit on. The proposal's falsifier was no added R².</p>

  <h2>H3: Does the model lean toward easy futures? <span class="chip m">Measured</span></h2>
  <p>The Value Lens proposal's test of whether valuation is upstream of behavior. Does the model give more probability to next tokens that lead to easier futures than real text supports? A model that steered itself toward comfortable states would show it here.</p>
  <ul>
    <li><strong>Data:</strong> @@H3_WIN@@ held-out fineweb windows, 6 positions each (@@H3_POS@@ positions).
      <ul>
        <li>At each position, each of the model's top 8 candidates is continued 4 times for 16 tokens, at temperature 1 with no truncation.</li>
        <li>Every candidate gets the same random numbers, so differences between candidates are not sampling luck.</li>
      </ul>
    </li>
    <li><strong>Ease of a candidate's future (V):</strong> minus the mean next-token entropy over the 16 steps after it.</li>
    <li><strong>Fit:</strong> a conditional logit over the 8 candidates against the token that actually came next, q(x) ∝ exp(a·log p(x) + b·V(x)).
      <ul>
        <li>b &lt; 0 is a lean: the model over-weights easy futures.</li>
        <li>b &gt; 0: real text goes to easy futures more often than the model expects.</li>
        <li>Only positions where the actual token is in the top 8 are used (@@H3_USED@@, @@H3_USEDPCT@@). Standard errors come from resampling windows.</li>
      </ul>
    </li>
    <li><strong>Rollout noise:</strong> within a position, V varies by @@H3_SDV@@ nats. Two halves of the rollouts agree at r = @@H3_SH@@, so V from all 4 has reliability about @@H3_REL@@.</li>
  </ul>
  <h3>Positive control</h3>
  <p>Synthetic outcomes are drawn from the model's own probabilities tilted by β times V from one half of the rollouts. They are then fit with V from the other half, which has independent noise.</p>
  <div class="table"><table>
    <thead><tr><th>True tilt β</th><th>Recovered b (other half)</th><th>Recovered b (same half)</th></tr></thead>
    <tbody>@@H3_GATE_ROWS@@</tbody>
  </table></div>
  <p>The test passes. With the same half it recovers β, and the null (β = 0) sits near zero. With independent noise b keeps the right sign but shrinks to between a fifth and two fifths of β, so real-text values of b are strongly attenuated.</p>
  <h3>Real text</h3>
  <div class="table"><table>
    <thead><tr><th>Model</th><th>b</th><th>SE</th><th>b / SE</th></tr></thead>
    <tbody>@@H3_REAL_ROWS@@</tbody>
  </table></div>
  <ul>
    <li><strong>No lean; a small effect the other way.</strong> b = @@H3_B@@ (95% interval @@H3_LO@@ to @@H3_HI@@). The actual next token is more often the candidate with the easier future than the model's own probabilities say.
      <ul>
        <li>For scale, in the control a lean of β = −0.25 shows as b = @@H3_G025@@ and β = −0.5 as @@H3_G05@@.</li>
        <li>It survives token frequency and class and the token's own average V, so it is a contrast within token types.</li>
        <li>Both the next step and the 15 after it contribute: @@H3_SD1@@ and @@H3_SDL@@ nats of log-odds per standard deviation. The next step's entropy has no rollout noise, so the later steps' true share is larger.</li>
        <li>It is strongest where the model is already confident: b = @@H3_ST0@@ (SE @@H3_ST0SE@@) at positions with entropy below 1 nat.</li>
      </ul>
    </li>
    <li><strong>It is small.</strong> @@H3_PERSD@@ nats of log-odds per standard deviation of V, perhaps 2 to 3 times that without rollout noise. Fit quality improves by @@H3_NLL@@ nats per position. Within its top 8 the model is also slightly over-confident (a = @@H3_A@@).</li>
    <li><strong>What it can't separate:</strong> this measures the model's net miscalibration along V. A lean in the model and a tendency of human text toward predictable continuations would add up.</li>
    <li><strong>Not the copy choice itself.</strong> A candidate that repeats earlier text has an easy future, so the model under-predicting repetition would also give b &gt; 0.
      <ul>
        <li>With indicators for the candidate occurring earlier in the window, or continuing an earlier bigram or trigram, b stays @@H3C_B@@ (SE @@H3C_SE@@). The indicators themselves come out near zero: the model is already calibrated about copying.</li>
        <li>But b is larger at positions where some candidate continues an earlier bigram (@@H3C_WB@@, SE @@H3C_WBSE@@) than where none does (@@H3C_NB@@, SE @@H3C_NBSE@@). So the effect is partly concentrated in passages where copying is possible.</li>
      </ul>
    </li>
  </ul>

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
    <li><strong>The value lens is teacher-forced and local.</strong> Prices are first-order (gradients) and measured against the text that actually follows, so they describe what would help predict this continuation, not what the model would choose. Stakes is a candidate "what matters now" variable, not a measure of valence.</li>
    <li><strong>Optimizer settings.</strong> The sweep uses 60 steps per layer (the layer-40 run used 200; its control reached 62% at step 60 against 72% at step 200).</li>
  </ul>

  <h2>What comes next</h2>
  <ul>
    <li><strong>Concept vectors and loops:</strong> build a concept vector on GLM, measure its component along the temperature axis, and run it through K4 and K4b.</li>
    <li><strong>K1, kick test:</strong> does the slow surprise level return after a forced surprising token faster than evidence alone predicts? Needs fresh rollouts with min_p = 0.</li>
    <li><strong>Steer along the stable future-value axes</strong> under K4 endpoints, to see what they do to text.</li>
    <li><strong>An exact mode for prices in the loom.</strong> The live stakes readout from the VL2 probe is built (llama-server <code>--value-probe</code>, a "value" view in minloomwebui).</li>
  </ul>

  <h2>Where things are</h2>
  <ul>
    <li>Data: <code>/mnt/models/homeo/</code> (<code>s1</code>, <code>s2</code>, <code>s2b</code>, <code>band2</code>, <code>logits</code>, <code>s2opt</code>, <code>s2sweep</code>, <code>s2big</code>, <code>k4</code>, <code>value</code>, <code>value_scen</code>, <code>value_scen2</code>, <code>value_probe</code>, <code>lean</code>)</li>
    <li>Analysis: <code>homeo/s1_probe.py</code>, <code>s2_make_vecs.py</code>, <code>s2b_band_vecs.py</code>, <code>s2b_summarize.py</code>, <code>s2c_logit_identity.py</code>, <code>s2sweep_summary.py</code>, <code>s2d_within_token.py</code>, <code>k4_loop_summary.py</code>, <code>value_lens.py</code>, <code>value_scenarios_prep.py</code>, <code>value_scenarios.py</code>, <code>value_probe.py</code>, <code>value_forecast.py</code>, <code>value_directions.py</code>, <code>value_structure_robust.py</code>, <code>value_scenarios2.py</code>, <code>lean_fit.py</code>, <code>lean_copy.py</code>, <code>value_readout_export.py</code>, <code>log_tf_exposure.py</code>; this report: <code>homeo/results_report.py</code></li>
    <li>Tools: <code>llama.cpp/tools/homeo/</code> and <code>llama.cpp/tools/jspace/</code></li>
    <li>Running notes: <code>NOTES-homeostasis.md</code></li>
  </ul>
  <p class="credits">Experiments run and report drafted by Claude (Opus 5.5) in collaboration. This is a working report to base an official write-up on.</p>
</article>
</div>
'''

if __name__ == '__main__':
    main()
