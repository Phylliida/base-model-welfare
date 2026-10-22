#!/usr/bin/env python3
"""Table 1 (difficulty of kinds of text): mean surprisal under the model, from the value-lens scenario run.

Source: homeo/value_scenarios.py's summary ($VALUE_SCEN/summary.txt; runs/value/run.sh + runs/value/followup.sh made
the windows and log-likelihoods). "level" there is the mean log-likelihood of the next token over the probe positions;
difficulty = -level. Positions: 32-158 of 192-token windows for the whole-window groups (1,200 FineWeb windows, their
easiest tenth, 12 model-written fiction windows); 100-158, all inside the loop, for the loop windows (16 each).
"""
import re
from decimal import Decimal, ROUND_HALF_UP

from common import VALUE_SCEN, Out

ROWS = [('Phrase loop', 'phrase loop (period 12)'), ('Token loop (``the the the\'\')', 'token loop ("the the the")'),
        ('FineWeb subset, easiest tenth', 'fineweb, easiest tenth (boring)'), ('FineWeb subset, all', 'fineweb, all'),
        ('Model-written fiction', 'fiction (model-written)')]
txt = open(f'{VALUE_SCEN}/summary.txt').read()
o = Out('difficulty_table.tex')
o('% Table 1: mean surprisal (nats per token); from ' + f'{VALUE_SCEN}/summary.txt (difficulty = -level)')
o('\\begin{tabular}{lr}')
o('  \\toprule')
o('  Text & Difficulty \\\\')
o('  \\midrule')
for tex, key in ROWS:
    m = re.search(re.escape(key) + r'\s+(\d+)\s+(-?\d+\.\d+)', txt)
    n, level = int(m.group(1)), Decimal(m.group(2))
    d = (-level).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)  # exact decimal rounding of the printed value
    o(f'  {tex:40s} & ${d}$ \\\\  % n = {n} windows')
o('  \\bottomrule')
o('\\end{tabular}')
o.save()
